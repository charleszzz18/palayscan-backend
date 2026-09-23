# =========================================================================
# PALAYSCAN - DATABASE CONNECTION & QUERY CONTROLLER (disease_db.py)
# =========================================================================
# This module manages all MariaDB communications. It handles database connections,
# checks, data inserts, queries for auth (users, sessions), scans, audit logs,
# heat maps, backups, and admin-level actions. Written with clean error boundaries to prevent
# database exceptions from crashing the Flask app.

import pymysql as mariadb
import sys
import os
import secrets
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash

# --- 1. CONFIGURATION SETTINGS ---
DB_CONFIG = { 
    "host":     "mysql-36584390-dugay684-9775.e.aivencloud.com",
    "user":     "avnadmin",
    "password": "AVNS_6KuybtPDl6mL-ahfFvI",
    "port":         10633,
    "database":     "defaultdb",
    "autocommit":   True,
    "init_command": "SET time_zone = '+08:00'"
}

# Accurate coordinates for all 47 Barangays of Bacnotan, La Union (PhilAtlas / PSA Geographic Data)
BACNOTAN_BARANGAY_COORDS = {
    "Agtipal":          {"lat": 16.7206, "lng": 120.3693},
    "Arosip":           {"lat": 16.7359, "lng": 120.4141},
    "Bacqui":           {"lat": 16.7438, "lng": 120.3812},
    "Bacsil":           {"lat": 16.7135, "lng": 120.3459},
    "Bagutot":          {"lat": 16.7291, "lng": 120.3683},
    "Ballogo":          {"lat": 16.7663, "lng": 120.3453},
    "Baroro":           {"lat": 16.7092, "lng": 120.3419},
    "Bitalag":          {"lat": 16.7502, "lng": 120.3779},
    "Bulala":           {"lat": 16.7310, "lng": 120.3467},
    "Burayoc":          {"lat": 16.7170, "lng": 120.3689},
    "Bussaoit":         {"lat": 16.7119, "lng": 120.3695},
    "Cabaroan":         {"lat": 16.7361, "lng": 120.3639},
    "Cabarsican":       {"lat": 16.7428, "lng": 120.3424},
    "Cabugao":          {"lat": 16.7511, "lng": 120.3654},
    "Calautit":         {"lat": 16.7475, "lng": 120.3891},
    "Carcarmay":        {"lat": 16.7751, "lng": 120.3534},
    "Casiaman":         {"lat": 16.7326, "lng": 120.3835},
    "Galongen":         {"lat": 16.7561, "lng": 120.3391},
    "Guinabang":        {"lat": 16.7575, "lng": 120.3895},
    "Legleg":           {"lat": 16.7032, "lng": 120.3729},
    "Lisqueb":          {"lat": 16.7050, "lng": 120.3652},
    "Mabanengbeng 1st": {"lat": 16.7580, "lng": 120.3556},
    "Mabanengbeng 2nd": {"lat": 16.7599, "lng": 120.3505},
    "Maragayap":        {"lat": 16.7569, "lng": 120.3454},
    "Nagatiran":        {"lat": 16.7755, "lng": 120.3585},
    "Nagsaraboan":      {"lat": 16.7184, "lng": 120.3583},
    "Nagsimbaanan":     {"lat": 16.7190, "lng": 120.3498},
    "Nangalisan":       {"lat": 16.7528, "lng": 120.3537},
    "Narra":            {"lat": 16.7571, "lng": 120.3683},
    "Ortega":           {"lat": 16.7732, "lng": 120.3884},
    "Oya-oy":           {"lat": 16.7719, "lng": 120.3727},
    "Paagan":           {"lat": 16.7901, "lng": 120.3488},
    "Pandan":           {"lat": 16.7325, "lng": 120.3434},
    "Pang-pang":        {"lat": 16.7419, "lng": 120.3725},
    "Poblacion":        {"lat": 16.7213, "lng": 120.3511},
    "Quirino":          {"lat": 16.7641, "lng": 120.3384},
    "Raois":            {"lat": 16.7207, "lng": 120.3547},
    "Salincob":         {"lat": 16.7341, "lng": 120.3779},
    "San Martin":       {"lat": 16.7347, "lng": 120.3581},
    "Santa Cruz":       {"lat": 16.7404, "lng": 120.3454},
    "Santa Rita":       {"lat": 16.7461, "lng": 120.3696},
    "Sapilang":         {"lat": 16.7257, "lng": 120.3856},
    "Sayoan":           {"lat": 16.7356, "lng": 120.3718},
    "Sipulo":           {"lat": 16.7356, "lng": 120.3522},
    "Tammocalao":       {"lat": 16.7496, "lng": 120.3384},
    "Ubbog":            {"lat": 16.7718, "lng": 120.3473},
    "Zaragosa":         {"lat": 16.7077, "lng": 120.3687}
}

_migrated = False

