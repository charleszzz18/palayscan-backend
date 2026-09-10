# =========================================================================
# PALAYSCAN - DATABASE CONNECTION & QUERY CONTROLLER (disease_db.py)
# =========================================================================
# This module manages all MariaDB communications. It handles database connections,
# checks, data inserts, queries for auth (users, sessions), scans, and 
# admin-level actions. Written with clean error boundaries to prevent
# database exceptions from crashing the Flask app.

import pymysql as mariadb
import sys
import secrets
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash

# --- 1. CONFIGURATION SETTINGS ---
# Defines the server address, user credentials, database name, and custom port.
# NOTE: Port is set to 3307 to target the default WAMP MariaDB server.
DB_CONFIG = { 
    "host":     "mysql-36584390-dugay684-9775.e.aivencloud.com",
    "user":     "avnadmin",
    "password": "AVNS_6KuybtPDl6mL-ahfFvI",
    "port":     10633,
    "database": "defaultdb",
    "autocommit": True
}

_migrated = False

def run_auto_migrations(conn):
    """Safely checks and adds address, sex, and age columns to users table if missing."""
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
        conn.commit()
    except mariadb.Error as e:
        pass

def get_db_connection(): 
    """
    Opens and returns a fresh MariaDB connection.
    Raises a clear error if the connection fails so Flask can handle it gracefully.
    """
    global _migrated
    try: 
        conn = mariadb.connect(**DB_CONFIG) 
        conn.auto_reconnect = True # Keep connection active and prevent timeout drops
        if not _migrated:
            run_auto_migrations(conn)
            _migrated = True
        return conn 
    except mariadb.Error as e: 
        print(f"[DB] ERROR: Cannot connect to database — {e}", file=sys.stderr) 
        print(f"[DB] Check: Is WAMP running? Is the password correct? Port={DB_CONFIG['port']}", file=sys.stderr) 
        raise # Stop execution and propagate failure to the caller

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
    "Leaf Strip": [
        "Apply Copper-based bactericides or Streptomycin.",
        "Remove and burn infected leaves to prevent further spread.",
        "Practice crop rotation to break the disease cycle."
    ],
    "Rust": [
        "Apply Hexaconazole or Propiconazole fungicide.",
        "Ensure good field drainage and weed management to increase air circulation.",
        "Avoid planting late during the season as rust thrives in cooler late-season temperatures."
    ],
    "Healthy": [
        "Walang kailangang gamot. Panatilihin ang regular na patubig at pag-aalaga.",
        "Magpatuloy sa regular na pagsusuri ng palayan upang maagapan ang anumang peste."
    ]
}

def get_advice(disease_name): 
    """
    Returns a list of treatment advice strings for the given disease from MariaDB.
    Falls back to curated default advice if the database query returns empty or fails.
    """
    if not disease_name: 
        return [] 
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

    # Return curated fallback advice if database has no records or errored
    return DEFAULT_ADVICE.get(disease_name, [
        f"Kumonsulta sa inyong lokal na Agriculture Officer para sa tamang gamot laban sa {disease_name}.",
        "Ihiwalay ang mga apektadong halaman upang maiwasan ang pagkalat ng sakit."
    ]) 

def get_diseases_by_weather_from_db(weather_condition): 
    """
    Returns all disease names that can occur under the given weather condition.
    Includes both weather-specific AND temperature-tolerant diseases.
    """
    try: 
        conn = get_db_connection() 
        cursor = conn.cursor() 
        # Select diseases matching the hot/cold temperature category
        cursor.execute( 
            "SELECT DISTINCT disease_name FROM disease_temperature_categories WHERE temperature_category = %s", 
            (weather_condition,) 
        )
        weather_diseases = [row[0] for row in cursor.fetchall()] 
        conn.close() 
        
        # Remove any duplicates while keeping array order
        seen = set() 
        all_diseases = [] 
        for d in weather_diseases: 
            if d not in seen: 
                seen.add(d) 
                all_diseases.append(d) 
        return all_diseases 
    except mariadb.Error as e: 
        print(f"[DB] get_diseases_by_weather_from_db('{weather_condition}') failed: {e}", file=sys.stderr) 
        return None 

