#!/usr/bin/env python3
"""
Recuperar datos de telemetria (V6).
Fixes:
- Crash at commit due to FK.
- Implements Row-by-Row Commit to isolate errors.
- Targets ONLY Dec 2025 and Jan 2026+
"""
import psycopg2
import os
import sys

def main():
    print("="*60)
    print("RECUPERACIÓN DE DATOS DEL CLUSTER (V6 - FINAL)")
    print("="*60)
    sys.stdout.flush()

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

    remote_cursor = remote_conn.cursor()
    local_cursor = local_conn.cursor()

    # Resume from Dec 2025
    months = [
        "2025-12", "2026-01", "2026-02"
    ]

    print(f"🚀 INICIANDO RECUPERACIÓN V6...")
    
    batch_size = 5000
    total_copiados = 0
    total_errores = 0

    for mes in months:
        print(f"\n📥 Copiando mes {mes}...")
        sys.stdout.flush()

        year, month = mes.split('-')
        if month == '12':
            next_month = f"{int(year)+1}-01-01"
        else:
            next_month = f"{year}-{int(month)+1:02d}-01"

        offset = 0
        mes_copiados = 0
        
        while True:
            remote_cursor.execute("""
                SELECT
                    catchment_point_id, date_time_medition, date_time_last_logger,
                    flow, total, total_diff, total_today_diff, nivel, water_table,
                    send_dga, return_dga, n_voucher, is_error,
                    pulses, days_not_conection, created
                FROM core_interactiondetail
                WHERE date_time_medition >= %s AND date_time_medition < %s
                ORDER BY date_time_medition
                LIMIT %s OFFSET %s
            """, (f"{mes}-01", next_month, batch_size, offset))

            rows = remote_cursor.fetchall()
            if not rows:
                break
            
            for row in rows:
                try:
                    local_cursor.execute("""
                        INSERT INTO core_interactiondetail (
                            catchment_point_id, date_time_medition, date_time_last_logger,
                            flow, total, total_diff, total_today_diff, nivel, water_table,
                            send_dga, return_dga, n_voucher, is_error,
                            pulses, days_not_conection, created, modified, notification_id, is_partial
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL, false)
                        ON CONFLICT (catchment_point_id, date_time_medition) DO NOTHING
                    """, (
                        row[0], row[1], row[2],
                        row[3], row[4], row[5], row[6], row[7], row[8],
                        row[9], row[10], row[11], row[12],
                        row[13], row[14], row[15], row[15] # modified
                    ))
                    # COMMIT PER ROW to safely handle orphans
                    local_conn.commit()
                except Exception as e:
                    total_errores += 1
                    local_conn.rollback()
            
            mes_copiados += len(rows)
            total_copiados += len(rows)
            print(f"  ✓ {mes}: {mes_copiados:>8,} procesados (Offset {offset})", end='\r')
            sys.stdout.flush()
            
            offset += batch_size

        print(f"  ✅ {mes}: {mes_copiados:>8,} procesados COMPLETO")

    print(f"\n🎉 RECUPERACIÓN COMPLETADA")
    print(f"Total procesados: {total_copiados:,}")
    print(f"Errores (ignorados): {total_errores:,}")

if __name__ == '__main__':
    main()
