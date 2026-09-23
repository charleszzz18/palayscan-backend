import os
import sys
import shutil

# Ensure backend directory in path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from disease_db import get_db_connection

def wipe_system_data():
    print("=" * 60)
    print("   [+] PALAYSCAN - CLEANUP & RESET WIZARD [+]")
    print("=" * 60)
    
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # 1. Check superadmin exists
        cursor.execute("SELECT id, username, full_name, role FROM users WHERE username = 'admin';")
        admin_user = cursor.fetchone()
        if not admin_user:
            print("[!] Warning: 'admin' account not found. Looking for any role='admin'...")
            cursor.execute("SELECT id, username, full_name, role FROM users WHERE role = 'admin' LIMIT 1;")
            admin_user = cursor.fetchone()

        if admin_user:
            admin_id = admin_user[0]
            admin_name = admin_user[1]
            print(f"[+] Preserving Superadmin: ID={admin_id}, Username='{admin_name}'")
        else:
            print("[!] Error: No admin account found. Aborting to avoid locking out.")
            return

        # 2. Delete all sessions
        cursor.execute("DELETE FROM user_sessions;")
        print(f"[+] Cleared 'user_sessions' table.")

        # 3. Delete all scan records
        cursor.execute("DELETE FROM scan_records;")
        cursor.execute("ALTER TABLE scan_records AUTO_INCREMENT = 1;")
        print(f"[+] Cleared 'scan_records' table (Reset AUTO_INCREMENT to 1).")

        # 4. Delete all audit logs
        cursor.execute("DELETE FROM audit_logs;")
        cursor.execute("ALTER TABLE audit_logs AUTO_INCREMENT = 1;")
        print(f"[+] Cleared 'audit_logs' table (Reset AUTO_INCREMENT to 1).")

        # 5. Delete all users except superadmin
        cursor.execute("DELETE FROM users WHERE id != %s AND username != 'admin';", (admin_id,))
        print(f"[+] Deleted all test users (Only superadmin '{admin_name}' remains).")

        # 6. Delete 'Rust' from disease_advice table
        cursor.execute("DELETE FROM disease_advice WHERE LOWER(disease_name) = 'rust';")
        print(f"[+] Removed any 'Rust' records from 'disease_advice' table.")

        conn.commit()

        # 7. Clear uploads directory
        uploads_dir = os.path.join(BASE_DIR, "uploads")
        if os.path.exists(uploads_dir):
            file_count = 0
            for fname in os.listdir(uploads_dir):
                fpath = os.path.join(uploads_dir, fname)
                try:
                    if os.path.isfile(fpath) or os.path.islink(fpath):
                        os.unlink(fpath)
                        file_count += 1
                    elif os.path.isdir(fpath):
                        shutil.rmtree(fpath)
                        file_count += 1
                except Exception as ex:
                    print(f"   [!] Could not delete {fname}: {ex}")
            print(f"[+] Cleared 'uploads/' directory ({file_count} files removed).")

        print("=" * 60)
        print("   [SUCCESS] System wiped cleanly! Ready for live testing.")
        print(f"   [OK] Active Superadmin: username='{admin_name}'")
        print("=" * 60)

    except Exception as e:
        conn.rollback()
        print(f"[ERROR] Wipe failed: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    wipe_system_data()
