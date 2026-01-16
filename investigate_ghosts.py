import psycopg2
import sys

def main():
    print("INVESTIGATING GHOST POINTS (189, 192)")
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
    
    # 1. Search in DGA/Profile Configs (metadata might survive point deletion if cascaded incorrectly? unlikely but check)
    print("\n--- Searching in DGA/Profile Configs ---")
    rc.execute("SELECT * FROM core_dgadataconfigcatchment WHERE point_catchment_id IN (189, 192)")
    print(f"DGA Configs found: {rc.fetchall()}")
    
    rc.execute("SELECT * FROM core_profiledataconfigcatchment WHERE point_catchment_id IN (189, 192)")
    print(f"Profile Configs found: {rc.fetchall()}")

    # 2. Check Django Admin Log
    # Table: django_admin_log
    # Columns: id, action_time, user_id, content_type_id, object_id, object_repr, action_flag, change_message
    print("\n--- Searching in Django Admin Log (Deletions) ---")
    try:
        # action_flag = 3 (Deletion)
        rc.execute("""
            SELECT action_time, user_id, object_id, object_repr, change_message 
            FROM django_admin_log 
            WHERE object_id IN ('189', '192') 
            ORDER BY action_time DESC
        """)
        rows = rc.fetchall()
        if rows:
            for r in rows:
                print(f"LOG FOUND: {r}")
        else:
            print("No admin logs found for these IDs.")
            
        # Also search for "Higuera" in logs just in case it was deleted
        print("\n--- Searching 'Higuera' in Admin Log ---")
        rc.execute("""
            SELECT action_time, object_repr, action_flag
            FROM django_admin_log 
            WHERE object_repr ILIKE '%Higuera%'
            ORDER BY action_time DESC
            LIMIT 10
        """)
        for r in rows:
            print(f"LOG HIGUERA: {r}")

    except Exception as e:
        print(f"Could not read admin log: {e}")

    remote_conn.close()

if __name__ == '__main__':
    main()
