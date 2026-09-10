# =========================================================================
# PALAYSCAN - USER SEEDING SCRIPT (seed_users.py)
# =========================================================================
# This script inserts 100 users (60 males, 40 females) distributed across
# all 47 barangays of Bacnotan, La Union into the Palayscan database.
# Usage: python seed_users.py

import sys
import os
import random

# Add backend directory to system path to resolve local imports cleanly
sys.path.insert(0, os.path.dirname(__file__))

from disease_db import create_user, check_email_exists, get_db_connection

BARANGAYS = [
    "Agtipal", "Arosip", "Bacqui", "Bacsil", "Bagutot", "Ballogo",
    "Baroro", "Bitalag", "Bulala", "Burayoc", "Bussaoit", "Cabaroan",
    "Cabarsican", "Cabugao", "Calautit", "Carcarmay", "Casiaman",
    "Galongen", "Guinabang", "Legleg", "Lisqueb", "Mabanengbeng 1st",
    "Mabanengbeng 2nd", "Maragayap", "Nagatiran", "Nagsaraboan",
    "Nagsimbaanan", "Nangalisan", "Narra", "Ortega", "Oya-oy",
    "Paagan", "Pandan", "Pang-pang", "Poblacion", "Quirino",
    "Raois", "Salincob", "San Martin", "Santa Cruz", "Santa Rita",
    "Sapilang", "Sayoan", "Sipulo", "Tammocalao", "Ubbog", "Zaragosa"
]

MALE_FIRST_NAMES = [
    "Juan", "Jose", "Pedro", "Eduardo", "Roberto", "Antonio", "Francisco", "Manuel",
    "Ricardo", "Fernando", "Mario", "Carlos", "Miguel", "Rafael", "Gabriel", "Ramon",
    "Angelo", "Dennis", "Mark", "John", "Michael", "Christian", "Ronald", "Reynaldo",
    "Danilo", "Noel", "Victor", "Alexander", "Louie", "Vincent", "Kevin", "Jayson",
    "Bryan", "Anthony", "Edgar", "Wilfredo", "Rodolfo", "Armando", "Arnel", "Ernesto",
    "Benigno", "Dominador", "Rogelio", "Generoso", "Teodoro", "Bonifacio", "Apolinario", "Emilio",
    "Crisanto", "Gregorio", "Macario", "Leandro", "Mariano", "Severino", "Dionisio", "Catalino",
    "Florentino", "Silvestre", "Valeriano", "Zosimo"
]

FEMALE_FIRST_NAMES = [
    "Maria", "Elena", "Rosa", "Ana", "Teresa", "Carmen", "Yolanda", "Luisa",
    "Sofia", "Clara", "Cristina", "Gloria", "Lilia", "Remedios", "Teresita", "Victoria",
    "Cecilia", "Josefina", "Lourdes", "Rosario", "Estelita", "Corazon", "Marites", "Rowena",
    "Jennifer", "Michelle", "Catherine", "Janice", "Irene", "Jocelyn", "Marilyn", "Analyn",
    "Shirley", "Josephine", "Evelyn", "Leticia", "Divina", "Amalia", "Perlita", "Milagros"
]

LAST_NAMES = [
    "Cruz", "Santos", "Reyes", "Garcia", "Mendoza", "Torres", "Flores", "Gonzales",
    "Perez", "Castillo", "Gomez", "Romero", "Alvarez", "Ramos", "Rivera", "Bautista",
    "Villanueva", "Roxas", "Soriano", "Mercado", "Navarro", "Tolentino", "Trinidad", "Fernandez",
    "Aquino", "Dizon", "Valenzuela", "Salazar", "De Leon", "Pineda", "Jimenez", "Aguilar",
    "Cortez", "Miranda", "Guzman", "Morales", "Santiago", "David", "Ocampo", "Ignacio",
    "Delos Santos", "Valdez", "Pascual", "Soriano", "Manalo", "Calderon", "Velasco", "Rosario"
]

def generate_users():
    print("[INFO] Starting database seeding for Bacnotan users...")
    
    # Check DB connection first
    try:
        conn = get_db_connection()
        conn.close()
    except Exception as e:
        print(f"[ERROR] Cannot connect to database: {e}")
        return

    created_count = 0
    skipped_count = 0
    males_created = 0
    females_created = 0

    # Ensure every barangay gets at least one user first (47 users: 28 males, 19 females)
    # Then randomly assign the remaining 53 users (32 males, 21 females) across the barangays.
    
    barangay_pool = list(BARANGAYS)
    random.shuffle(barangay_pool)
    
    # We want exactly 60 males and 40 females
    user_definitions = []
    
    # 60 Males
    for i in range(60):
        fname = MALE_FIRST_NAMES[i % len(MALE_FIRST_NAMES)]
        lname = LAST_NAMES[(i * 3) % len(LAST_NAMES)]
        # Assign barangay: first 47 users get one unique barangay each, remainder random
        if i < len(BARANGAYS):
            brgy = BARANGAYS[i]
        else:
            brgy = random.choice(BARANGAYS)
        user_definitions.append({
            "full_name": f"{fname} {lname}",
            "sex": "Male",
            "barangay": brgy,
            "email_prefix": f"{fname.lower()}.{lname.lower().replace(' ', '')}"
        })

    # 40 Females
    for i in range(40):
        fname = FEMALE_FIRST_NAMES[i % len(FEMALE_FIRST_NAMES)]
        lname = LAST_NAMES[(i * 5 + 2) % len(LAST_NAMES)]
        # For females, assign remaining unassigned barangays if any (there are 47 barangays, 60 males covered all 47, so females can be random or distributed)
        brgy = random.choice(BARANGAYS)
        user_definitions.append({
            "full_name": f"{fname} {lname}",
            "sex": "Female",
            "barangay": brgy,
            "email_prefix": f"{fname.lower()}.{lname.lower().replace(' ', '')}"
        })

    # Shuffle the insertion order
    random.shuffle(user_definitions)

    default_password = "Farmer@123"

    for idx, u in enumerate(user_definitions, 1):
        # Create unique email
        clean_brgy = u["barangay"].lower().replace(" ", "").replace("-", "")
        email = f"{u['email_prefix']}.{clean_brgy}{idx}@palayscan.com"
        
        # Check if email already exists, if so append random number
        while check_email_exists(email):
            email = f"{u['email_prefix']}.{clean_brgy}{random.randint(100, 9999)}@palayscan.com"

        age = random.randint(21, 65)
        address = f"{u['barangay']}, Bacnotan, La Union"
        contact_number = f"09{random.randint(10, 99)}{random.randint(1000000, 9999999)}"

        user_id = create_user(
            full_name=u["full_name"],
            email=email,
            password=default_password,
            role="farmer",
            address=address,
            sex=u["sex"],
            age=age,
            barangay=u["barangay"],
            contact_number=contact_number
        )

        if user_id:
            created_count += 1
            if u["sex"] == "Male":
                males_created += 1
            else:
                females_created += 1
            print(f"[{created_count:03d}/100] Created {u['sex']:6s} user: {u['full_name']:22s} | Brgy: {u['barangay']:18s} | {email}")
        else:
            skipped_count += 1
            print(f"[ERROR] Failed to create user: {u['full_name']}")

    print("\n" + "="*65)
    print("USER SEEDING SUMMARY")
    print("="*65)
    print(f"Total Attempted : 100")
    print(f"Successfully Added: {created_count} (Males: {males_created}, Females: {females_created})")
    print(f"Skipped/Failed  : {skipped_count}")
    print(f"Default Password: {default_password}")
    print("="*65)

if __name__ == "__main__":
    generate_users()
