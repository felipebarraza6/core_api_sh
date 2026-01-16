import psycopg2
import sys

def main():
    env = {}
    with open('/app/.env') as f:
        for line in f:
            if '=' in line and not line.strip().startswith('#'):
                key, val = line.strip().split('=', 1)
                env[key] = val

    print("Connecting to LOCAL...")
    conn = psycopg2.connect(
        host='postgres',
        port=5432,
        user='smarthydro_user',
        password='smarthydro_password_2025',
        database='smarthydro_prod'
    )
    cur = conn.cursor()
    
    # Check core_client columns
    print("\n--- core_client columns ---")
    cur.execute("SELECT * FROM core_client LIMIT 0")
    colnames = [desc[0] for desc in cur.description]
    print(colnames)

    # Check core_user columns
    print("\n--- core_user columns ---")
    try:
        cur.execute("SELECT * FROM core_user LIMIT 0")
        colnames = [desc[0] for desc in cur.description]
        print(colnames)
    except Exception as e:
        print(e)

    conn.close()
    # Check core_profiledataconfigcatchment columns
    print("\n--- core_profiledataconfigcatchment columns ---")
    try:
        cur.execute("SELECT * FROM core_profiledataconfigcatchment LIMIT 0")
        colnames = [desc[0] for desc in cur.description]
        print(colnames)
    except Exception as e:
        print(e)

    conn.close()

if __name__ == "__main__":
    main()
