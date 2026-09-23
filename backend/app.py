# =========================================================================
# PALAYSCAN - BACKEND CENTRAL API CONTROLLER (app.py)
# =========================================================================
# This is the main server file for the Palayscan system built using the Flask web framework.
# It acts as the "brain" of the application, connecting the frontend client to:
# 1. Image processing algorithms (Color mask analysis & Texture analysis).
# 2. MariaDB database storage (CRUD for user records, stats, disease advice).
# 3. AI Leaf Healing (Image inpainting to simulate healthy leaves).
# 4. Report exports (CSV spreadsheet generation for administration).

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import cv2
import numpy as np
import os
import base64
import uuid
import functools
from datetime import datetime, date
import sys

# Ensure backend directory is in sys.path so local imports resolve reliably
_backend_dir = os.path.dirname(os.path.abspath(__file__))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

# --- Import custom local processing modules ---
from color_analysis import analyze_color, extract_lesion_hotspots       # Detects leaf color thresholds, lesions, and growth stages
from texture_analysis import analyze_texture   # Evaluates leaf surface textures for disease patterns
from disease_db import (
    get_advice, filter_diseases_by_weather,
    # User Account Auth Functions
    check_username_exists, check_email_exists, create_user, verify_password, create_session,
    get_user_by_token, delete_session, update_user_password, verify_user_password_by_id,
    # Scan Logs
    save_scan_record, get_scan_record_by_id,
    # Admin Stats & Queries
    get_all_scan_records, get_all_users, delete_user_by_id, get_dashboard_stats,
    admit_staff_user, reject_staff_user,
    # Disease DB CRUD Controls
    get_all_disease_advice, add_disease_advice, update_disease_advice, delete_disease_advice,
    get_scan_records_for_report, get_barangay_summary,
    # Audit Trail
    log_audit, get_audit_logs,
    # Heat Map Data
    get_barangay_heatmap_data,
    # Backup & Restore
    export_all_database_records, import_database_records
)
from image_comparison import ImageComparison   # Visual comparison (MobileNetV2 feature embeddings)

# --- 1. SYSTEM DIRECTORY SETUP ---
# Map relative directories dynamically to make sure the app works on WAMP or any host
backend_dir  = os.path.dirname(__file__)
frontend_dir = os.path.join(os.path.dirname(backend_dir), 'frontend')
uploads_dir  = os.path.join(backend_dir, 'uploads')
os.makedirs(uploads_dir, exist_ok=True) # Automatically create upload directory if missing

# Initialize the image similarity comparison module
image_comparator = ImageComparison(reference_dir="dataset")
print(f"[App] Reference image counts: {image_comparator.get_stats()}")

# Asynchronously pre-load Deep Learning Model in background thread so Gunicorn boots instantly
from dl_analysis import load_dl_model
import threading

def _async_warmup():
    print("[App] Asynchronously pre-warming deep learning model in background...")
    load_dl_model()
    print("[App] Deep learning model pre-warmed successfully.")

threading.Thread(target=_async_warmup, daemon=True).start()

# Initialize the Flask Application
app = Flask(__name__)
CORS(app) # Enable CORS (Cross-Origin Resource Sharing) so our frontend pages can talk to port 5000


# --- 2. AUTHENTICATION ROUTING MIDDLEWARE (DECORATORS) ---

def get_token_from_request():
    """Extracts the cryptographic session Bearer token from the HTTP Authorization request header."""
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        return auth_header[7:] # Slice out the "Bearer " prefix to isolate the raw token
    return None

def require_auth(f):
    """
    Decorator function: Secures an endpoint to require a login session token.
    Blocks requests with invalid/expired tokens and responds with a 401 Unauthorized status.
    """
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        token = get_token_from_request()
        user = get_user_by_token(token)
        if not user:
            return jsonify({"error": "Authentication required. Please log in."}), 401
        request.current_user = user # Inject user details into Flask's request context
        return f(*args, **kwargs)
    return decorated

def require_admin(f):
    """
    Decorator function: Restricts access to administrator profiles or approved MAO Staff.
    Checks the user's role and returns 403 Forbidden if they are not an administrator or approved staff.
    """
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        token = get_token_from_request()
        user = get_user_by_token(token)
        if not user:
            return jsonify({"error": "Authentication required."}), 401
        is_admin = user.get('role') == 'admin'
        is_approved_staff = user.get('role') == 'staff' and user.get('staff_status') == 'approved'
        if not (is_admin or is_approved_staff):
            return jsonify({"error": "Admin or approved MAO Staff access required."}), 403
        request.current_user = user # Inject user details
        return f(*args, **kwargs)
    return decorated


# --- 3. STATIC RESOURCE ROUTING ---
# Handlers to serve static HTML, CSS, JavaScript, and uploaded leaf images to the client browser.

@app.route("/")
def home():
    """Serves the main login page on root access."""
    return send_from_directory(frontend_dir, 'login.html')

@app.route("/uploads/<path:filename>")
def serve_upload(filename):
    """Serves uploaded leaf photos stored in WAMP backend directory."""
    return send_from_directory(uploads_dir, filename)

@app.route("/reference-image/<disease>")
def serve_reference_image(disease):
    """Serves a clear reference comparison photograph from the dataset for a given rice disease."""
    dataset_base = os.path.join(backend_dir, 'dataset', 'Rice Disease')
    target_dir = os.path.join(dataset_base, disease)
    if not os.path.exists(target_dir):
        for d in os.listdir(dataset_base):
            if d.lower() == disease.lower():
                target_dir = os.path.join(dataset_base, d)
                break
    if os.path.exists(target_dir):
        files = [f for f in sorted(os.listdir(target_dir)) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
        if files:
            # Pick a clear representative photo from the folder
            idx = min(len(files) // 2, len(files) - 1)
            return send_from_directory(target_dir, files[idx])
    return jsonify({"error": "No reference image found"}), 404


# --- 4. SECURE USER ACCOUNT ROUTING (AUTHENTICATION) ---

@app.route("/register", methods=["POST"])
def register():
    """Handles new user registrations with username, DOB, and auto-calculated age. Stores in MariaDB."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid request."}), 400

    full_name      = (data.get('full_name') or '').strip()
    username       = (data.get('username') or '').strip().lower()
    email          = (data.get('email') or '').strip().lower()
    password       = data.get('password') or ''
    role           = data.get('role') or 'farmer'
    address        = (data.get('address') or '').strip()
    sex            = (data.get('sex') or 'Male').strip()
    dob            = (data.get('dob') or '').strip()
    barangay       = (data.get('barangay') or '').strip()
    contact_number = (data.get('contact_number') or '').strip()

    # Form field validation
    if not full_name or not username or not password:
        return jsonify({"error": "Full name, username, and password are required."}), 400
    if len(username) < 3:
        return jsonify({"error": "Username must be at least 3 characters."}), 400
    if not username.replace('_', '').replace('-', '').isalnum():
        return jsonify({"error": "Username can only contain letters, numbers, hyphens, and underscores."}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters."}), 400
    if role not in ('farmer', 'staff'):
        return jsonify({"error": "Invalid role selected."}), 400

    # Auto-calculate age from Date of Birth
    age = 0
    if dob:
        try:
            from datetime import date
            parts = [int(p) for p in dob.split('-')]
            birth_d = date(parts[0], parts[1], parts[2])
            today_d = date.today()
            age = today_d.year - birth_d.year - ((today_d.month, today_d.day) < (birth_d.month, birth_d.day))
        except Exception:
            age = 0
    else:
        try:
            age = int(data.get('age') or 0)
        except (ValueError, TypeError):
            age = 0

    if age < 1 or age > 120:
        return jsonify({"error": "Please provide a valid Date of Birth resulting in an age between 1 and 120."}), 400

    if check_username_exists(username):
        return jsonify({"error": f"The username '{username}' is already taken. Please choose another."}), 409

    if email and check_email_exists(email):
        return jsonify({"error": "This email is already registered."}), 409

    staff_status = 'pending' if role == 'staff' else 'approved'

    # Add account record to users table
    user_id = create_user(full_name, username, password, role, staff_status, address, sex, age, barangay, contact_number, email=email, dob=dob)
    if not user_id:
        return jsonify({"error": "Registration failed. Please try again."}), 500

    # Audit trail logging
    log_audit("USER_REGISTER", f"Registered new user '{username}' ({role}) from {barangay or 'Bacnotan'}",
              user_id=user_id, username=username, role=role, ip_address=request.remote_addr)

    if role == 'staff':
        msg = "Account created! Since you registered as MAO Staff, your account requires Admin approval before accessing the Admin Panel. You may log in as a Farmer in the meantime."
    else:
        msg = "Account created successfully!"

    return jsonify({"message": msg, "user_id": user_id, "username": username, "age": age, "dob": dob, "role": role, "staff_status": staff_status}), 201


@app.route("/login", methods=["POST"])
def login():
    """Validates login credentials via username. Issues a session token if login is successful."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid request."}), 400

    identifier = (data.get('username') or data.get('email') or '').strip().lower()
    password   = data.get('password') or ''

    if not identifier or not password:
        return jsonify({"error": "Username and password are required."}), 400

    # Cross-reference with database users table (username or email fallback)
    user = verify_password(identifier, password)
    if not user:
        log_audit("LOGIN_FAILED", f"Failed login attempt for identifier '{identifier}'",
                  username=identifier, ip_address=request.remote_addr)
        return jsonify({"error": "Incorrect username or password."}), 401

    # Issue secure session token stored in user_sessions table
    token = create_session(user['id'])
    if not token:
        return jsonify({"error": "Could not create session. Please try again."}), 500

    log_audit("USER_LOGIN", f"User '{user['username']}' logged in successfully",
              user_id=user['id'], username=user['username'], role=user['role'], ip_address=request.remote_addr)

    return jsonify({
        "token": token,
        "user": {
            "id":           user['id'],
            "full_name":    user['full_name'],
            "username":     user['username'],
            "email":        user['email'],
            "role":         user['role'],
            "staff_status": user.get('staff_status', 'approved'),
            "address":      user.get('address', ''),
            "sex":          user.get('sex', 'Male'),
            "age":          user.get('age', 0),
            "dob":          user.get('dob', ''),
            "barangay":     user['barangay']
        }
    })