def run_auto_migrations(conn):
    """Safely checks and adds columns/tables for username, dob, audit trail, and relaxed email constraints."""
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'users'", (DB_CONFIG['database'],))
        existing_cols = [row[0].lower() for row in cursor.fetchall()]
        
        if 'address' not in existing_cols:
            cursor.execute("ALTER TABLE users ADD COLUMN address VARCHAR(150) DEFAULT '' AFTER role")
        if 'staff_status' not in existing_cols:
            cursor.execute("ALTER TABLE users ADD COLUMN staff_status VARCHAR(20) DEFAULT 'approved' AFTER role")
        if 'sex' not in existing_cols:
            cursor.execute("ALTER TABLE users ADD COLUMN sex VARCHAR(10) DEFAULT 'Male' AFTER address")
        if 'age' not in existing_cols:
            cursor.execute("ALTER TABLE users ADD COLUMN age INT DEFAULT 0 AFTER sex")
        if 'dob' not in existing_cols:
            cursor.execute("ALTER TABLE users ADD COLUMN dob DATE NULL AFTER age")
        if 'username' not in existing_cols:
            cursor.execute("ALTER TABLE users ADD COLUMN username VARCHAR(50) NULL AFTER full_name")
            cursor.execute("UPDATE users SET username = SUBSTRING_INDEX(email, '@', 1) WHERE username IS NULL OR username = ''")
            cursor.execute("UPDATE users SET username = 'admin' WHERE email = 'admin@palayscan.com'")
            cursor.execute("ALTER TABLE users ADD UNIQUE (username)")
            
        # Ensure email can be nullable
        try:
            cursor.execute("ALTER TABLE users MODIFY COLUMN email VARCHAR(100) NULL")
        except Exception:
            pass

        # Create audit_logs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NULL,
                username VARCHAR(50) DEFAULT 'system',
                role VARCHAR(20) DEFAULT 'system',
                action VARCHAR(100) NOT NULL,
                details TEXT,
                ip_address VARCHAR(45) DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()
    except Exception as e:
        print(f"[DB Migration Note] {e}", file=sys.stderr)

def get_db_connection(): 
    """
    Opens and returns a fresh MariaDB connection.
    Raises a clear error if the connection fails so Flask can handle it gracefully.
    """
    global _migrated
    try: 
        conn = mariadb.connect(**DB_CONFIG) 
        conn.auto_reconnect = True
        try:
            with conn.cursor() as cur:
                cur.execute("SET time_zone = '+08:00'")
        except Exception:
            pass
        if not _migrated:
            run_auto_migrations(conn)
            _migrated = True
        return conn 
    except mariadb.Error as e: 
        print(f"[DB] ERROR: Cannot connect to database — {e}", file=sys.stderr) 
        print(f"[DB] Check: Is WAMP running? Is the password correct? Port={DB_CONFIG['port']}", file=sys.stderr) 
        raise

# --- 2. PUBLIC USER & VISUAL ADVICE RETRIEVAL ---

DEFAULT_ADVICE = {
    "Blast": [
        "Apply Tricyclazole or Isoprothiolane fungicide immediately.",
        "Maintain proper water level and avoid excessive nitrogen fertilizer.",
        "Avoid planting highly susceptible rice varieties in the next season."
    ],
    "Blight": [
        "Apply Copper-based bactericides (e.g., Copper Oxychloride).",
        "Drain the field to reduce humidity and stop bacterial spread.",
        "Avoid applying too much nitrogen fertilizer which softens plant tissues."
    ],
    "Brown Spot": [
        "Apply Mancozeb, Propiconazole, or Edifenphos fungicide.",
        "Ensure proper soil nutrition, specifically Nitrogen, Phosphorus, and Potassium.",
        "Treat seeds with hot water (53-54°C) for 10-12 minutes before planting."
    ],
    "Leaf Streak": [
        "Apply Copper-based bactericides or Streptomycin.",
        "Remove and burn infected leaves to prevent further spread.",
        "Practice crop rotation to break the disease cycle."
    ],
    "Leaf Strip": [
        "Apply Copper-based bactericides or Streptomycin.",
        "Remove and burn infected leaves to prevent further spread.",
        "Practice crop rotation to break the disease cycle."
    ],
    "Healthy": [
        "Walang kailangang gamot. Panatilihin ang regular na patubig at pag-aalaga.",
        "Magpatuloy sa regular na pagsusuri ng palayan upang maagapan ang anumang peste."
    ]
}

def get_advice(disease_name): 
    if not disease_name: 
        return [] 
    if disease_name == "Leaf Strip":
        disease_name = "Leaf Streak"
    try: 
        conn = get_db_connection() 
        cursor = conn.cursor() 
        cursor.execute( 
            "SELECT advice FROM disease_advice WHERE disease_name = %s ORDER BY id", 
            (disease_name,) 
        )
        results = cursor.fetchall() 
        conn.close() 
        if results:
            return [row[0] for row in results]
    except Exception as e: 
        print(f"[DB] get_advice('{disease_name}') failed: {e}", file=sys.stderr) 

    return DEFAULT_ADVICE.get(disease_name, [
        f"Kumonsulta sa inyong lokal na Agriculture Officer para sa tamang gamot laban sa {disease_name}.",
        "Ihiwalay ang mga apektadong halaman upang maiwasan ang pagkalat ng sakit."
    ]) 

def get_diseases_by_weather_from_db(weather_condition): 
    try: 
        conn = get_db_connection() 
        cursor = conn.cursor() 
        cursor.execute( 
            "SELECT DISTINCT disease_name FROM disease_temperature_categories WHERE temperature_category = %s", 
            (weather_condition,) 
        )
        weather_diseases = [row[0] for row in cursor.fetchall()] 
        conn.close() 
        
        seen = set() 
        all_diseases = [] 
        for d in weather_diseases: 
            if d not in seen: 
                seen.add(d) 
                all_diseases.append(d) 
        return all_diseases 
    except Exception as e: 
        print(f"[DB] get_diseases_by_weather_from_db('{weather_condition}') failed: {e}", file=sys.stderr) 
        return None 

def get_diseases_by_weather(weather_condition): 
    return get_diseases_by_weather_from_db(weather_condition) 

def filter_diseases_by_weather(detected_diseases, weather_condition):
    if not detected_diseases:
        return []
    weather_appropriate = get_diseases_by_weather(weather_condition)
    if weather_appropriate is None:
        return detected_diseases
    return [d for d in detected_diseases if d in weather_appropriate]


