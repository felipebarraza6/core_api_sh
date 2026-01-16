#!/usr/bin/env python3
"""
Recuperar datos de telemetria (V3).
Fixes:
- Inserts 'modified' column (required by ModelApi).
- Skips orphans (caught by FK exception).
"""
import psycopg2
import os
import sys
from datetime import datetime

def main():
    print("="*60)
    print("RECUPERACIÓN DE DATOS DEL CLUSTER (V3)")
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

    # Meses a recuperar: Desde Enero 2025
    # El script original analizaba, pero aqui voy directo a copiar.
    # Recorremos 2025-01 a 2026-02
    months = [
        "2025-01", "2025-02", "2025-03", "2025-04", 
        "2025-05", "2025-06", "2025-07", "2025-08", 
        "2025-09", "2025-10", "2025-11", "2025-12", "2026-01", "2026-02"
    ]

    print(f"🚀 INICIANDO RECUPERACIÓN V3...")
    
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
            # Select INCLUDING created. We will use created as modified.
            remote_cursor.execute("""
                SELECT
                    catchment_point_id, date_time_medition, send_dga, flow, nivel,
                    total, total_diff, created, days_not_conection, pulses,
                    date_time_last_logger
                FROM core_interactiondetail
                WHERE date_time_medition >= %s AND date_time_medition < %s
                ORDER BY date_time_medition
                LIMIT %s OFFSET %s
            """, (f"{mes}-01", next_month, batch_size, offset))

            rows = remote_cursor.fetchall()
            if not rows:
                break
            
            # Insert
            for row in rows:
                # row: (pid, dt_med, send, flow, niv, tot, tot_diff, created, days, puls, dt_log)
                # We construct params for insert:
                # ..., created, modified, ...
                # modified = created (row[7])
                
                params = list(row)
                # insert modified after created?
                # Local Schema: 
                # catch_id, dt_med, send, flow, niv, tot, tot_diff, created, MODIFIED, days, puls, dt_log
                
                try:
                    local_cursor.execute("""
                        INSERT INTO core_interactiondetail (
                            catchment_point_id, date_time_medition, send_dga, flow, nivel,
                            total, total_diff, created, modified, days_not_conection, pulses,
                            date_time_last_logger
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (catchment_point_id, date_time_medition) DO NOTHING
                    """, (
                        row[0], row[1], row[2], row[3], row[4],
                        row[5], row[6], row[7], row[7], # modified=created
                        row[8], row[9], row[10]
                    ))
                except Exception as e:
                    # Ignore FK errors or others
                    # print(f"Err {e}")
                    total_errores += 1
                    local_conn.rollback()
            
            local_conn.commit()
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