@app.route("/logout", methods=["POST"])
def logout():
    """Wipes session token from database when logging out."""
    token = get_token_from_request()
    if token:
        user = get_user_by_token(token)
        if user:
            log_audit("USER_LOGOUT", f"User '{user['username']}' logged out",
                      user_id=user['id'], username=user['username'], role=user['role'], ip_address=request.remote_addr)
        delete_session(token)
    return jsonify({"message": "Logged out successfully."})


@app.route("/me", methods=["GET"])
@require_auth
def me():
    """Profile retrieval route to check logged-in status."""
    return jsonify({"user": request.current_user})


@app.route("/change-password", methods=["POST"])
@require_auth
def change_password():
    """Securely updates password for the authenticated user or admin."""
    data = request.get_json() or {}
    current_password = data.get("current_password") or ""
    new_password     = data.get("new_password") or ""

    if not current_password or not new_password:
        return jsonify({"error": "Current password and new password are required."}), 400

    if len(new_password) < 6:
        return jsonify({"error": "New password must be at least 6 characters long."}), 400

    user_id = request.current_user['id']

    # Verify current password
    if not verify_user_password_by_id(user_id, current_password):
        return jsonify({"error": "Incorrect current password."}), 400

    # Save new hashed password
    if not update_user_password(user_id, new_password):
        return jsonify({"error": "Failed to update password. Please try again."}), 500

    log_audit("PASSWORD_CHANGE", f"User '{request.current_user['username']}' updated their password",
              user_id=user_id, username=request.current_user['username'],
              role=request.current_user.get('role'), ip_address=request.remote_addr)

    return jsonify({"message": "Password updated successfully!"})


# --- 5. ENCYCLOPEDIA & METRIC RETRIEVAL ROUTES ---

@app.route("/disease-advice")
def disease_advice():
    """Queries treatment suggestions for a disease from MariaDB."""
    disease = request.args.get('disease')
    if not disease:
        return jsonify({"error": "No disease specified"}), 400
    advice = get_advice(disease)
    return jsonify({"disease": disease, "advice": advice})

@app.route("/reference-stats")
def reference_stats():
    """Returns dataset stats to show how many images are in training/similarity database."""
    stats = image_comparator.get_stats()
    return jsonify({
        "total_reference_images": sum(stats.values()),
        "diseases_covered": len(stats),
        "breakdown": stats,
    })


# --- 6. LOCAL LANGUAGE EXPLANATION GENERATORS (TAGALOG HELPER) ---

def get_tagalog_translation(disease_name, stage, weather):
    """
    Compiles localized descriptions matching the growth stage and weather conditions.
    Explains context to farmers during the capstone demo.
    """
    translations = {
        "Blight":     "Nakitaan ng Blight ang iyong palay. Ito ay sanhi ng bacteria at mabilis kumalat.",
        "Blast":      "Mayroong Blast ang iyong palay. Ito ay isang mapanirang sakit na sumisira sa mga dahon.",
        "Brown Spot": "Mayroong Brown Spot ang iyong palay. Kadalasan ito ay dahil sa kulang na sustansya ng lupa.",
        "Leaf Streak": "May Leaf Streak ang palay. Ito ay mga maninipis na guhit sa dahon.",
        "Leaf Strip":  "May Leaf Streak ang palay. Ito ay mga maninipis na guhit sa dahon.",
        "Healthy":    "Maganda ang kalagayan ng iyong palay. Walang nakitang sakit."
    }
    base = translations.get(disease_name, f"Ang iyong palay ay posibleng may {disease_name}.")
    
    stage_msg = ""
    if stage == "Seedling":
        stage_msg = "Nasa seedling stage pa lamang ito, kaya agapan agad upang hindi mamatay ang punla."
    elif stage == "Tillering":
        stage_msg = "Nasa tillering stage na ito, kaya mahalagang gamutin para dumami ang mga suwi."
    elif stage == "Heading":
        stage_msg = "Nasa heading stage na ang palay. Ingatan ito upang hindi maapektuhan ang mga butil."
    elif stage == "Maturity":
        stage_msg = "Malapit nang anihin ang palay. Huwag nang maglayag ng matatapang na kemikal."
        
    weather_msg = ""
    if weather == "hot" and disease_name != "Healthy":
        weather_msg = "Ang mainit na panahon ngayon ay maaaring magpabilis sa pagkalat ng sakit na ito."
    elif weather == "cold" and disease_name != "Healthy":
        weather_msg = "Ang malamig na panahon ay lalong nagpapahina sa resistensya ng palay."
        
    return f"{base} {stage_msg} {weather_msg}".strip()

def get_tagalog_advice(disease_name):
    """Retrieves list of advice steps in Tagalog, fallback to local office recommendation."""
    from disease_db import get_advice
    db_advice = get_advice(disease_name)
    if db_advice:
        return db_advice
    return ["Kumunsulta sa inyong lokal na agriculturist sa munisipyo para sa tamang gamot."]