# --- 3. SECURE AUTHENTICATION QUERIES (USERNAME-BASED) ---

def check_username_exists(username):
    """Checks if a username is already present in the users table."""
    if not username:
        return False
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE LOWER(username) = LOWER(%s)", (username.strip(),))
        result = cursor.fetchone()
        conn.close()
        return result is not None
    except Exception as e:
        print(f"[DB] check_username_exists failed: {e}", file=sys.stderr)
        return False

def check_email_exists(email):
    """Checks if an email is already present in the users table."""
    if not email:
        return False
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE LOWER(email) = LOWER(%s)", (email.strip(),))
        result = cursor.fetchone()
        conn.close()
        return result is not None
    except Exception as e:
        print(f"[DB] check_email_exists failed: {e}", file=sys.stderr)
        return False

def create_user(full_name, username, password, role='farmer', staff_status='approved', address='', sex='Male', age=0, barangay='', contact_number='', email=None, dob=None):
    """
    Creates a new user profile with username, password hash, dob, and calculated age.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        password_hash = generate_password_hash(password)
        if not email:
            email = f"{username.strip().lower()}@palayscan.local"

        cursor.execute(
            """INSERT INTO users (full_name, username, email, password, role, staff_status, address, sex, age, dob, barangay, contact_number)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (full_name.strip(), username.strip().lower(), email.strip().lower(), password_hash, role, staff_status, address.strip(), sex, int(age), dob or None, barangay.strip(), contact_number.strip())
        )
        conn.commit()
        user_id = cursor.lastrowid
        conn.close()
        return user_id
    except Exception as e:
        print(f"[DB] create_user failed: {e}", file=sys.stderr)
        return None

def get_user_by_username_or_email(identifier):
    """Fetches user account row matching a username (primary) or email address (fallback)."""
    if not identifier:
        return None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        identifier_clean = identifier.strip().lower()
        cursor.execute(
            """SELECT id, full_name, username, email, password, role, staff_status, address, sex, age, barangay, contact_number, dob
               FROM users
               WHERE LOWER(username) = %s OR LOWER(email) = %s""",
            (identifier_clean, identifier_clean)
        )
        row = cursor.fetchone()
        conn.close()
        if row:
            raw_u = row[2]
            raw_e = row[3] or ''
            fallback_u = raw_e.split('@')[0] if raw_e else f"user_{row[0]}"
            return {
                'id': row[0],
                'full_name': row[1],
                'username': raw_u or fallback_u,
                'email': raw_e,
                'password': row[4],
                'role': row[5],
                'staff_status': row[6] or 'approved',
                'address': row[7] or '',
                'sex': row[8] or 'Male',
                'age': row[9] or 0,
                'barangay': row[10] or '',
                'contact_number': row[11] or '',
                'dob': str(row[12]) if row[12] else ''
            }
        return None
    except Exception as e:
        print(f"[DB] get_user_by_username_or_email failed: {e}", file=sys.stderr)
        return None

def verify_password(identifier, password):
    """
    Validates password validity.
    Compares the raw login input with the stored cryptographic hash.
    """
    user = get_user_by_username_or_email(identifier)
    if user and check_password_hash(user['password'], password):
        return user
    return None

def verify_user_password_by_id(user_id, password):
    """Checks whether the provided password matches the user's current password hash."""
    if not user_id or not password:
        return False
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT password FROM users WHERE id = %s", (user_id,))
        row = cursor.fetchone()
        conn.close()
        if not row:
            return False
        return check_password_hash(row[0], password)
    except Exception as e:
        print(f"[DB] verify_user_password_by_id error: {e}", file=sys.stderr)
        return False

def update_user_password(user_id, new_password):
    """Hashes and updates user password in MariaDB/MySQL."""
    if not user_id or not new_password:
        return False
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        hashed = generate_password_hash(new_password)
        cursor.execute("UPDATE users SET password = %s WHERE id = %s", (hashed, user_id))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[DB] update_user_password error: {e}", file=sys.stderr)
        return False

def create_session(user_id):
    """Generates a secure hex session token valid for 7 days."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        token = secrets.token_hex(32)
        expires_at = datetime.now() + timedelta(days=7)
        cursor.execute(
            "INSERT INTO user_sessions (user_id, token, expires_at) VALUES (%s, %s, %s)",
            (user_id, token, expires_at)
        )
        conn.commit()
        conn.close()
        return token
    except Exception as e:
        print(f"[DB] create_session failed: {e}", file=sys.stderr)
        return None

def get_user_by_token(token):
    """Validates session token validity and returns active profile."""
    if not token:
        return None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """SELECT u.id, u.full_name, u.username, u.email, u.role, u.staff_status, u.address, u.sex, u.age, u.barangay, u.dob
               FROM users u JOIN user_sessions s ON u.id = s.user_id
               WHERE s.token = %s AND s.expires_at > NOW()""",
            (token,)
        )
        row = cursor.fetchone()
        conn.close()
        if row:
            raw_u = row[2]
            raw_e = row[3] or ''
            fallback_u = raw_e.split('@')[0] if raw_e else f"user_{row[0]}"
            return {
                'id': row[0], 'full_name': row[1], 'username': raw_u or fallback_u,
                'email': raw_e, 'role': row[4], 'staff_status': row[5] or 'approved',
                'address': row[6], 'sex': row[7], 'age': row[8], 'barangay': row[9],
                'dob': str(row[10]) if row[10] else ''
            }
        return None
    except Exception as e:
        print(f"[DB] get_user_by_token failed: {e}", file=sys.stderr)
        return None

def delete_session(token):
    """Deletes a session token from the DB. Used when logging out."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM user_sessions WHERE token = %s", (token,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[DB] delete_session failed: {e}", file=sys.stderr)
        return False


# --- 4. SCAN HISTORICAL RECORD QUERIES ---

def save_scan_record(user_id, image_filename, detected_diseases, health_score, is_healthy, weather_condition, growth_stage, advice):
    """Saves diagnostic outputs to the database."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        diseases_str = ', '.join(detected_diseases) if isinstance(detected_diseases, list) else (detected_diseases or 'Healthy')
        advice_str   = ' | '.join(advice) if isinstance(advice, list) else (advice or '')
        cursor.execute(
            """INSERT INTO scan_records
               (user_id, image_filename, detected_diseases, health_score, is_healthy, weather_condition, growth_stage, advice)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (user_id, image_filename, diseases_str, float(health_score), bool(is_healthy), weather_condition, growth_stage, advice_str)
        )
        conn.commit()
        scan_id = cursor.lastrowid
        conn.close()
        return scan_id
    except Exception as e:
        print(f"[DB] save_scan_record failed: {e}", file=sys.stderr)
        return None


