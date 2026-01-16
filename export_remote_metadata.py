import psycopg2
import sys

def main():
    print("Listing ALL Remote Clients and Projects")
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
    
    print("\n--- ALL CLIENTS ---")
    rc.execute("SELECT id, name FROM core_client ORDER BY name")
    for r in rc.fetchall():
        print(r)
        
    print("\n--- ALL PROJECTS ---")
    rc.execute("SELECT id, name FROM core_projectcatchments ORDER BY name")
    for r in rc.fetchall():
        print(r)

    remote_conn.close()

if __name__ == '__main__':
    main()