def get_diseases_by_weather(weather_condition): 
    """
    Public wrapper for get_diseases_by_weather_from_db.
    Returns a list of disease names, or None if DB is unavailable.
    """
    return get_diseases_by_weather_from_db(weather_condition) 

def filter_diseases_by_weather(detected_diseases, weather_condition):
    """
    Filters detected diseases by checking if they are biologically appropriate for the current weather.
    If the DB is down, it skips the filter and returns the original list as a fallback.
    """
    if not detected_diseases:
        return []
    weather_appropriate = get_diseases_by_weather(weather_condition)
    if weather_appropriate is None:
        print(f"[DB] WARNING: DB unavailable — skipping weather filter.", file=sys.stderr)
        return detected_diseases
    return [d for d in detected_diseases if d in weather_appropriate]


# --- 3. SECURE AUTHENTICATION QUERIES ---

def check_email_exists(email):
    """Checks if an email is already present in the users table."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
        result = cursor.fetchone()
        conn.close()
        return result is not None
    except mariadb.Error as e:
        print(f"[DB] check_email_exists failed: {e}", file=sys.stderr)
        return False

def create_user(full_name, email, password, role='farmer', staff_status='approved', address='', sex='Male', age=0, barangay='', contact_number=''):
    """
    Creates a new user profile.
    Uses Werkzeug's secure hashing (PBKDF2) to hash the password before database insertion.
    Returns user_id or None on failure.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        password_hash = generate_password_hash(password) # Secure password hash
        cursor.execute(
            "INSERT INTO users (full_name, email, password, role, staff_status, address, sex, age, barangay, contact_number) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (full_name, email, password_hash, role, staff_status, address, sex, int(age), barangay, contact_number)
        )
        conn.commit()
        user_id = cursor.lastrowid
        conn.close()
        return user_id
    except Exception as e:
        print(f"[DB] create_user failed: {e}", file=sys.stderr)
        return None

def get_user_by_email(email):
    """Fetches user account row matching an email address."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, full_name, email, password, role, staff_status, address, sex, age, barangay, contact_number FROM users WHERE email = %s",
            (email,)
        )
        row = cursor.fetchone()
        conn.close()
        if row:
            return {'id': row[0], 'full_name': row[1], 'email': row[2],
                    'password': row[3], 'role': row[4], 'staff_status': row[5] or 'approved',
                    'address': row[6], 'sex': row[7], 'age': row[8], 'barangay': row[9], 'contact_number': row[10]}
        return None
    except Exception as e:
        print(f"[DB] get_user_by_email failed: {e}", file=sys.stderr)
        return None

def verify_password(email, password):
    """
    Validates password validity.
    Compares the raw login input with the stored cryptographic hash.
    """
    user = get_user_by_email(email)
    if user and check_password_hash(user['password'], password):
        return user
    return None

def create_session(user_id):
    """
    Generates a secure hex session token valid for 7 days.
    Inserts details into user_sessions to keep the user logged in.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        token = secrets.token_hex(32) # Secure 64-character token string
        expires_at = datetime.now() + timedelta(days=7)
        cursor.execute(
            "INSERT INTO user_sessions (user_id, token, expires_at) VALUES (%s, %s, %s)",
            (user_id, token, expires_at)
        )
        conn.commit()
        conn.close()
        return token
    except mariadb.Error as e:
        print(f"[DB] create_session failed: {e}", file=sys.stderr)
        return None

def get_user_by_token(token):
    """
    Validates token validity.
    Checks if token is correct and that the expiration timestamp is in the future.
    """
    if not token:
        return None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """SELECT u.id, u.full_name, u.email, u.role, u.staff_status, u.address, u.sex, u.age, u.barangay
               FROM users u JOIN user_sessions s ON u.id = s.user_id
               WHERE s.token = %s AND s.expires_at > NOW()""",
            (token,)
        )
        row = cursor.fetchone()
        conn.close()
        if row:
            return {'id': row[0], 'full_name': row[1], 'email': row[2], 'role': row[3], 'staff_status': row[4] or 'approved',
                    'address': row[5], 'sex': row[6], 'age': row[7], 'barangay': row[8]}
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
    except mariadb.Error as e:
        print(f"[DB] delete_session failed: {e}", file=sys.stderr)
        return False


# --- 4. SCAN HISTORICAL RECORD QUERIES ---