# --- 5. AUDIT TRAIL LOGGING ---

def log_audit(action, details='', user_id=None, username=None, role=None, ip_address=None):
    """Writes an immutable security/system event log to the audit_logs table."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO audit_logs (user_id, username, role, action, details, ip_address)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (user_id, username or 'system', role or 'system', action, str(details or ''), ip_address or '')
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[DB] log_audit failed: {e}", file=sys.stderr)
        return False

def get_audit_logs(limit=100, offset=0, action_filter=None, search=None):
    """Fetches paginated audit logs with search and action filters."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        query = "SELECT id, user_id, username, role, action, details, ip_address, created_at FROM audit_logs"
        params = []
        conditions = []
        if action_filter and action_filter.strip() and action_filter.lower() != 'all':
            conditions.append("action = %s")
            params.append(action_filter.strip())
        if search and search.strip():
            conditions.append("(username LIKE %s OR action LIKE %s OR details LIKE %s OR ip_address LIKE %s)")
            like_s = f"%{search.strip()}%"
            params.extend([like_s, like_s, like_s, like_s])

        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY created_at DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])

        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()

        count_query = "SELECT COUNT(*) FROM audit_logs"
        if conditions:
            count_query += " WHERE " + " AND ".join(conditions)
        cursor.execute(count_query, tuple(params[:-2]))
        total = cursor.fetchone()[0]

        conn.close()
        return {
            "total": total,
            "logs": [{
                "id": r[0], "user_id": r[1], "username": r[2], "role": r[3],
                "action": r[4], "details": r[5], "ip_address": r[6], "created_at": str(r[7])
            } for r in rows]
        }
    except Exception as e:
        print(f"[DB] get_audit_logs failed: {e}", file=sys.stderr)
        return {"total": 0, "logs": []}


# --- 6. BARANGAY DISEASE HEAT MAP & SPATIAL QUERIES ---

def get_barangay_heatmap_data():
    """
    Aggregates scan records by barangay to build the disease distribution heat map.
    Returns array of barangay objects with geographical coordinates, total scans,
    healthy vs diseased, and frequency breakdown per disease.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COALESCE(NULLIF(u.barangay, ''), 'Unknown') as barangay,
                   sr.detected_diseases,
                   sr.is_healthy
            FROM scan_records sr
            LEFT JOIN users u ON sr.user_id = u.id
        """)
        rows = cursor.fetchall()
        conn.close()

        # Initialize full Bacnotan map
        barangay_stats = {}
        for b_name, coords in BACNOTAN_BARANGAY_COORDS.items():
            barangay_stats[b_name] = {
                "barangay": b_name,
                "lat": coords["lat"],
                "lng": coords["lng"],
                "total_scans": 0,
                "healthy_scans": 0,
                "unhealthy_scans": 0,
                "diseases": {
                    "Blight": 0, "Blast": 0, "Brown Spot": 0,
                    "Leaf Streak": 0, "Others": 0
                },
                "most_common_disease": "None"
            }

        for b_raw, d_str, is_healthy in rows:
            b_clean = (b_raw or '').strip()
            # Strictly filter out 'Bacnotan' (municipality name) or unknown/empty
            if not b_clean or b_clean.lower() in ('bacnotan', 'unknown'):
                continue
            matched_key = next((k for k in barangay_stats if k.lower() == b_clean.lower()), None)
            if not matched_key:
                continue

            stat = barangay_stats[matched_key]
            stat["total_scans"] += 1
            if is_healthy:
                stat["healthy_scans"] += 1
            else:
                stat["unhealthy_scans"] += 1
                diseases_found = [d.strip() for d in (d_str or '').split(',') if d.strip() and d.strip() != 'Healthy']
                for d in diseases_found:
                    d_norm = "Leaf Streak" if d == "Leaf Strip" else d
                    if d_norm in stat["diseases"]:
                        stat["diseases"][d_norm] += 1
                    else:
                        stat["diseases"]["Others"] += 1

        for b_name, stat in barangay_stats.items():
            d_counts = stat["diseases"]
            max_d = max(d_counts.items(), key=lambda x: x[1])
            if max_d[1] > 0:
                top_dis = max_d[0]
            elif stat["healthy_scans"] > 0:
                top_dis = "Healthy"
            else:
                top_dis = "None"
            stat["most_common_disease"] = top_dis
            stat["top_disease"] = top_dis
            stat["diseased_scans"] = stat["unhealthy_scans"]
            stat["disease_counts"] = dict(stat["diseases"])

        return list(barangay_stats.values())
    except Exception as e:
        print(f"[DB] get_barangay_heatmap_data failed: {e}", file=sys.stderr)
        return []


