import mariadb
import sys

try:
    conn = mariadb.connect(
        host="mysql-36584390-dugay684-9775.e.aivencloud.com",
        user="avnadmin",
        password="AVNS_6KuybtPDl6mL-ahfFvI",
        database="defaultdb",
        port=10633
    )
    print("Success without explicit SSL!")
    conn.close()
    sys.exit(0)
except Exception as e:
    print(f"Failed without explicit SSL: {e}")

try:
    conn = mariadb.connect(
        host="mysql-36584390-dugay684-9775.e.aivencloud.com",
        user="avnadmin",
        password="AVNS_6KuybtPDl6mL-ahfFvI",
        database="defaultdb",
        port=10633,
        ssl_verify_cert=False
    )
    print("Success with ssl_verify_cert=False!")
    conn.close()
except Exception as e:
    print(f"Failed with ssl_verify_cert=False: {e}")