def detect_leaf_streaks(img):
    """
    Detects if an image contains interveinal narrow parallel streaks characteristic
    of Bacterial Leaf Streak. Returns (streak_count, max_aspect_ratio).
    """
    h, w = img.shape[:2]
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    green_mask = cv2.inRange(hsv, (35, 30, 30), (85, 255, 255))
    non_green = cv2.bitwise_not(green_mask)
    cnts, _ = cv2.findContours(non_green, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    vertical_streaks = []
    for c in cnts:
        area = cv2.contourArea(c)
        if area < 70:
            continue
        x, y, cw, ch = cv2.boundingRect(c)
        # Narrow vertical interveinal stripe:
        # 1. Height is at least 2.8x width (vertical orientation)
        # 2. Width is narrow (<= 0.08 * image width, typically < 60px)
        # 3. Height is at least 35 px
        if ch >= 2.8 * cw and cw <= 0.08 * w and ch >= 35:
            vertical_streaks.append((cw, ch, ch / max(1, cw), area))
            
    num_streaks = len(vertical_streaks)
    max_ar = max([s[2] for s in vertical_streaks]) if vertical_streaks else 0.0
    return num_streaks, max_ar


# --- 7. CORE DIAGNOSTIC LOGIC ---

DISEASE_DIAGNOSTIC_EXPLANATIONS = {
    "Brown Spot": {
        "name": "Brown Spot",
        "name_tl": "Brown Spot (Mantsang Kayumanggi)",
        "lesion_color": "Reddish-Brown with Yellow Halo",
        "lesion_color_tl": "Mamula-mulang Kayumanggi na may Dilaw na Paligid",
        "color_hex": ["#78350f", "#ca8a04"],
        "symptom": "Circular to oval reddish-brown lesions with gray necrotic centers and yellow chlorotic halos.",
        "symptom_tl": "Maliliit na bilog o pahabang kayumangging patse na may abuhing gitna at madilaw na paligid sa dahon.",
        "why_detected": "The leaf blade exhibits discrete circular/oval brown spots with necrotic centers, characteristic of Bipolaris oryzae fungal infection."
    },
    "Blast": {
        "name": "Rice Blast",
        "name_tl": "Rice Blast (Pumutok/Dahon Blast)",
        "lesion_color": "Grayish-White with Dark Brown Margin",
        "lesion_color_tl": "Abuhing Puti na may Maitim na Kayumangging Gilid",
        "color_hex": ["#94a3b8", "#78350f"],
        "symptom": "Spindle-shaped or diamond-shaped lesions with pointed ends, gray-whitish centers, and dark brown margins.",
        "symptom_tl": "Hugis-brilyanteng mga sugat na may matulis na dulo, abuhing gitna, at maitim na kayumangging gilid.",
        "why_detected": "Diamond- or spindle-shaped lesions observed across the leaf blade, characteristic of Pyricularia oryzae fungal blast."
    },
    "Blight": {
        "name": "Bacterial Leaf Blight",
        "name_tl": "Bacterial Leaf Blight (Bacterial Hawas)",
        "lesion_color": "Straw-Yellow to Bleached Wavy White",
        "lesion_color_tl": "Madilaw na Dayami hanggang Maputing Guhit",
        "color_hex": ["#eab308", "#fef08a"],
        "symptom": "Water-soaked stripes starting from leaf tips and margins, rapidly turning wavy yellowish-white or straw-colored.",
        "symptom_tl": "Parang basang mga guhit mula sa dulo at gilid ng dahon na nagiging madilaw hanggang mapuputi.",
        "why_detected": "Marginal chlorotic and wavy lesions progressing inward along veins from the leaf margin, indicative of Xanthomonas oryzae."
    },
    "Leaf Streak": {
        "name": "Leaf Streak",
        "name_tl": "Bacterial Leaf Streak (Leaf Streak)",
        "lesion_color": "Narrow Yellowish-Brown Streaks",
        "lesion_color_tl": "Maninipis na Dilaw-Kayumangging Guhit",
        "color_hex": ["#b45309", "#d97706"],
        "symptom": "Narrow, interveinal linear streaks between leaf veins that turn yellowish-brown.",
        "symptom_tl": "Maninipis na linyang sugat sa pagitan ng mga ugat ng dahon na nagiging kulay kayumanggi.",
        "why_detected": "Linear lesion streaks restricted between leaf veins with translucent or yellowish-brown appearance."
    },
    "Leaf Strip": {
        "name": "Leaf Streak",
        "name_tl": "Bacterial Leaf Streak (Leaf Streak)",
        "lesion_color": "Narrow Yellowish-Brown Streaks",
        "lesion_color_tl": "Maninipis na Dilaw-Kayumangging Guhit",
        "color_hex": ["#b45309", "#d97706"],
        "symptom": "Narrow, interveinal linear streaks between leaf veins that turn yellowish-brown.",
        "symptom_tl": "Maninipis na linyang sugat sa pagitan ng mga ugat ng dahon na nagiging kulay kayumanggi.",
        "why_detected": "Linear lesion streaks restricted between leaf veins with translucent or yellowish-brown appearance."
    },
    "Healthy": {
        "name": "Healthy",
        "name_tl": "Malusog na Palay",
        "lesion_color": "Vibrant Clean Green (No Lesions)",
        "lesion_color_tl": "Matingkad na Luntian (Walang Sugat)",
        "color_hex": ["#22c55e", "#16a34a"],
        "symptom": "Uniform green leaf tissue with no necrotic lesions or pathogen spots.",
        "symptom_tl": "Matingkad na luntiang dahon nang walang anumang sugat o bakas ng peste.",
        "why_detected": "No significant necrotic or fungal discoloration detected on the leaf surface."
    }
}


def has_visual_evidence_for_disease(disease_name, tex_metrics):
    """
    Validates whether the leaf actually possesses the physical morphological and color 
    characteristics of the candidate disease.
    If the leaf tissue does not exhibit these characteristics, the disease CANNOT be
    pinpointed in the Diagnostic Visualization and must be completely rejected from
    secondary considerations.
    """
    if not disease_name or disease_name == "Healthy" or not tex_metrics:
        return False
        
    brown_ratio   = tex_metrics.get('brown_ratio', 0.0)
    straw_ratio   = tex_metrics.get('straw_ratio', 0.0)
    white_ratio   = tex_metrics.get('white_ratio', 0.0)
    yellow_ratio  = tex_metrics.get('yellow_ratio', 0.0)
    orange_ratio  = tex_metrics.get('orange_ratio', 0.0)
    gray_ratio    = tex_metrics.get('gray_ratio', 0.0)
    num_streaks   = tex_metrics.get('num_streaks', 0)
    max_streak_ar = tex_metrics.get('max_streak_ar', 1.0)
    straw_white_ratio = straw_ratio + white_ratio

    if disease_name == "Blight":
        # Blight requires distinct straw-yellow to bleached lesions along leaf margins/veins
        return (straw_white_ratio >= 0.030 or (straw_white_ratio >= 0.018 and yellow_ratio >= 0.12) or (yellow_ratio >= 0.18 and max_streak_ar >= 2.5))
        
    elif disease_name == "Brown Spot":
        # Brown Spot requires reddish-brown circular/oval spots or orange halo necrosis
        return (brown_ratio >= 0.022 or (brown_ratio >= 0.014 and orange_ratio >= 0.010) or orange_ratio >= 0.030)
        
    elif disease_name == "Blast":
        # Blast requires necrotic lesions with grayish centers and brown borders
        return (gray_ratio >= 0.003 and (brown_ratio >= 0.012 or straw_white_ratio >= 0.018))
        
    elif disease_name in ("Leaf Streak", "Leaf Strip"):
        # Leaf Streak requires narrow linear interveinal streaks
        return (num_streaks >= 6 and max_streak_ar >= 6.0)

    return False


def assign_hotspots_to_candidates(hotspots, primary_disease, visual_matches, diag_explanations, tex_metrics=None):
    """
    Enriches each lesion hotspot with disease-specific attribution.
    Only secondary candidate diseases that have genuine, verified physical evidence
    on the leaf can receive a pinpoint in the Diagnostic Visualization.
    If a secondary candidate has NO visual evidence on the leaf, it is rejected
    and receives NO pinpoint.
    """
    if not hotspots or not primary_disease or primary_disease == "Healthy":
        return []

    # Find secondary candidate diseases with meaningful probability (>= 15%)
    # that PASS physical visual evidence validation on this leaf
    secondary_candidates = []
    if visual_matches and len(hotspots) > 1:
        for m in visual_matches:
            name = m.get("name")
            try:
                sim = float(m.get("similarity", 0))
            except (ValueError, TypeError):
                sim = 0.0
            if name and name != primary_disease and name != "Healthy" and sim >= 0.15 and name in diag_explanations:
                # Strictly require physical visual evidence for this disease on the leaf
                if tex_metrics is None or has_visual_evidence_for_disease(name, tex_metrics):
                    secondary_candidates.append({
                        "name": name,
                        "sim": sim,
                        "prob_pct": int(round(sim * 100))
                    })

    primary_info = diag_explanations.get(primary_disease, {})
    primary_colors = primary_info.get("color_hex", ["#ef4444", "#dc2626"])

    # If there are no secondary candidates, all hotspots represent the primary diagnosis
    if not secondary_candidates:
        for h in hotspots:
            h.update({
                "disease": primary_disease,
                "disease_tl": primary_info.get("name_tl", primary_disease),
                "probability": "Primary Diagnosis",
                "is_primary": True,
                "lesion_color": primary_info.get("lesion_color", ""),
                "color_hex": primary_colors,
                "pin_color": primary_colors[0],
                "why": primary_info.get("why_detected", ""),
                "symptom": primary_info.get("symptom", "")
            })
        return hotspots

    # Assign secondary candidate(s) to smaller/subsequent lesion hotspots
    num_spots = len(hotspots)
    assigned_secondary = {} # index -> candidate dict

    for cand in secondary_candidates:
        available_indices = [i for i in range(num_spots) if i not in assigned_secondary]
        # Keep index 0 for the primary disease's largest lesion
        if len(available_indices) > 1:
            target_idx = available_indices[-1] # pick a secondary spot
        elif available_indices:
            target_idx = available_indices[0]
        else:
            break
        assigned_secondary[target_idx] = cand

    for idx, h in enumerate(hotspots):
        if idx in assigned_secondary:
            cand = assigned_secondary[idx]
            c_name = cand["name"]
            c_info = diag_explanations.get(c_name, {})
            c_colors = c_info.get("color_hex", ["#78350f", "#ca8a04"])
            h.update({
                "disease": c_name,
                "disease_tl": c_info.get("name_tl", c_name),
                "probability": f"{cand['prob_pct']}% Probability Consideration",
                "is_primary": False,
                "lesion_color": c_info.get("lesion_color", ""),
                "color_hex": c_colors,
                "pin_color": c_colors[0],
                "why": f"Evaluated by model with {cand['prob_pct']}% probability as a potential {c_name} lesion.",
                "symptom": c_info.get("symptom", "")
            })
        else:
            h.update({
                "disease": primary_disease,
                "disease_tl": primary_info.get("name_tl", primary_disease),
                "probability": "Primary Diagnosis",
                "is_primary": True,
                "lesion_color": primary_info.get("lesion_color", ""),
                "color_hex": primary_colors,
                "pin_color": primary_colors[0],
                "why": primary_info.get("why_detected", ""),
                "symptom": primary_info.get("symptom", "")
            })

    return hotspots


def analyze_rice_health(img, weather_condition="hot"):
    """
    Main image processing pipeline:
    1. Color Analysis (HSV thresholding) - determines base health score.
    2. Highlighting - marks infected regions in red (Diagnostic Visualization).
    3. Weather Tuning - adjusts model sensitivity boundaries based on ambient heat.
    4. Deep Learning Classifier (dl_analysis.py) - runs MobileNetV2 identification.
    5. Heuristics & Sim matching - resolves edge cases and queries databases.
    """
    # 7.1 Run HSV color thresholding
    health_score, healthy_mask, unhealthy_mask, stage, bad_background = analyze_color(img)
    lesion_hotspots = extract_lesion_hotspots(unhealthy_mask)
    
    # Check for background validation failure immediately
    if bad_background:
        if bad_background == "complex":
            message = "The leaf shape appears too complex, spiky, or scattered (like a weed flower or whole plant). Please take a clear, focused close-up of a single smooth rice leaf."
        else:
            message = f"The background of your image is too {bad_background}. Please take a picture of the leaf with a clear, contrasting background (avoiding too much {bad_background} color) for accurate analysis."
            
        return {
            "is_valid": False,
            "message": message
        }
    
    # Draw red highlight overlays on infected leaf pixels
    overlay = img.copy()
    overlay[unhealthy_mask > 0] = [0, 0, 255] # BGR color format: Red
    highlighted = cv2.addWeighted(img, 0.6, overlay, 0.4, 0)
    
    # Encode highlighted image into Base64 format for browser display (compressed JPEG to keep payload small)
    _, buffer = cv2.imencode('.jpg', highlighted, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
    highlighted_image_uri = f"data:image/jpeg;base64,{base64.b64encode(buffer).decode('utf-8')}"

    # 7.2 Weather Sensitivity tuning
    # Cold temperatures reduce crop metabolism, lowering thresholds. Hot/Dry climates alter patterns.
    if weather_condition == "cold":
        health_threshold = 0.1
        texture_diseases, tex_metrics = analyze_texture(img, sensitivity=1.2, return_metrics=True)
    else:
        health_threshold = 0.7
        texture_diseases, tex_metrics = analyze_texture(img, sensitivity=1.0, return_metrics=True)

    brown_ratio = tex_metrics['brown_ratio']
    gray_ratio  = tex_metrics['gray_ratio']
    straw_ratio = tex_metrics['straw_ratio']
    white_ratio = tex_metrics['white_ratio']

    # 7.3 Deep Learning Identification (MobileNetV2)
    from dl_analysis import analyze_with_dl
    dl_disease, dl_confidence, dl_all_preds = analyze_with_dl(img, return_all_preds=True)
    if dl_disease == "Leaf Strip":
        dl_disease = "Leaf Streak"
    if "Leaf Strip" in dl_all_preds:
        dl_all_preds["Leaf Streak"] = dl_all_preds.pop("Leaf Strip")

    SUPPORTED_DISEASES = ["Blight", "Blast", "Brown Spot", "Leaf Streak", "Leaf Strip", "Healthy"]
    if dl_disease and dl_disease not in SUPPORTED_DISEASES:
        dl_disease = None

    # Deep Learning Model (MobileNetV2) provides primary diagnosis across supported classes

    # PHASE 1: Image Validation (Out of distribution check)
    # Only reject if BOTH deep learning confidence is extremely low AND visual similarity is below 0.15
    if dl_confidence < 0.25:
        raw_visual_matches = image_comparator.get_matching_diseases(img, threshold=0.0, max_matches=1)
        top_visual_score = raw_visual_matches[0][1] if raw_visual_matches else 0.0
        
        if top_visual_score < 0.15:
            return {
                "is_valid": False,
                "message": "This image does not appear to be a clear rice leaf. Please upload a clear, focused picture of a rice leaf for accurate analysis."
            }

    # Resolve visual matches and merge heuristics
    visual_matches = image_comparator.get_matching_diseases(img, threshold=0.30, max_matches=3)
    visual_matches = [(d, s) for d, s in visual_matches if d in SUPPORTED_DISEASES]
    top_visual_disease = visual_matches[0][0] if visual_matches else None
    top_visual_score = visual_matches[0][1] if visual_matches else 0.0

    confirmed_diseases = []
    possible_diseases = []
    visual_matches_formatted = []

    # Detect interveinal streak morphometry for Bacterial Leaf Streak (Leaf Streak)
    num_streaks, max_streak_ar = detect_leaf_streaks(img)

    # Check for Bacterial Leaf Streak
    # MobileNetV2 has < 100 clump photos for Leaf Streak and zero single-leaf macro training shots,
    # causing it to misclassify close-up Leaf Streak as Blight, Blast, or Healthy.
    is_leaf_streak = False
    # Only consider disease overrides if the leaf is NOT overwhelmingly confirmed healthy by DL, color, and lack of necrosis
    straw_white_ratio = straw_ratio + white_ratio
    is_confidently_healthy = (dl_disease == "Healthy" and dl_confidence >= 0.70 and health_score >= 0.85 and straw_white_ratio < 0.02 and brown_ratio < 0.02)

    leaf_streak_sim = next((s for d, s in visual_matches if d in ("Leaf Streak", "Leaf Strip")), 0.0)
    if not is_confidently_healthy:
        if top_visual_disease in ("Leaf Streak", "Leaf Strip") and top_visual_score >= 0.75:
            if dl_disease == "Blast" and dl_confidence >= 0.90:
                if num_streaks >= 10 or max_streak_ar >= 16.0:
                    is_leaf_streak = True
            else:
                is_leaf_streak = True
        elif leaf_streak_sim >= 0.75 and dl_disease == "Blight":
            is_leaf_streak = True
        elif num_streaks >= 12 and max_streak_ar >= 10.0:
            # Interveinal linear streaks between veins (neither Blight nor Brown Spot forms > 10 narrow streaks)
            if not (dl_disease == top_visual_disease and dl_confidence >= 0.60):
                is_leaf_streak = True

    # Check for Bacterial Leaf Blight (Blight) cross-validation safeguard:
    # DL often misclassifies images with panicles/screens or whole clumps as Brown Spot,
    # even when the leaf exhibits continuous longitudinal straw/bleached blighted bands and the 13,480-image dataset comparator identifies Blight as #1!
    is_blight = False
    blight_sim = next((s for d, s in visual_matches if d == "Blight"), 0.0)

    if not is_leaf_streak and not is_confidently_healthy and not (dl_disease == "Blast" and dl_confidence >= 0.60):
        if top_visual_disease == "Blight" and top_visual_score >= 0.78:
            if straw_white_ratio >= 0.035 or (straw_white_ratio >= 0.025 and max_streak_ar >= 3.5) or ("Blight" in texture_diseases and straw_white_ratio >= 0.02):
                is_blight = True
        elif blight_sim >= 0.82 and straw_white_ratio >= 0.04 and max_streak_ar >= 3.5:
            if dl_disease == "Brown Spot":
                is_blight = True
        elif "Blight" in texture_diseases and blight_sim >= 0.75 and straw_white_ratio >= 0.03 and dl_disease != top_visual_disease:
            is_blight = True

    if is_leaf_streak:
        confirmed_diseases.append("Leaf Streak")
        possible_diseases.append("Leaf Streak")
        conf_score = max(leaf_streak_sim if leaf_streak_sim >= 0.70 else 0.88, 0.85)
        visual_matches_formatted.append({"name": "Leaf Streak", "similarity": f"{conf_score:.2f}"})
        if dl_disease and dl_disease not in ("Leaf Streak", "Leaf Strip", "Healthy"):
            visual_matches_formatted.append({"name": dl_disease, "similarity": f"{dl_confidence:.2f}"})
            if dl_confidence >= 0.40 and dl_disease not in possible_diseases:
                possible_diseases.append(dl_disease)
    elif is_blight:
        confirmed_diseases.append("Blight")
        possible_diseases.append("Blight")
        conf_score = max(blight_sim if blight_sim >= 0.75 else 0.88, 0.86)
        visual_matches_formatted.append({"name": "Blight", "similarity": f"{conf_score:.2f}"})
        if dl_disease and dl_disease != "Blight" and dl_disease != "Healthy":
            if has_visual_evidence_for_disease(dl_disease, tex_metrics):
                visual_matches_formatted.append({"name": dl_disease, "similarity": f"{min(dl_confidence, 0.35):.2f}"})
                if dl_confidence >= 0.50 and dl_disease not in possible_diseases:
                    possible_diseases.append(dl_disease)
    # 1. High Confidence Deep Learning: Decisive diagnosis without confusing fingerprint noise
    elif dl_disease and dl_confidence >= 0.65:
        # Safeguard: If DL guessed Brown Spot, but leaf has elongated bleached stripes with high Blight dataset similarity:
        if dl_disease == "Brown Spot" and top_visual_disease == "Blight" and top_visual_score >= 0.78 and straw_white_ratio >= 0.035:
            confirmed_diseases.append("Blight")
            possible_diseases.append("Blight")
            visual_matches_formatted.append({"name": "Blight", "similarity": f"{top_visual_score:.2f}"})
            if has_visual_evidence_for_disease("Brown Spot", tex_metrics):
                visual_matches_formatted.append({"name": "Brown Spot", "similarity": f"{min(dl_confidence, 0.35):.2f}"})
        else:
            confirmed_diseases.append(dl_disease)
            possible_diseases.append(dl_disease)
            visual_matches_formatted.append({"name": dl_disease, "similarity": f"{dl_confidence:.2f}"})
            # Add secondary candidate only if DL itself detected a substantial second probability (> 20%)
            for name, conf in sorted(dl_all_preds.items(), key=lambda x: x[1], reverse=True):
                if name != dl_disease and name in SUPPORTED_DISEASES and conf >= 0.20 and name != "Healthy":
                    if has_visual_evidence_for_disease(name, tex_metrics):
                        visual_matches_formatted.append({"name": name, "similarity": f"{conf:.2f}"})
                        if name not in possible_diseases:
                            possible_diseases.append(name)
    elif dl_disease and dl_confidence >= 0.40:
        # Moderate confidence: cross-reference with top fingerprint match
        if dl_disease == "Brown Spot" and top_visual_disease == "Blight" and top_visual_score >= 0.75 and straw_white_ratio >= 0.035:
            confirmed_diseases.append("Blight")
            possible_diseases.append("Blight")
            visual_matches_formatted.append({"name": "Blight", "similarity": f"{top_visual_score:.2f}"})
            if has_visual_evidence_for_disease("Brown Spot", tex_metrics):
                visual_matches_formatted.append({"name": "Brown Spot", "similarity": f"{min(dl_confidence, 0.35):.2f}"})
        elif dl_disease == top_visual_disease:
            confirmed_diseases.append(dl_disease)
            possible_diseases.append(dl_disease)
            visual_matches_formatted.append({"name": dl_disease, "similarity": f"{dl_confidence:.2f}"})
        elif top_visual_disease and top_visual_score >= 0.60:
            confirmed_diseases.append(top_visual_disease)
            possible_diseases.append(top_visual_disease)
            if dl_disease not in possible_diseases:
                possible_diseases.append(dl_disease)
            visual_matches_formatted.append({"name": top_visual_disease, "similarity": f"{top_visual_score:.2f}"})
            if has_visual_evidence_for_disease(dl_disease, tex_metrics):
                visual_matches_formatted.append({"name": dl_disease, "similarity": f"{dl_confidence:.2f}"})
        elif dl_confidence >= 0.50:
            confirmed_diseases.append(dl_disease)
            possible_diseases.append(dl_disease)
            visual_matches_formatted.append({"name": dl_disease, "similarity": f"{dl_confidence:.2f}"})
        else:
            possible_diseases.append(dl_disease)
            if top_visual_disease and top_visual_disease not in possible_diseases:
                possible_diseases.append(top_visual_disease)
            visual_matches_formatted.append({"name": dl_disease, "similarity": f"{dl_confidence:.2f}"})
                
        # Use DL model probabilities for secondary candidates so all match percentages use the exact same scale
        for name, conf in sorted(dl_all_preds.items(), key=lambda x: x[1], reverse=True):
            if name != dl_disease and name in SUPPORTED_DISEASES and conf >= 0.15 and name != "Healthy":
                if has_visual_evidence_for_disease(name, tex_metrics):
                    if not any(m["name"] == name for m in visual_matches_formatted):
                        visual_matches_formatted.append({"name": name, "similarity": f"{conf:.2f}"})
                    if name not in possible_diseases and conf >= 0.25:
                        possible_diseases.append(name)
    elif top_visual_disease and top_visual_score >= 0.45:
        # Fallback to visual fingerprints if DL is uncertain
        possible_diseases.append(top_visual_disease)
        if top_visual_score >= 0.60:
            confirmed_diseases.append(top_visual_disease)
        for name, score in visual_matches:
            if name == top_visual_disease or has_visual_evidence_for_disease(name, tex_metrics):
                visual_matches_formatted.append({"name": name, "similarity": f"{score:.2f}"})

    # Filter according to weather context
    possible_diseases = filter_diseases_by_weather(possible_diseases, weather_condition)
    confirmed_diseases = [d for d in confirmed_diseases if d in possible_diseases]

    # "Healthy" is a classification but not a disease. Handle it to prevent marking healthy scans as diseased.
    if "Healthy" in confirmed_diseases:
        confirmed_diseases.remove("Healthy")
        is_healthy = True
    elif "Healthy" in possible_diseases:
        possible_diseases.remove("Healthy")
        is_healthy = not possible_diseases
    else:
        is_healthy = health_score > health_threshold and not possible_diseases
    
    # 7.4 Compile Treatment Advice
    all_advice = []
    if possible_diseases:
        for disease in possible_diseases:
            for advice in get_advice(disease):
                if advice not in all_advice:
                    all_advice.append(advice)
    else:
        all_advice = ["Keep current practices"]

    weather_context = "Hot weather" if weather_condition == "hot" else "Cold weather"
    
    # Create text messages for the report
    if is_healthy:
        message = f"Healthy rice! (Analysis optimized for {weather_context.lower()} conditions during the {stage} stage)"
    elif confirmed_diseases:
        message = f"Confirmed disease(s): {', '.join(confirmed_diseases)} (detected in {weather_context.lower()} conditions during the {stage} stage)"
    elif possible_diseases:
        message = f"Possible disease(s): {', '.join(possible_diseases)} (likely in {weather_context.lower()} conditions during the {stage} stage)"
    else:
        message = f"Unhealthy rice detected, but no specific disease identified for {weather_context.lower()} conditions during the {stage} stage"

    primary_disease = confirmed_diseases[0] if confirmed_diseases else possible_diseases[0] if possible_diseases else "Healthy"
    infected_area_pct = round(max(0.0, (1.0 - health_score) * 100), 1)

    # Categorical Health and Infection Status
    health_status = "Healthy" if is_healthy or primary_disease == "Healthy" else "Not Healthy"
    infection_level = "None" if is_healthy else ("High" if infected_area_pct > 15.0 else "Low")

    diag_info = DISEASE_DIAGNOSTIC_EXPLANATIONS.get(primary_disease, DISEASE_DIAGNOSTIC_EXPLANATIONS.get("Healthy", {}))

    # Enrich lesion hotspots with disease-specific attribution & secondary candidate pinpoints
    enriched_hotspots = assign_hotspots_to_candidates(
        lesion_hotspots,
        primary_disease,
        visual_matches_formatted,
        DISEASE_DIAGNOSTIC_EXPLANATIONS,
        tex_metrics
    ) if not is_healthy else []

    # STRICT HARMONIZATION WITH DIAGNOSTIC VISUALIZATION:
    # If a secondary disease does NOT have an active pinpoint in the Diagnostic Visualization,
    # it is rejected (meaning its probability is invalid) and MUST NOT appear in visual_matches
    # (Secondary Model Considerations) or possible_diseases!
    pinpointed_diseases = set(h["disease"] for h in enriched_hotspots if h.get("disease")) if enriched_hotspots else {primary_disease}
    visual_matches_formatted = [
        m for m in visual_matches_formatted 
        if m["name"] == primary_disease or m["name"] in pinpointed_diseases
    ]
    possible_diseases = [
        d for d in possible_diseases 
        if d == primary_disease or d in pinpointed_diseases
    ]
    confirmed_diseases = [
        d for d in confirmed_diseases 
        if d == primary_disease or d in pinpointed_diseases
    ]

    return {
        "health_score":       float(health_score),
        "health_status":      health_status,
        "infection_level":    infection_level,
        "infected_area_pct":  float(infected_area_pct) if not is_healthy else 0.0,
        "is_healthy":         is_healthy,
        "primary_disease":    primary_disease,
        "primary_disease_tl": diag_info.get("name_tl", primary_disease),
        "disease_symptom":    diag_info.get("symptom", ""),
        "disease_symptom_tl": diag_info.get("symptom_tl", ""),
        "why_detected":       diag_info.get("why_detected", ""),
        "lesion_color":       diag_info.get("lesion_color", ""),
        "lesion_color_tl":    diag_info.get("lesion_color_tl", ""),
        "color_hex":          diag_info.get("color_hex", ["#ef4444"]),
        "reference_image_url": f"/reference-image/{primary_disease}" if not is_healthy and primary_disease != "Healthy" else None,
        "lesion_hotspots":    enriched_hotspots,
        "diseases":           possible_diseases if possible_diseases else None,
        "confirmed_diseases": confirmed_diseases if confirmed_diseases else None,
        "visual_matches":     visual_matches_formatted if visual_matches_formatted else None,
        "message":            message,
        "message_tl":         get_tagalog_translation(primary_disease, stage, weather_condition),
        "advice":             all_advice,
        "advice_tl":          get_tagalog_advice(primary_disease) if primary_disease != "Healthy" else [],
        "weather_condition":  weather_condition,
        "weather_context":    weather_context,
        "stage":              stage,
        "highlighted_image":  highlighted_image_uri,
    }


# --- 8. PHOTO UPLOAD ROUTING ---

@app.route("/upload", methods=["POST"])
@require_auth
def upload():
    """
    Accepts leaf scan image file payloads.
    Saves image, executes analysis pipeline, and logs transaction details into MariaDB.
    """
    if "image" not in request.files:
        return jsonify({"error": "No image uploaded"}), 400

    file              = request.files["image"]
    img_data          = file.read()
    weather_condition = request.form.get("weather", "hot")
    current_user      = request.current_user

    # Generate a unique hash filename to prevent filename collision issues
    ext           = os.path.splitext(file.filename)[1] or '.jpg'
    unique_name   = f"{uuid.uuid4().hex}{ext}"
    save_path     = os.path.join(uploads_dir, unique_name)
    with open(save_path, 'wb') as f:
        f.write(img_data)

    img = cv2.imdecode(np.frombuffer(img_data, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return jsonify({"error": "Could not process image"}), 400

    # Downscale high-resolution images
    max_dim = 1024
    h, w = img.shape[:2]
    if max(h, w) > max_dim:
        scale = max_dim / max(h, w)
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

    # Run analysis
    result = analyze_rice_health(img, weather_condition)
    
    # Check if Phase 1 validation failed
    if result.get("is_valid") is False:
        return jsonify(result)

    # Persist highlighted image to disk for historical audit retrieval
    try:
        hl_data_str = result.get('highlighted_image', '')
        if hl_data_str and ',' in hl_data_str:
            hl_b64 = hl_data_str.split(',', 1)[1]
            hl_bytes = base64.b64decode(hl_b64)
            hl_path = os.path.join(uploads_dir, f"highlighted_{unique_name}")
            with open(hl_path, 'wb') as f_hl:
                f_hl.write(hl_bytes)
    except Exception as e_hl:
        print(f"Failed to persist highlighted image: {e_hl}")

    # Save details to scan_records table
    diseases_list = result.get('confirmed_diseases') or result.get('diseases') or []
    scan_id = save_scan_record(
        user_id           = current_user['id'],
        image_filename    = unique_name,
        detected_diseases = diseases_list if diseases_list else ['Healthy'],
        health_score      = result['health_score'],
        is_healthy        = result['is_healthy'],
        weather_condition = weather_condition,
        growth_stage      = result.get('stage', 'Unknown'),
        advice            = result.get('advice', [])
    )

    # Audit log scan event
    log_audit("LEAF_SCAN", f"Scan #{scan_id}: {result.get('primary_disease')} ({result.get('health_status')}) in {current_user.get('barangay', 'Bacnotan')}",
              user_id=current_user.get('id'), username=current_user.get('username'),
              role=current_user.get('role'), ip_address=request.remote_addr)

    result['scan_id']   = scan_id
    result['user_name'] = current_user['full_name']
    return jsonify(result)


# --- 9. AI HEALING GRAPHICS INPAINTING ROUTE ---

@app.route("/ai-heal", methods=["POST"])
@require_auth
def ai_heal():
    """
    Applies image processing algorithms (Inpainting + Color balancing) to simulate
    a fully healed and healthy green version of an infected leaf.
    Uses Telea's inpainting algorithm to remove visual blemishes and spots.
    """
    if "image" not in request.files:
        return jsonify({"error": "No image uploaded"}), 400
    file     = request.files["image"]
    img_data = file.read()
    img      = cv2.imdecode(np.frombuffer(img_data, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return jsonify({"error": "Could not process image"}), 400

    max_dim = 1024
    h, w = img.shape[:2]
    if max(h, w) > max_dim:
        scale = max_dim / max(h, w)
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

    # Locate yellow/brown spots and red highlight spots
    _, _, unhealthy_mask, _, _ = analyze_color(img)
    red_highlight_mask      = cv2.inRange(img, (0, 0, 200), (80, 80, 255))
    unhealthy_mask          = cv2.bitwise_or(unhealthy_mask, red_highlight_mask)
    
    # Inpaint: Reconstruct damaged pixels using surrounding healthy green leaf pixels
    healed                  = cv2.inpaint(img, unhealthy_mask, 3, cv2.INPAINT_TELEA)
    
    # Shift HSV hues back to bright agricultural green
    hsv                     = cv2.cvtColor(healed, cv2.COLOR_BGR2HSV)
    full_leaf_mask          = cv2.bitwise_or(cv2.inRange(hsv, (0, 0, 40), (180, 255, 255)), unhealthy_mask)
    hsv[full_leaf_mask > 0, 0] = 65 # Set green hue angle
    hsv[full_leaf_mask > 0, 1] = np.clip(hsv[full_leaf_mask > 0, 1] * 1.6, 0, 255) # Saturated green color balance
    
    # Brighten value channel
    hsv_f                   = hsv.astype("float32")
    hsv_f[:,:,2]            = np.clip(hsv_f[:,:,2] * 1.1, 0, 255)
    healed                  = cv2.cvtColor(hsv_f.astype("uint8"), cv2.COLOR_HSV2BGR)
    healed                  = cv2.GaussianBlur(healed, (3,3), 0) # Smooth out transitions
    
    _, buffer               = cv2.imencode('.jpg', healed, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
    healed_image_uri        = f"data:image/jpeg;base64,{base64.b64encode(buffer).decode('utf-8')}"
    return jsonify({"healed_image": healed_image_uri})


# --- 10. SECURE ADMIN ROUTINGS ---

@app.route("/admin/stats", methods=["GET"])
@require_admin
def admin_stats():
    """Aggregates metrics for the admin dashboard dashboard metrics."""
    return jsonify(get_dashboard_stats())

@app.route("/admin/records", methods=["GET"])
@require_admin
def admin_records():
    """Lists the full history of rice scan events."""
    return jsonify(get_all_scan_records())

@app.route("/admin/records/<int:scan_id>", methods=["GET"])
@require_admin
def admin_get_record(scan_id):
    """Returns single scan record with full image and diagnosis advice details."""
    record = get_scan_record_by_id(scan_id)
    if not record:
        return jsonify({"error": f"Scan #{scan_id} not found"}), 404
    return jsonify(record)

@app.route("/records/<int:scan_id>", methods=["GET"])
@require_auth
def get_record(scan_id):
    """Returns single scan record with full image and diagnosis advice details for scanner page view."""
    record = get_scan_record_by_id(scan_id)
    if not record:
        return jsonify({"error": f"Scan #{scan_id} not found"}), 404
    return jsonify(record)


@app.route("/admin/users", methods=["GET"])
@require_admin
def admin_users():
    """Lists all user accounts registered in the database."""
    return jsonify(get_all_users())

@app.route("/admin/users/<int:user_id>", methods=["DELETE"])
@require_admin
def admin_delete_user(user_id):
    """Deletes a user account. Security rule: Admins cannot be deleted."""
    if request.current_user.get('role') != 'admin':
        return jsonify({"error": "Only the System Administrator can delete users."}), 403
    success = delete_user_by_id(user_id)
    if success:
        log_audit("USER_DELETE", f"Deleted user account ID #{user_id}",
                  user_id=request.current_user.get('id'), username=request.current_user.get('username'),
                  role=request.current_user.get('role'), ip_address=request.remote_addr)
        return jsonify({"message": "User deleted successfully."})
    return jsonify({"error": "Cannot delete this user (admin or not found)."}), 400

@app.route("/admin/users/<int:user_id>/admit", methods=["POST"])
@require_admin
def admin_admit_staff(user_id):
    """Admit a user as MAO Staff (admin only). Sets role to staff and staff_status to approved."""
    if request.current_user.get('role') != 'admin':
        return jsonify({"error": "Only the System Administrator can admit MAO Staff."}), 403
    success = admit_staff_user(user_id)
    if success:
        log_audit("STAFF_ADMIT", f"Admitted user ID #{user_id} as approved MAO Staff",
                  user_id=request.current_user.get('id'), username=request.current_user.get('username'),
                  role=request.current_user.get('role'), ip_address=request.remote_addr)
        return jsonify({"message": "User admitted as MAO Staff successfully!"})
    return jsonify({"error": "Failed to admit user."}), 400

@app.route("/admin/users/<int:user_id>/reject", methods=["POST"])
@require_admin
def admin_reject_staff(user_id):
    """Reject a MAO Staff request. Automatically sets user to Farmer role (admin only)."""
    if request.current_user.get('role') != 'admin':
        return jsonify({"error": "Only the System Administrator can reject MAO Staff."}), 403
    success = reject_staff_user(user_id)
    if success:
        log_audit("STAFF_REJECT", f"Rejected MAO Staff request for user ID #{user_id}",
                  user_id=request.current_user.get('id'), username=request.current_user.get('username'),
                  role=request.current_user.get('role'), ip_address=request.remote_addr)
        return jsonify({"message": "MAO Staff request rejected. User is now listed as a Farmer."})
    return jsonify({"error": "Failed to reject user."}), 400


# --- 11. ADMIN DISEASE ADVICE MANAGEMENT (CRUD) ---

@app.route("/admin/diseases", methods=["GET"])
@require_admin
def admin_get_diseases():
    """Lists full disease advice database entries."""
    return jsonify(get_all_disease_advice())

@app.route("/admin/diseases", methods=["POST"])
@require_admin
def admin_add_disease():
    """Adds a new advice entry to a disease profile."""
    data = request.get_json()
    disease_name = (data.get('disease_name') or '').strip()
    advice_text  = (data.get('advice') or '').strip()
    if not disease_name or not advice_text:
        return jsonify({"error": "Disease name and advice are required."}), 400
    new_id = add_disease_advice(disease_name, advice_text)
    if new_id:
        log_audit("ADVICE_ADD", f"Added treatment advice #{new_id} for '{disease_name}'",
                  user_id=request.current_user.get('id'), username=request.current_user.get('username'),
                  role=request.current_user.get('role'), ip_address=request.remote_addr)
        return jsonify({"message": "Advice added.", "id": new_id}), 201
    return jsonify({"error": "Failed to add advice."}), 500

@app.route("/admin/diseases/<int:advice_id>", methods=["PUT"])
@require_admin
def admin_update_disease(advice_id):
    """Edits advice statements."""
    data = request.get_json()
    advice_text = (data.get('advice') or '').strip()
    if not advice_text:
        return jsonify({"error": "Advice text is required."}), 400
    success = update_disease_advice(advice_id, advice_text)
    if success:
        log_audit("ADVICE_UPDATE", f"Updated treatment advice #{advice_id}",
                  user_id=request.current_user.get('id'), username=request.current_user.get('username'),
                  role=request.current_user.get('role'), ip_address=request.remote_addr)
        return jsonify({"message": "Advice updated."})
    return jsonify({"error": "Update failed or record not found."}), 400

@app.route("/admin/diseases/<int:advice_id>", methods=["DELETE"])
@require_admin
def admin_delete_disease(advice_id):
    """Deletes an advice entry by ID."""
    success = delete_disease_advice(advice_id)
    if success:
        log_audit("ADVICE_DELETE", f"Deleted treatment advice #{advice_id}",
                  user_id=request.current_user.get('id'), username=request.current_user.get('username'),
                  role=request.current_user.get('role'), ip_address=request.remote_addr)
        return jsonify({"message": "Advice deleted."})
    return jsonify({"error": "Delete failed or record not found."}), 400


# --- 12. BARANGAY DISEASE HEAT MAP ROUTE ---

@app.route("/admin/heatmap-data", methods=["GET"])
@require_admin
def admin_heatmap_data():
    """Returns barangay spatial disease distribution data for Bacnotan."""
    return jsonify(get_barangay_heatmap_data())


# --- 13. AUDIT TRAIL ROUTE ---

@app.route("/admin/audit-logs", methods=["GET"])
@require_admin
def admin_audit_logs():
    """Fetches paginated audit logs with search and action filters."""
    limit = int(request.args.get('limit', 50))
    offset = int(request.args.get('offset', 0))
    action = request.args.get('action', None)
    search = request.args.get('search', None)
    logs = get_audit_logs(limit=limit, offset=offset, action_filter=action, search=search)
    return jsonify(logs)


# --- 14. EXPORT REPORTS (ALL OR BARANGAY-SPECIFIC) ---

import csv
import io
from flask import Response

@app.route("/admin/report/csv", methods=["GET"])
@require_admin
def admin_generate_csv():
    """Generates and downloads a CSV report containing scan logs, optionally filtered by barangay."""
    barangay = request.args.get('barangay')
    records = get_scan_records_for_report(barangay=barangay)
    output  = io.StringIO()
    writer  = csv.writer(output)
    writer.writerow([
        'Scan ID', 'Farmer Name', 'Username', 'Barangay', 'Detected Disease',
        'Health Status', 'Status', 'Weather', 'Growth Stage', 'Treatment Advice', 'Date & Time'
    ])
    for r in records:
        writer.writerow([
            r.get('id'),
            r.get('user_name'),
            r.get('username'),
            r.get('barangay'),
            r.get('detected_diseases'),
            r.get('health_score'),
            r.get('is_healthy'),
            r.get('weather_condition'),
            r.get('growth_stage'),
            r.get('advice'),
            r.get('created_at')
        ])
    csv_data = output.getvalue()
    
    b_suffix = f"_{barangay.strip().replace(' ', '_')}" if barangay and barangay.strip().lower() != 'all' else ""
    filename = f"PALAYSCAN_Report{b_suffix}_{datetime.now().strftime('%Y%m%d')}.csv"
    
    log_audit("REPORT_EXPORT", f"Exported scan CSV report (Location: {barangay or 'All'})",
              user_id=request.current_user.get('id'), username=request.current_user.get('username'),
              role=request.current_user.get('role'), ip_address=request.remote_addr)

    return Response(
        csv_data,
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )

@app.route("/admin/report/barangay-summary", methods=["GET"])
@require_admin
def admin_barangay_summary():
    """Returns focused summary report data for a specific barangay."""
    barangay = request.args.get('barangay')
    if not barangay:
        return jsonify({"error": "Barangay parameter is required"}), 400
    summary = get_barangay_summary(barangay)
    if not summary:
        return jsonify({"error": f"No data found for barangay '{barangay}'"}), 404
    return jsonify(summary)


# --- 15. DATABASE BACKUP & RESTORE ROUTES ---

import zipfile
import json

@app.route("/admin/backup", methods=["GET"])
@require_admin
def admin_backup():
    """
    Creates and downloads a complete self-contained ZIP backup containing:
    1. database_dump.json (all table records)
    2. uploads/ (all leaf scan image files)
    3. metadata.json (timestamp, version, counts)
    """
    try:
        db_dump = export_all_database_records()
        
        memory_zip = io.BytesIO()
        with zipfile.ZipFile(memory_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
            # 1. Database records dump
            zf.writestr('database_dump.json', json.dumps(db_dump, indent=2, ensure_ascii=False))
            
            # 2. Metadata file
            meta = {
                "system": "PALAYSCAN",
                "timestamp": datetime.now().isoformat(),
                "created_by": request.current_user.get('username', 'admin'),
                "user_count": len(db_dump.get("users", [])),
                "scan_count": len(db_dump.get("scan_records", [])),
                "advice_count": len(db_dump.get("disease_advice", []))
            }
            zf.writestr('metadata.json', json.dumps(meta, indent=2))
            
            # 3. Include all uploaded scan images from backend/uploads
            if os.path.exists(uploads_dir):
                for root, dirs, files in os.walk(uploads_dir):
                    for file in files:
                        full_path = os.path.join(root, file)
                        rel_path = os.path.relpath(full_path, uploads_dir)
                        zf.write(full_path, arcname=os.path.join('uploads', rel_path))

        memory_zip.seek(0)
        log_audit("BACKUP_DOWNLOAD", "Generated and downloaded full system backup (Database + Images)",
                  user_id=request.current_user.get('id'), username=request.current_user.get('username'),
                  role=request.current_user.get('role'), ip_address=request.remote_addr)

        backup_name = f"PALAYSCAN_Backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        return Response(
            memory_zip.getvalue(),
            mimetype='application/zip',
            headers={'Content-Disposition': f'attachment; filename={backup_name}'}
        )
    except Exception as e:
        print(f"[Admin Backup Error] {e}", file=sys.stderr)
        return jsonify({"error": f"Failed to generate backup: {e}"}), 500


@app.route("/admin/restore", methods=["POST"])
@require_admin
def admin_restore():
    """
    Restores the system from an uploaded backup ZIP archive:
    1. Validates archive structure
    2. Restores database records into MariaDB
    3. Reconstructs all associated images in backend/uploads/
    """
    if "backup_file" not in request.files:
        return jsonify({"error": "No backup file uploaded"}), 400

    file = request.files["backup_file"]
    if not file.filename.lower().endswith(".zip"):
        return jsonify({"error": "The uploaded file must be a valid .zip archive."}), 400

    try:
        zip_bytes = io.BytesIO(file.read())
        with zipfile.ZipFile(zip_bytes, "r") as zf:
            namelist = zf.namelist()
            if "database_dump.json" not in namelist:
                return jsonify({"error": "Corrupted or invalid backup archive (missing database_dump.json)."}), 400

            # 1. Restore Database Records
            dump_data = json.loads(zf.read("database_dump.json").decode("utf-8"))
            restore_summary = import_database_records(dump_data)

            # 2. Restore Uploaded Images
            os.makedirs(uploads_dir, exist_ok=True)
            restored_images_count = 0
            for name in namelist:
                if name.startswith("uploads/") and not name.endswith("/"):
                    base_filename = os.path.basename(name)
                    if base_filename:
                        target_file_path = os.path.join(uploads_dir, base_filename)
                        with open(target_file_path, "wb") as out_f:
                            out_f.write(zf.read(name))
                        restored_images_count += 1

        log_audit(
            "DATABASE_RESTORE",
            f"Restored system from backup archive: {restore_summary.get('users_restored', 0)} users, "
            f"{restore_summary.get('scans_restored', 0)} scans, {restored_images_count} images",
            user_id=request.current_user.get('id'),
            username=request.current_user.get('username'),
            role=request.current_user.get('role'),
            ip_address=request.remote_addr
        )

        return jsonify({
            "message": "System successfully restored from backup!",
            "users_restored": restore_summary.get("users_restored", 0),
            "scans_restored": restore_summary.get("scans_restored", 0),
            "advice_restored": restore_summary.get("advice_restored", 0),
            "images_restored": restored_images_count
        })

    except Exception as e:
        print(f"[Admin Restore Error] {e}", file=sys.stderr)
        return jsonify({"error": f"Database restoration failed: {e}"}), 500


@app.route("/<path:path>")
def serve_frontend(path):
    """Serves matching frontend assets (images, styles, scripts) when static file exists."""
    full_path = os.path.join(frontend_dir, path)
    if os.path.isfile(full_path):
        return send_from_directory(frontend_dir, path)
    return jsonify({"error": f"Resource '{path}' not found"}), 404


# --- 13. RUN APPLICATION SERVER ---
# Bound to 0.0.0.0 so the server responds on both localhost and external LAN device connections.
if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', threaded=True)