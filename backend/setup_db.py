# =========================================================================
# PALAYSCAN - DATABASE SET-UP WIZARD (setup_db.py)
# =========================================================================
# Run this ONCE to create the MariaDB database tables, schemas, and register
# the initial administrator account.
# Usage: python setup_db.py

import sys
import os

# Add backend directory to system path to resolve local imports cleanly
sys.path.insert(0, os.path.dirname(__file__))

try:
    import pymysql as mariadb
    from werkzeug.security import generate_password_hash
except ImportError as e:
    print(f"[ERROR] Missing dependency: {e}")
    print("Run: pip install mariadb werkzeug")
    sys.exit(1)

# Connection parameters for local server setup (WAMP default MariaDB port 3307)
DB_CONFIG = {
    "host":     "mysql-36584390-dugay684-9775.e.aivencloud.com",
    "user":     "avnadmin",
    "password": "AVNS_6KuybtPDl6mL-ahfFvI",
    "port":     10633,
    "database": "defaultdb"
}

def run_setup():
    try:
        # Establish connection to MariaDB server
        conn = mariadb.connect(**DB_CONFIG)
        cursor = conn.cursor()
        print("[OK] Connected to MariaDB.")

        # --- 2. CREATE USERS TABLE ---
        # Stores credentials, usernames, full names, addresses (barangays), and contact numbers.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                full_name VARCHAR(100) NOT NULL,
                username VARCHAR(50) UNIQUE,
                email VARCHAR(100) NULL,
                password VARCHAR(255) NOT NULL,
                role ENUM('farmer', 'staff', 'admin') DEFAULT 'farmer',
                staff_status VARCHAR(20) DEFAULT 'approved',
                address VARCHAR(150) DEFAULT '',
                sex VARCHAR(10) DEFAULT 'Male',
                age INT DEFAULT 0,
                dob DATE NULL,
                barangay VARCHAR(100) DEFAULT '',
                contact_number VARCHAR(20) DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        print("[OK] Table 'users' ready.")

        # --- 3. CREATE SESSIONS TABLE ---
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_sessions (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                token VARCHAR(64) NOT NULL UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
        """)
        print("[OK] Table 'user_sessions' ready.")

        # --- 4. CREATE SCAN RECORDS TABLE ---
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS scan_records (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT,
                image_filename VARCHAR(255) DEFAULT '',
                detected_diseases VARCHAR(255) DEFAULT 'Healthy',
                health_score FLOAT DEFAULT 0,
                is_healthy BOOLEAN DEFAULT FALSE,
                weather_condition VARCHAR(20) DEFAULT 'hot',
                growth_stage VARCHAR(30) DEFAULT 'Unknown',
                advice TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
            );
        """)
        print("[OK] Table 'scan_records' ready.")

        # --- 5. CREATE AUDIT LOGS TABLE ---
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
        print("[OK] Table 'audit_logs' ready.")

        # --- RUN AUTO-MIGRATIONS FOR NEW COLUMNS (username, dob, etc.) ---
        from disease_db import run_auto_migrations
        run_auto_migrations(conn)
        print("[OK] Column migrations applied.")

        # --- 6. REGISTER DEFAULT ADMIN ACCOUNT ---
        cursor.execute("SELECT id FROM users WHERE email = 'admin@palayscan.com';")
        admin_row = cursor.fetchone()
        if admin_row is None:
            admin_hash = generate_password_hash("Admin@123")
            cursor.execute("""
                INSERT INTO users (full_name, username, email, password, role, address, sex, age, barangay)
                VALUES ('System Administrator', 'admin', 'admin@palayscan.com', %s, 'admin', 'DMMMSU Campus', 'Male', 35, 'Poblacion');
            """, (admin_hash,))
            conn.commit()
            print("[OK] Default admin created.")
            print("     Username: admin")
            print("     Password: Admin@123")
        else:
            cursor.execute("UPDATE users SET username = 'admin' WHERE id = %s", (admin_row[0],))
            conn.commit()
            print("[OK] Admin account updated with username 'admin'.")

        conn.close()
        print("\n[SUCCESS] Database setup complete! PALAYSCAN database is configured and ready.")

    except mariadb.Error as e:
        print(f"[ERROR] Database error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_setup()
