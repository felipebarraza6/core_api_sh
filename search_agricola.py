import psycopg2
import sys

def main():
    print("SEARCHING FOR 'Agricola' IN REMOTE")
    env = {}
    with open('/app/.env') as f:
        for line in f:
            if '=' in line and not line.strip().startswith('#'):
                key, val = line.strip().split('=', 1)
                env[key] = val

    remote_conn = psycopg2.connect(
        host=env['CLUSTER_DB_HOST'],
        port=int(env['CLUSTER_DB_PORT']),
        user=env['CLUSTER_DB_USER'],
        password=env['CLUSTER_DB_PASSWORD'],
        database='data_store_telemetry',
        sslmode='require'
    )
    rc = remote_conn.cursor()
    
    # Check Clients
    print("\n--- Clients matching 'Agricola' ---")
    rc.execute("SELECT id, name FROM core_client WHERE name ILIKE '%Agricola%' LIMIT 50")
    rows = rc.fetchall()
    for r in rows:
        print(r)
        
    remote_conn.close()

if __name__ == '__main__':
    main()