# --- 7. ADMINISTRATION CONTROL PANEL CONTROLLERS ---

def get_all_scan_records():
    """Fetches list of all scans in reverse chronological order for administration view."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """SELECT sr.id, u.full_name, COALESCE(u.username, SUBSTRING_INDEX(u.email, '@', 1)) as username,
                      u.email, u.barangay, sr.detected_diseases, sr.health_score, sr.is_healthy,
                      sr.weather_condition, sr.growth_stage, sr.created_at, sr.image_filename, sr.advice
               FROM scan_records sr
               LEFT JOIN users u ON sr.user_id = u.id
               ORDER BY sr.created_at DESC"""
        )
        rows = cursor.fetchall()
        conn.close()
        results = []
        for r in rows:
            raw_score = float(r[6]) if r[6] is not None else 1.0
            infected_pct = round(max(0.0, (1.0 - raw_score) * 100), 1) if not bool(r[7]) else 0.0
            results.append({
                'id': r[0], 'user_name': r[1] or 'Unknown', 'username': r[2] or '',
                'user_email': r[3] or '', 'barangay': r[4] or '', 'detected_diseases': r[5],
                'health_score': 'Healthy' if r[7] else 'Not Healthy',
                'is_healthy': bool(r[7]),
                'infected_area_pct': infected_pct,
                'weather_condition': r[8] or 'Unknown',
                'growth_stage': r[9] or 'Unknown',
                'created_at': str(r[10]),
                'image_filename': r[11] or '',
                'image_url': f"/uploads/{r[11]}" if r[11] else None,
                'advice': [a.strip() for a in (r[12] or '').split('|') if a.strip()]
            })
        return results
    except Exception as e:
        print(f"[DB] get_all_scan_records failed: {e}", file=sys.stderr)
        return []

def get_scan_record_by_id(scan_id):
    """Fetches single scan record with full image and diagnosis advice details."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """SELECT sr.id, u.full_name, COALESCE(u.username, SUBSTRING_INDEX(u.email, '@', 1)) as username,
                      u.email, u.barangay, sr.detected_diseases, sr.health_score, sr.is_healthy,
                      sr.weather_condition, sr.growth_stage, sr.created_at, sr.image_filename, sr.advice
               FROM scan_records sr
               LEFT JOIN users u ON sr.user_id = u.id
               WHERE sr.id = %s""", (scan_id,)
        )
        r = cursor.fetchone()
        conn.close()
        if not r:
            return None

        raw_score = float(r[6]) if r[6] is not None else 1.0
        infected_pct = round(max(0.0, (1.0 - raw_score) * 100), 1) if not bool(r[7]) else 0.0
        advice_raw = r[12] or ''
        advice_list = [a.strip() for a in advice_raw.split('|') if a.strip()]

        # Resolve or generate red-highlighted diagnostic image
        highlighted_url = None
        if r[11]:
            hl_name = f"highlighted_{r[11]}"
            backend_uploads = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
            hl_path = os.path.join(backend_uploads, hl_name)
            raw_path = os.path.join(backend_uploads, r[11])
            if os.path.exists(hl_path):
                highlighted_url = f"/uploads/{hl_name}"
            elif os.path.exists(raw_path):
                try:
                    import cv2
                    from color_analysis import analyze_color
                    img = cv2.imread(raw_path)
                    if img is not None:
                        _, _, um, _, _ = analyze_color(img)
                        over = img.copy()
                        over[um > 0] = [0, 0, 255]
                        hl = cv2.addWeighted(img, 0.6, over, 0.4, 0)
                        cv2.imwrite(hl_path, hl)
                        highlighted_url = f"/uploads/{hl_name}"
                except Exception as hl_err:
                    print(f"[DB] Auto-generate highlighted image failed: {hl_err}", file=sys.stderr)

        return {
            'id': r[0], 'user_name': r[1] or 'Unknown', 'username': r[2] or '',
            'user_email': r[3] or '', 'barangay': r[4] or '', 'detected_diseases': r[5],
            'health_score': 'Healthy' if r[7] else 'Not Healthy',
            'is_healthy': bool(r[7]),
            'infected_area_pct': infected_pct,
            'weather_condition': r[8] or 'Unknown',
            'growth_stage': r[9] or 'Unknown',
            'created_at': str(r[10]),
            'image_filename': r[11] or '',
            'image_url': f"/uploads/{r[11]}" if r[11] else None,
            'highlighted_image_url': highlighted_url or (f"/uploads/{r[11]}" if r[11] else None),
            'advice': advice_list
        }
    except Exception as e:
        print(f"[DB] get_scan_record_by_id failed: {e}", file=sys.stderr)
        return None

def get_all_users():
    """Fetches list of registered users with username, age, and dob for dashboard review."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """SELECT id, full_name, username, email, role, staff_status, address, sex, age, barangay, contact_number, dob, created_at
               FROM users ORDER BY created_at DESC"""
        )
        rows = cursor.fetchall()
        conn.close()
        return [{
            'id': r[0], 'full_name': r[1], 'username': r[2] or (r[3].split('@')[0] if r[3] else f"user_{r[0]}"),
            'email': r[3] or '', 'role': r[4], 'staff_status': r[5] or 'approved',
            'address': r[6] or '', 'sex': r[7] or '—', 'age': r[8] or 0,
            'barangay': r[9] or '', 'contact_number': r[10] or '', 'dob': str(r[11]) if r[11] else '',
            'created_at': str(r[12])
        } for r in rows]
    except Exception as e:
        print(f"[DB] get_all_users failed: {e}", file=sys.stderr)
        return []

def admit_staff_user(user_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET role = 'staff', staff_status = 'approved' WHERE id = %s", (user_id,))
        conn.commit()
        affected = cursor.rowcount
        conn.close()
        return affected > 0
    except Exception as e:
        print(f"[DB] admit_staff_user failed: {e}", file=sys.stderr)
        return False

def reject_staff_user(user_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET role = 'farmer', staff_status = 'rejected' WHERE id = %s", (user_id,))
        conn.commit()
        affected = cursor.rowcount
        conn.close()
        return affected > 0
    except Exception as e:
        print(f"[DB] reject_staff_user failed: {e}", file=sys.stderr)
        return False

def delete_user_by_id(user_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM users WHERE id = %s AND role != 'admin'", (user_id,))
        conn.commit()
        affected = cursor.rowcount
        conn.close()
        return affected > 0
    except Exception as e:
        print(f"[DB] delete_user_by_id failed: {e}", file=sys.stderr)
        return False

def get_dashboard_stats():
    """Calculates summary metrics and demographics for admin charts."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM users WHERE role != 'admin'")
        total_users = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM scan_records")
        total_scans = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM scan_records WHERE is_healthy = 1")
        healthy_scans = cursor.fetchone()[0]
        
        cursor.execute(
            "SELECT detected_diseases, COUNT(*) as cnt FROM scan_records GROUP BY detected_diseases ORDER BY cnt DESC LIMIT 5"
        )
        top_diseases = [{'disease': r[0], 'count': r[1]} for r in cursor.fetchall()]

        cursor.execute("SELECT sex, COUNT(*) FROM users WHERE role != 'admin' GROUP BY sex")
        gender_distribution = [{'sex': r[0] or 'Unknown', 'count': r[1]} for r in cursor.fetchall()]

        cursor.execute("SELECT barangay, COUNT(*) FROM users WHERE role != 'admin' AND barangay != '' GROUP BY barangay ORDER BY COUNT(*) DESC")
        users_per_barangay = [{'barangay': r[0], 'count': r[1]} for r in cursor.fetchall()]

        cursor.execute("""
            SELECT 
                CASE 
                    WHEN dob IS NOT NULL THEN TIMESTAMPDIFF(YEAR, dob, CURDATE())
                    ELSE age
                END AS calculated_age,
                COUNT(*)
            FROM users 
            WHERE role != 'admin' AND (age > 0 OR dob IS NOT NULL)
            GROUP BY calculated_age
            ORDER BY calculated_age ASC
        """)
        age_counts = cursor.fetchall()
        # Precise age demographics: exact age mapped to farmer count (e.g. "19": 1, "21": 2, "31": 7)
        age_demographics = {str(r[0]): int(r[1]) for r in age_counts}

        total_farmers_with_age = sum(r[1] for r in age_counts)
        total_age_sum = sum(r[0] * r[1] for r in age_counts)
        avg_age = round(total_age_sum / total_farmers_with_age, 1) if total_farmers_with_age > 0 else 0

        cursor.execute("SELECT COUNT(*) FROM users WHERE role != 'admin' AND DATE(created_at) = CURDATE()")
        new_users_today = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM scan_records WHERE DATE(created_at) = CURDATE()")
        new_scans_today = cursor.fetchone()[0]

        conn.close()
        
        return {
            'total_users': total_users, 'total_scans': total_scans,
            'new_users_today': new_users_today, 'new_scans_today': new_scans_today,
            'healthy_scans': healthy_scans,
            'diseased_scans': total_scans - healthy_scans,
            'unhealthy_scans': total_scans - healthy_scans,
            'top_diseases': top_diseases,
            'gender_distribution': gender_distribution,
            'users_per_barangay': users_per_barangay,
            'age_demographics': age_demographics,
            'avg_age': avg_age
        }
    except Exception as e:
        print(f"[DB] get_dashboard_stats failed: {e}", file=sys.stderr)
        return {}


