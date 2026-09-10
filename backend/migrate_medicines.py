import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import mariadb
from disease_db import DB_CONFIG, get_db_connection

def migrate_medicines():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Create table if it doesn't exist
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS disease_advice (
                id INT AUTO_INCREMENT PRIMARY KEY,
                disease_name VARCHAR(100) NOT NULL,
                advice TEXT NOT NULL
            );
        """)
        
        # Specific medicines to seed
        medicines = {
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
            ]
        }
        
        # Clear old general advice and insert specific medicines
        cursor.execute("TRUNCATE TABLE disease_advice;")
        
        for disease, advices in medicines.items():
            for advice in advices:
                cursor.execute(
                    "INSERT INTO disease_advice (disease_name, advice) VALUES (%s, %s)",
                    (disease, advice)
                )
                
        conn.commit()
        conn.close()
        print("[SUCCESS] specific medicines seeded successfully.")
        
    except mariadb.Error as e:
        print(f"[ERROR] Database error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    migrate_medicines()
