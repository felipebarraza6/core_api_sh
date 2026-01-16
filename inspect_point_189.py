import psycopg2
import sys

def main():
    print("INSPECTING POINT 189")
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
    rc.execute("SELECT id, title FROM core_catchmentpoint WHERE id=189")
    row = rc.fetchone()
    if row:
        print(f"Remote Point 189: {row}")
    else:
        print("Remote Point 189 DOES NOT EXIST.")
    
    remote_conn.close()

if __name__ == '__main__':
    main()