# --- 8. DISEASE DATABASE EDITING (CRUD) ---

SUPPORTED_DISEASES = ["Blight", "Blast", "Brown Spot", "Leaf Streak", "Others", "Healthy"]

def get_all_disease_advice():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, disease_name, advice FROM disease_advice ORDER BY disease_name, id")
        rows = cursor.fetchall()
        conn.close()
        return [{'id': r[0], 'disease_name': r[1], 'advice': r[2]} for r in rows]
    except Exception as e:
        print(f"[DB] get_all_disease_advice failed: {e}", file=sys.stderr)
        return []

def add_disease_advice(disease_name, advice_text):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO disease_advice (disease_name, advice) VALUES (%s, %s)",
            (disease_name, advice_text)
        )
        conn.commit()
        new_id = cursor.lastrowid
        conn.close()
        return new_id
    except Exception as e:
        print(f"[DB] add_disease_advice failed: {e}", file=sys.stderr)
        return None

def update_disease_advice(advice_id, advice_text):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE disease_advice SET advice = %s WHERE id = %s",
            (advice_text, advice_id)
        )
        conn.commit()
        affected = cursor.rowcount
        conn.close()
        return affected > 0
    except Exception as e:
        print(f"[DB] update_disease_advice failed: {e}", file=sys.stderr)
        return False

