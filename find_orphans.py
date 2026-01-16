import psycopg2
import sys

def main():
    print("FINDING ALL ORPHANED IDS")
    env = {}
    with open('/app/.env') as f:
        for line in f:
            if '=' in line and not line.strip().startswith('#'):
                key, val = line.strip().split('=', 1)
                env[key] = val

    # Connect to REMOTE DB
    conn = psycopg2.connect(
        host=env['CLUSTER_DB_HOST'],
        port=int(env['CLUSTER_DB_PORT']),
        user=env['CLUSTER_DB_USER'],
        password=env['CLUSTER_DB_PASSWORD'],
        database='data_store_telemetry',
        sslmode='require'
    )
    c = conn.cursor()
    
    # IDs in interactiondetail but NOT in catchmentpoint
    c.execute("""
        SELECT DISTINCT catchment_point_id 
        FROM core_interactiondetail 
        WHERE catchment_point_id NOT IN (SELECT id FROM core_catchmentpoint)
    """)
    rows = c.fetchall()
    print(f"Orphaned IDs found: {rows}")
    
    # Check volume for each
    for r in rows:
        pid = r[0]
        c.execute("SELECT COUNT(*), MIN(date_time_medition), MAX(date_time_medition) FROM core_interactiondetail WHERE catchment_point_id=%s", (pid,))
        stats = c.fetchone()
        print(f"ID {pid}: {stats[0]} records (From {stats[1]} to {stats[2]})")

    conn.close()

if __name__ == '__main__':
    main()
