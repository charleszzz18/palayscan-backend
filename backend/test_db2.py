import pymysql
import sys

try:
    conn = pymysql.connect(
        host="mysql-36584390-dugay684-9775.e.aivencloud.com",
        user="avnadmin",
        password="AVNS_6KuybtPDl6mL-ahfFvI",
        database="defaultdb",
        port=10633
    )
    print("Success without explicit SSL using PyMySQL!")
    conn.close()
    sys.exit(0)
except Exception as e:
    print(f"Failed without explicit SSL using PyMySQL: {e}")