def delete_disease_advice(advice_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM disease_advice WHERE id = %s", (advice_id,))
        conn.commit()
        affected = cursor.rowcount
        conn.close()
        return affected > 0
    except Exception as e:
        print(f"[DB] delete_disease_advice failed: {e}", file=sys.stderr)
        return False


# --- 9. LOCATION & BARANGAY-SPECIFIC REPORTS ---

def get_scan_records_for_report(barangay=None):
    """
    Gathers full details of scans formatted for CSV exports.
    Can be filtered by a specific barangay location.
    Categorical results only (Healthy/Not Healthy).
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        query = """SELECT sr.id, u.full_name, COALESCE(u.username, SUBSTRING_INDEX(u.email, '@', 1)) as username,
                          u.barangay, sr.detected_diseases, sr.is_healthy,
                          sr.weather_condition, sr.growth_stage, sr.advice, sr.created_at
                   FROM scan_records sr
                   LEFT JOIN users u ON sr.user_id = u.id"""
        params = []
        if barangay and barangay.strip() and barangay.strip().lower() != 'all':
            query += " WHERE LOWER(u.barangay) = LOWER(%s)"
            params.append(barangay.strip())
        query += " ORDER BY sr.created_at DESC"

        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()
        conn.close()
        return [{
            'id': r[0],
            'user_name': r[1] or 'Unknown',
            'username': r[2] or '',
            'barangay': r[3] or '',
            'detected_diseases': r[4],
            'health_score': 'Healthy' if r[5] else 'Not Healthy',
            'is_healthy': 'Healthy' if r[5] else 'Not Healthy',
            'weather_condition': r[6],
            'growth_stage': r[7],
            'advice': r[8] or '',
            'created_at': str(r[9])
        } for r in rows]
    except Exception as e:
        print(f"[DB] get_scan_records_for_report failed: {e}", file=sys.stderr)
        return []

def get_barangay_summary(barangay):
    """Calculates focused statistical summary for a specific barangay report."""
    if not barangay or barangay.strip().lower() == 'all':
        return None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        clean_b = barangay.strip()

        cursor.execute("SELECT COUNT(*) FROM users WHERE LOWER(barangay) = LOWER(%s) AND role != 'admin'", (clean_b,))
        total_farmers = cursor.fetchone()[0]

        cursor.execute("""
            SELECT COUNT(*),
                   SUM(CASE WHEN sr.is_healthy = 1 THEN 1 ELSE 0 END),
                   SUM(CASE WHEN sr.is_healthy = 0 THEN 1 ELSE 0 END)
            FROM scan_records sr
            JOIN users u ON sr.user_id = u.id
            WHERE LOWER(u.barangay) = LOWER(%s)
        """, (clean_b,))
        scan_counts = cursor.fetchone()
        total_scans = scan_counts[0] or 0
        healthy_scans = scan_counts[1] or 0
        unhealthy_scans = scan_counts[2] or 0

        cursor.execute("""
            SELECT sr.detected_diseases, COUNT(*) as cnt
            FROM scan_records sr
            JOIN users u ON sr.user_id = u.id
            WHERE LOWER(u.barangay) = LOWER(%s) AND sr.is_healthy = 0
            GROUP BY sr.detected_diseases
            ORDER BY cnt DESC
        """, (clean_b,))
        disease_counts = [{'disease': r[0], 'count': r[1]} for r in cursor.fetchall()]

        cursor.execute("""
            SELECT sr.id, u.full_name, COALESCE(u.username, SUBSTRING_INDEX(u.email, '@', 1)) as username,
                   sr.detected_diseases, sr.is_healthy, sr.weather_condition, sr.created_at
            FROM scan_records sr
            JOIN users u ON sr.user_id = u.id
            WHERE LOWER(u.barangay) = LOWER(%s)
            ORDER BY sr.created_at DESC LIMIT 20
        """, (clean_b,))
        recent_scans = [{
            'id': r[0], 'user_name': r[1], 'username': r[2], 'disease': r[3],
            'status': 'Healthy' if r[4] else 'Not Healthy', 'weather': r[5], 'created_at': str(r[6])
        } for r in cursor.fetchall()]

        conn.close()

        top_disease = disease_counts[0]['disease'] if disease_counts else ("Healthy Field" if healthy_scans > 0 else "None Reported")
        disease_dict = {r['disease']: r['count'] for r in disease_counts}

        return {
            'barangay': clean_b,
            'total_farmers': total_farmers,
            'total_scans': total_scans,
            'healthy_scans': healthy_scans,
            'unhealthy_scans': unhealthy_scans,
            'diseased_scans': unhealthy_scans,
            'top_disease': top_disease,
            'primary_disease': top_disease,
            'disease_counts': disease_dict,
            'disease_list': disease_counts,
            'recent_scans': recent_scans
        }
    except Exception as e:
        print(f"[DB] get_barangay_summary failed: {e}", file=sys.stderr)
        return None


# --- 10. SYSTEM AUDIT TRAIL LOGGING ---

def log_audit(action, details="", user_id=None, username=None, role=None, ip_address=None):
    """
    Records an immutable security/activity log entry in MariaDB.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO audit_logs (user_id, username, role, action, details, ip_address)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            user_id,
            username or 'system',
            role or 'system',
            action,
            details,
            ip_address or ''
        ))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[DB] log_audit failed: {e}", file=sys.stderr)
        return False

