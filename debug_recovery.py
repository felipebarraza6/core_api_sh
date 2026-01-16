import psycopg2
import sys

def main():
    print("DEBUGGING RECOVERY")
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
    local_conn = psycopg2.connect(
        host='postgres',
        port=5432,
        user='smarthydro_user',
        password='smarthydro_password_2025',
        database='smarthydro_prod'
    )
    
    rc = remote_conn.cursor()
    lc = local_conn.cursor()
    
    print("Fetching 1 record from Sept 2025...")
    rc.execute("""
        SELECT
            catchment_point_id, date_time_medition, date_time_last_logger,
            flow, total, total_diff, total_today_diff, nivel, water_table,
            send_dga, return_dga, n_voucher, is_error,
            pulses, days_not_conection, created
        FROM core_interactiondetail
        WHERE date_time_medition >= '2025-09-01'
        LIMIT 1
    """)
    row = rc.fetchone()
    if row:
        # row: (pid, dt_med, dt_log, flow, tot, diff, today_diff, niv, wt, send, ret, n_v, err, puls, days, created)
        print(f"Got row: {row}")
        try:
            lc.execute("""
                INSERT INTO core_interactiondetail (
                    catchment_point_id, date_time_medition, date_time_last_logger,
                    flow, total, total_diff, total_today_diff, nivel, water_table,
                    send_dga, return_dga, n_voucher, is_error,
                    pulses, days_not_conection, created, modified, notification_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL)
            """, (
                row[0], row[1], row[2],
                row[3], row[4], row[5], row[6], row[7], row[8],
                row[9], row[10], row[11], row[12],
                row[13], row[14], row[15], row[15] # modified
            ))
            local_conn.commit()
            print("Insert SUCCESS")
        except Exception as e:
            print(f"Insert FAILED: {e}")
            local_conn.rollback()
            
            # Check if point exists
            pid = row[0]
            lc.execute("SELECT id FROM core_catchmentpoint WHERE id=%s", (pid,))
            if lc.fetchone():
                print(f"Point {pid} EXISTS locally.")
            else:
                print(f"Point {pid} DOES NOT EXIST locally.")
    else:
        print("No rows found in remote for Sept 2025")

if __name__ == '__main__':
    main()
