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

# --- Import custom local processing modules ---
from color_analysis import analyze_color       # Detects leaf color thresholds and growth stages
from texture_analysis import analyze_texture   # Evaluates leaf surface textures for disease patterns
from disease_db import (
    get_advice, filter_diseases_by_weather,
    # User Account Auth Functions
    check_email_exists, create_user, verify_password, create_session,
    get_user_by_token, delete_session,
    # Scan Logs
    save_scan_record,
    # Admin Stats & Queries
    get_all_scan_records, get_all_users, delete_user_by_id, get_dashboard_stats,
    admit_staff_user, reject_staff_user,
    # Disease DB CRUD Controls
    get_all_disease_advice, add_disease_advice, update_disease_advice, delete_disease_advice,
    get_scan_records_for_report
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

@app.route("/<path:path>")
def serve_frontend(path):
    """Serves matching frontend assets (images, styles, scripts)."""
    return send_from_directory(frontend_dir, path)

@app.route("/uploads/<path:filename>")
def serve_upload(filename):
    """Serves uploaded leaf photos stored in WAMP backend directory."""
    return send_from_directory(uploads_dir, filename)


# --- 4. SECURE USER ACCOUNT ROUTING (AUTHENTICATION) ---

@app.route("/register", methods=["POST"])
def register():
    """Handles new user registrations. Stores encrypted accounts in MariaDB."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid request."}), 400

    full_name      = (data.get('full_name') or '').strip()
    email          = (data.get('email') or '').strip().lower()
    password       = data.get('password') or ''
    role           = data.get('role') or 'farmer'
    address        = (data.get('address') or '').strip()
    sex            = (data.get('sex') or 'Male').strip()
    try:
        age        = int(data.get('age') or 0)
    except (ValueError, TypeError):
        age        = 0
    barangay       = (data.get('barangay') or '').strip()
    contact_number = (data.get('contact_number') or '').strip()

    # Form field validation
    if not full_name or not email or not password:
        return jsonify({"error": "Full name, email, and password are required."}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters."}), 400
    if role not in ('farmer', 'staff'):
        return jsonify({"error": "Invalid role selected."}), 400
    if check_email_exists(email):
        return jsonify({"error": "This email is already registered."}), 409

    staff_status = 'pending' if role == 'staff' else 'approved'

    # Add account record to users table
    user_id = create_user(full_name, email, password, role, staff_status, address, sex, age, barangay, contact_number)
    if not user_id:
        return jsonify({"error": "Registration failed. Please try again."}), 500

    if role == 'staff':
        msg = "Account created! Since you registered as MAO Staff, your account requires Admin approval before accessing the Admin Panel. You may log in as a Farmer in the meantime."
    else:
        msg = "Account created successfully!"

    return jsonify({"message": msg, "user_id": user_id, "role": role, "staff_status": staff_status}), 201


@app.route("/login", methods=["POST"])
def login():
    """Validates login credentials. Issues a session token if login is successful."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid request."}), 400

    email    = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''

    if not email or not password:
        return jsonify({"error": "Email and password are required."}), 400

    # Cross-reference with database users table
    user = verify_password(email, password)
    if not user:
        return jsonify({"error": "Incorrect email or password."}), 401

    # Issue secure session token stored in user_sessions table
    token = create_session(user['id'])
    if not token:
        return jsonify({"error": "Could not create session. Please try again."}), 500

    return jsonify({
        "token": token,
        "user": {
            "id":           user['id'],
            "full_name":    user['full_name'],
            "email":        user['email'],
            "role":         user['role'],
            "staff_status": user.get('staff_status', 'approved'),
            "address":      user.get('address', ''),
            "sex":          user.get('sex', 'Male'),
            "age":          user.get('age', 0),
            "barangay":     user['barangay']
        }
    })


@app.route("/logout", methods=["POST"])
def logout():
    """Wipes session token from database when logging out."""
    token = get_token_from_request()
    if token:
        delete_session(token)
    return jsonify({"message": "Logged out successfully."})


@app.route("/me", methods=["GET"])
@require_auth
def me():
    """Profile retrieval route to check logged-in status."""
    return jsonify({"user": request.current_user})


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
        "Rust":       "Ang iyong palay ay may sakit na Rust, na nagdudulot ng kalawangin na kulay sa mga dahon.",
        "Leaf Strip": "May Leaf Strip ang palay. Ito ay mga maninipis na guhit sa dahon.",
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