def save_scan_record(user_id, image_filename, detected_diseases, health_score, is_healthy, weather_condition, growth_stage, advice):
    """
    Saves diagnostic outputs to the database.
    Serializes list parameters to comma-separated lists for storage.
    """
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
    except mariadb.Error as e:
        print(f"[DB] save_scan_record failed: {e}", file=sys.stderr)
        return None


# --- 5. ADMINISTRATION CONTROL PANEL CONTROLLERS ---

def get_all_scan_records():
    """Fetches list of all scans in reverse chronological order for administration view."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """SELECT sr.id, u.full_name, u.email, u.barangay,
                      sr.detected_diseases, sr.health_score, sr.is_healthy,
                      sr.weather_condition, sr.growth_stage, sr.created_at, sr.image_filename
               FROM scan_records sr
               LEFT JOIN users u ON sr.user_id = u.id
               ORDER BY sr.created_at DESC"""
        )
        rows = cursor.fetchall()
        conn.close()
        return [{
            'id': r[0], 'user_name': r[1] or 'Unknown', 'user_email': r[2] or '',
            'barangay': r[3] or '', 'detected_diseases': r[4],
            'health_score': round(float(r[5]) * 100, 1) if r[5] else 0,
            'is_healthy': bool(r[6]), 'weather_condition': r[7],
            'growth_stage': r[8], 'created_at': str(r[9]), 'image_filename': r[10] or ''
        } for r in rows]
    except mariadb.Error as e:
        print(f"[DB] get_all_scan_records failed: {e}", file=sys.stderr)
        return []

def get_all_users():
    """Fetches list of registered users for dashboard review."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, full_name, email, role, staff_status, address, sex, age, barangay, contact_number, created_at FROM users ORDER BY created_at DESC"
        )
        rows = cursor.fetchall()
        conn.close()
        return [{
            'id': r[0], 'full_name': r[1], 'email': r[2], 'role': r[3], 'staff_status': r[4] or 'approved',
            'address': r[5] or '', 'sex': r[6] or '—', 'age': r[7] or 0,
            'barangay': r[8] or '', 'contact_number': r[9] or '', 'created_at': str(r[10])
        } for r in rows]
    except Exception as e:
        print(f"[DB] get_all_users failed: {e}", file=sys.stderr)
        return []

def admit_staff_user(user_id):
    """Admit a pending staff registration: sets role='staff', staff_status='approved'."""
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
    """Reject a staff registration: sets role='farmer', staff_status='rejected'. Automatically listed as farmer."""
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
    """Deletes user record. Security rule: Admins cannot be deleted."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM users WHERE id = %s AND role != 'admin'", (user_id,))
        conn.commit()
        affected = cursor.rowcount
        conn.close()
        return affected > 0
    except mariadb.Error as e:
        print(f"[DB] delete_user_by_id failed: {e}", file=sys.stderr)
        return False

def get_dashboard_stats():
    """Calculates numerical summaries and disease counts for admin charts."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 1. Total users
        cursor.execute("SELECT COUNT(*) FROM users WHERE role != 'admin'")
        total_users = cursor.fetchone()[0]
        
        # 2. Total scans
        cursor.execute("SELECT COUNT(*) FROM scan_records")
        total_scans = cursor.fetchone()[0]
        
        # 3. Healthy count
        cursor.execute("SELECT COUNT(*) FROM scan_records WHERE is_healthy = 1")
        healthy_scans = cursor.fetchone()[0]
        
        # 4. Top 5 scan result frequencies (including healthy)
        cursor.execute(
            "SELECT detected_diseases, COUNT(*) as cnt FROM scan_records GROUP BY detected_diseases ORDER BY cnt DESC LIMIT 5"
        )
        top_diseases = [{'disease': r[0], 'count': r[1]} for r in cursor.fetchall()]

        # 5. Gender distribution
        cursor.execute("SELECT sex, COUNT(*) FROM users WHERE role != 'admin' GROUP BY sex")
        gender_distribution = [{'sex': r[0] or 'Unknown', 'count': r[1]} for r in cursor.fetchall()]

        # 6. Users per barangay
        cursor.execute("SELECT barangay, COUNT(*) FROM users WHERE role != 'admin' AND barangay != '' GROUP BY barangay ORDER BY COUNT(*) DESC")
        users_per_barangay = [{'barangay': r[0], 'count': r[1]} for r in cursor.fetchall()]

        # 7. Age demographics
        cursor.execute("SELECT age FROM users WHERE role != 'admin' AND age > 0")
        ages = [r[0] for r in cursor.fetchall()]
        age_demographics = {
            '18-29': sum(1 for a in ages if 18 <= a <= 29),
            '30-45': sum(1 for a in ages if 30 <= a <= 45),
            '46-59': sum(1 for a in ages if 46 <= a <= 59),
            '60+': sum(1 for a in ages if a >= 60),
            'Under 18': sum(1 for a in ages if a < 18)
        }
        avg_age = round(sum(ages) / len(ages), 1) if ages else 0

        # 8. New users today
        cursor.execute("SELECT COUNT(*) FROM users WHERE role != 'admin' AND DATE(created_at) = CURDATE()")
        new_users_today = cursor.fetchone()[0]

        # 9. New scans today
        cursor.execute("SELECT COUNT(*) FROM scan_records WHERE DATE(created_at) = CURDATE()")
        new_scans_today = cursor.fetchone()[0]

        conn.close()
        
        return {
            'total_users': total_users, 'total_scans': total_scans,
            'new_users_today': new_users_today, 'new_scans_today': new_scans_today,
            'healthy_scans': healthy_scans, 'diseased_scans': total_scans - healthy_scans,
            'top_diseases': top_diseases,
            'gender_distribution': gender_distribution,
            'users_per_barangay': users_per_barangay,
            'age_demographics': age_demographics,
            'avg_age': avg_age
        }
    except mariadb.Error as e:
        print(f"[DB] get_dashboard_stats failed: {e}", file=sys.stderr)
        return {}


