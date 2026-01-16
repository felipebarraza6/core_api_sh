import psycopg2
import sys

def main():
    print("Listing ALL Remote Points")
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
    
    rc.execute("SELECT id, title, created FROM core_catchmentpoint ORDER BY title")
    rows = rc.fetchall()
    
    for r in rows:
        print(f"{r[0]}: {r[1]} (Created: {r[2]})")
    
    print(f"Exported {len(rows)} points.")
    remote_conn.close()

if __name__ == '__main__':
    main()