# --- 7. CORE DIAGNOSTIC LOGIC ---

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
    
    # Encode highlighted image into Base64 format for browser display
    _, buffer = cv2.imencode('.jpg', highlighted)
    highlighted_image_uri = f"data:image/jpeg;base64,{base64.b64encode(buffer).decode('utf-8')}"

    # 7.2 Weather Sensitivity tuning
    # Cold temperatures reduce crop metabolism, lowering thresholds. Hot/Dry climates alter patterns.
    if weather_condition == "cold":
        health_threshold       = 0.1
        texture_diseases       = analyze_texture(img, sensitivity=1.2)
        visual_match_threshold = 0.40
    else:
        health_threshold       = 0.7
        texture_diseases       = analyze_texture(img)
        visual_match_threshold = 0.45

    # 7.3 Deep Learning Identification
    from dl_analysis import analyze_with_dl
    dl_disease, dl_confidence = analyze_with_dl(img)

    SUPPORTED_DISEASES = ["Blight", "Blast", "Brown Spot", "Rust", "Leaf Strip", "Healthy"]
    if dl_disease and dl_disease not in SUPPORTED_DISEASES:
        dl_disease = None

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
    if dl_disease and dl_confidence >= 0.75:
        # High confidence deep learning detection
        confirmed_diseases          = [dl_disease]
        possible_diseases           = [dl_disease]
        visual_matches_formatted    = [{"name": dl_disease, "similarity": f"{dl_confidence:.2f}"}]
    else:
        # Fallback to feature comparisons and texture category metrics
        visual_matches  = image_comparator.get_matching_diseases(img, threshold=visual_match_threshold)
        visual_matches  = [(d, s) for d, s in visual_matches if d in SUPPORTED_DISEASES]
        possible_diseases    = texture_diseases.copy()
        visual_match_diseases = [name for name, score in visual_matches]
        
        for disease, _ in visual_matches:
            if disease not in possible_diseases:
                possible_diseases.append(disease)
                
        # Filter matches dynamically according to current weather category
        possible_diseases = filter_diseases_by_weather(possible_diseases, weather_condition)
        confirmed_diseases = []
        
        if visual_matches:
            top_disease, top_score = visual_matches[0]
            if top_score >= 0.60 and filter_diseases_by_weather([top_disease], weather_condition):
                confirmed_diseases.append(top_disease)
                
        for disease in texture_diseases:
            if disease in visual_match_diseases and disease not in confirmed_diseases:
                if filter_diseases_by_weather([disease], weather_condition):
                    confirmed_diseases.append(disease)
                    
        visual_matches_formatted = [
            {"name": name, "similarity": f"{score:.2f}"}
            for name, score in visual_matches
            if filter_diseases_by_weather([name], weather_condition)
        ]

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

    return {
        "health_score":       float(health_score),
        "is_healthy":         is_healthy,
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

    # Run analysis
    result = analyze_rice_health(img, weather_condition)
    
    # Check if Phase 1 validation failed
    if result.get("is_valid") is False:
        return jsonify(result)

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
    
    _, buffer               = cv2.imencode('.jpg', healed)
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
        return jsonify({"message": "Advice updated."})
    return jsonify({"error": "Update failed or record not found."}), 400

@app.route("/admin/diseases/<int:advice_id>", methods=["DELETE"])
@require_admin
def admin_delete_disease(advice_id):
    """Deletes an advice entry by ID."""
    success = delete_disease_advice(advice_id)
    if success:
        return jsonify({"message": "Advice deleted."})
    return jsonify({"error": "Delete failed or record not found."}), 400


# --- 12. EXPORT CSV REPORTS ---

import csv
import io
from flask import Response

@app.route("/admin/report/csv", methods=["GET"])
@require_admin
def admin_generate_csv():
    """Generates and downloads a CSV report containing all scan logs."""
    records = get_scan_records_for_report()
    output  = io.StringIO()
    writer  = csv.DictWriter(output, fieldnames=[
        'id','user_name','email','barangay','detected_diseases',
        'health_score','is_healthy','weather_condition','growth_stage','advice','created_at'
    ])
    writer.writeheader()
    writer.writerows(records)
    csv_data = output.getvalue()
    return Response(
        csv_data,
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=PALAYSCAN_Report.csv'}
    )


# --- 13. RUN APPLICATION SERVER ---
# Bound to 0.0.0.0 so the server responds on both localhost and external LAN device connections.
if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', threaded=True)