# --- 6. DISEASE DATABASE EDITING (CRUD) ---

SUPPORTED_DISEASES = ["Blight", "Blast", "Brown Spot", "Rust", "Leaf Strip", "Others", "Healthy"]

def get_all_disease_advice():
    """Fetches full list of disease advice rows."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, disease_name, advice FROM disease_advice ORDER BY disease_name, id")
        rows = cursor.fetchall()
        conn.close()
        return [{'id': r[0], 'disease_name': r[1], 'advice': r[2]} for r in rows]
    except mariadb.Error as e:
        print(f"[DB] get_all_disease_advice failed: {e}", file=sys.stderr)
        return []

def add_disease_advice(disease_name, advice_text):
    """Inserts a new advice statement. Returns new ID."""
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
    except mariadb.Error as e:
        print(f"[DB] add_disease_advice failed: {e}", file=sys.stderr)
        return None

def update_disease_advice(advice_id, advice_text):
    """Updates an existing advice statement text."""
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
    except mariadb.Error as e:
        print(f"[DB] update_disease_advice failed: {e}", file=sys.stderr)
        return False

def delete_disease_advice(advice_id):
    """Deletes an advice statement."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM disease_advice WHERE id = %s", (advice_id,))
        conn.commit()
        affected = cursor.rowcount
        conn.close()
        return affected > 0
    except mariadb.Error as e:
        print(f"[DB] delete_disease_advice failed: {e}", file=sys.stderr)
        return False

def get_scan_records_for_report():
    """Gathers full details of scans formatted for CSV exports."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """SELECT sr.id, u.full_name, u.email, u.barangay,
                      sr.detected_diseases, sr.health_score, sr.is_healthy,
                      sr.weather_condition, sr.growth_stage, sr.advice, sr.created_at
               FROM scan_records sr
               LEFT JOIN users u ON sr.user_id = u.id
               ORDER BY sr.created_at DESC"""
        )
        rows = cursor.fetchall()
        conn.close()
        return [{
            'id': r[0], 'user_name': r[1] or 'Unknown', 'email': r[2] or '',
            'barangay': r[3] or '', 'detected_diseases': r[4],
            'health_score': round(float(r[5]) * 100, 1) if r[5] else 0,
            'is_healthy': bool(r[6]), 'weather_condition': r[7],
            'growth_stage': r[8], 'advice': r[9] or '', 'created_at': str(r[10])
        } for r in rows]
    except mariadb.Error as e:
        print(f"[DB] get_scan_records_for_report failed: {e}", file=sys.stderr)
        return []