def get_audit_logs(limit=200, offset=0, action_filter=None, search=None):
    """
    Fetches historical audit logs in reverse chronological order with optional filtering and search.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        query = """
            SELECT al.id, al.user_id, al.username, al.role, al.action,
                   al.details, al.ip_address, al.created_at,
                   u.full_name
            FROM audit_logs al
            LEFT JOIN users u ON al.user_id = u.id
            WHERE 1=1
        """
        params = []
        if action_filter:
            query += " AND al.action = %s"
            params.append(action_filter)
        if search and search.strip():
            query += " AND (al.action LIKE %s OR al.username LIKE %s OR al.details LIKE %s OR al.ip_address LIKE %s)"
            s_param = f"%{search.strip()}%"
            params.extend([s_param, s_param, s_param, s_param])

        query += " ORDER BY al.created_at DESC, al.id DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])

        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()
        conn.close()

        return [{
            'id': r[0],
            'user_id': r[1],
            'username': r[2],
            'user_role': r[3],
            'action': r[4],
            'details': r[5],
            'ip_address': r[6],
            'created_at': str(r[7]),
            'user_name': r[8] or r[2] or 'System'
        } for r in rows]
    except Exception as e:
        print(f"[DB] get_audit_logs failed: {e}", file=sys.stderr)
        return []


# --- 11. DATABASE BACKUP & RESTORE UTILITIES ---

def export_all_database_records():
    """Exports all database tables into a structured Python dictionary for backup."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Users table
        cursor.execute("""SELECT id, full_name, username, email, password, role, staff_status,
                                 address, sex, age, barangay, contact_number, dob, created_at FROM users""")
        users_rows = cursor.fetchall()
        users = [{
            'id': r[0], 'full_name': r[1], 'username': r[2], 'email': r[3], 'password': r[4],
            'role': r[5], 'staff_status': r[6], 'address': r[7], 'sex': r[8], 'age': r[9],
            'barangay': r[10], 'contact_number': r[11], 'dob': str(r[12]) if r[12] else None,
            'created_at': str(r[13])
        } for r in users_rows]

        # Scan records table
        cursor.execute("""SELECT id, user_id, image_filename, detected_diseases, health_score,
                                 is_healthy, weather_condition, growth_stage, advice, created_at FROM scan_records""")
        scans_rows = cursor.fetchall()
        scans = [{
            'id': r[0], 'user_id': r[1], 'image_filename': r[2], 'detected_diseases': r[3],
            'health_score': r[4], 'is_healthy': bool(r[5]), 'weather_condition': r[6],
            'growth_stage': r[7], 'advice': r[8], 'created_at': str(r[9])
        } for r in scans_rows]

        # Disease advice table
        cursor.execute("SELECT id, disease_name, advice FROM disease_advice")
        advice_rows = cursor.fetchall()
        advice = [{'id': r[0], 'disease_name': r[1], 'advice': r[2]} for r in advice_rows]

        # Audit logs table
        cursor.execute("SELECT id, user_id, username, role, action, details, ip_address, created_at FROM audit_logs")
        logs_rows = cursor.fetchall()
        logs = [{
            'id': r[0], 'user_id': r[1], 'username': r[2], 'role': r[3],
            'action': r[4], 'details': r[5], 'ip_address': r[6], 'created_at': str(r[7])
        } for r in logs_rows]

        conn.close()
        return {
            "users": users,
            "scan_records": scans,
            "disease_advice": advice,
            "audit_logs": logs
        }
    except Exception as e:
        print(f"[DB] export_all_database_records failed: {e}", file=sys.stderr)
        raise

def import_database_records(records):
    """Restores database records from a backup dictionary."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # 1. Users
        users = records.get("users", [])
        for u in users:
            cursor.execute("""
                INSERT INTO users (id, full_name, username, email, password, role, staff_status, address, sex, age, barangay, contact_number, dob)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    full_name=VALUES(full_name), username=VALUES(username), email=VALUES(email),
                    password=VALUES(password), role=VALUES(role), staff_status=VALUES(staff_status),
                    address=VALUES(address), sex=VALUES(sex), age=VALUES(age), barangay=VALUES(barangay),
                    contact_number=VALUES(contact_number), dob=VALUES(dob)
            """, (
                u.get('id'), u.get('full_name'), u.get('username'), u.get('email'), u.get('password'),
                u.get('role', 'farmer'), u.get('staff_status', 'approved'), u.get('address', ''),
                u.get('sex', 'Male'), u.get('age', 0), u.get('barangay', ''), u.get('contact_number', ''),
                u.get('dob') or None
            ))

        # 2. Scan records
        scans = records.get("scan_records", [])
        for s in scans:
            cursor.execute("""
                INSERT INTO scan_records (id, user_id, image_filename, detected_diseases, health_score, is_healthy, weather_condition, growth_stage, advice)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    user_id=VALUES(user_id), image_filename=VALUES(image_filename),
                    detected_diseases=VALUES(detected_diseases), health_score=VALUES(health_score),
                    is_healthy=VALUES(is_healthy), weather_condition=VALUES(weather_condition),
                    growth_stage=VALUES(growth_stage), advice=VALUES(advice)
            """, (
                s.get('id'), s.get('user_id'), s.get('image_filename', ''), s.get('detected_diseases', 'Healthy'),
                s.get('health_score', 0.0), bool(s.get('is_healthy', False)), s.get('weather_condition', 'hot'),
                s.get('growth_stage', 'Unknown'), s.get('advice', '')
            ))

        # 3. Disease advice
        advice_list = records.get("disease_advice", [])
        for a in advice_list:
            cursor.execute("""
                INSERT INTO disease_advice (id, disease_name, advice)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    disease_name=VALUES(disease_name), advice=VALUES(advice)
            """, (a.get('id'), a.get('disease_name'), a.get('advice')))

        conn.commit()
        conn.close()
        return {
            "users_restored": len(users),
            "scans_restored": len(scans),
            "advice_restored": len(advice_list)
        }
    except Exception as e:
        conn.rollback()
        conn.close()
        print(f"[DB] import_database_records failed: {e}", file=sys.stderr)
        raise
