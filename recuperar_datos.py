#!/usr/bin/env python3
"""
Script para recuperar datos del cluster remoto
"""
import psycopg2
import os
import sys
from datetime import datetime

def main():
    print("="*60)
    print("RECUPERACIÓN DE DATOS DEL CLUSTER")
    print("="*60)
    sys.stdout.flush()

    # Leer .env
    env = {}
    with open('/app/.env') as f:
        for line in f:
            if '=' in line and not line.strip().startswith('#'):
                key, val = line.strip().split('=', 1)
                env[key] = val

    # Conectar a cluster remoto
    print("\n📡 Conectando al cluster remoto...")
    sys.stdout.flush()

    remote_conn = psycopg2.connect(
        host=env['CLUSTER_DB_HOST'],
        port=int(env['CLUSTER_DB_PORT']),
        user=env['CLUSTER_DB_USER'],
        password=env['CLUSTER_DB_PASSWORD'],
        database='data_store_telemetry',
        sslmode='require'
    )

    # Conectar a local
    print("📡 Conectando a base local...")
    sys.stdout.flush()

    local_conn = psycopg2.connect(
        host='postgres',
        port=5432,
        user='smarthydro_user',
        password='smarthydro_password_2025',
        database='smarthydro_prod'
    )

    remote_cursor = remote_conn.cursor()
    local_cursor = local_conn.cursor()

    # Ver datos disponibles en cluster por mes
    print("\n📊 DATOS EN CLUSTER REMOTO:")
    sys.stdout.flush()

    remote_cursor.execute("""
    SELECT
      TO_CHAR(date_time_medition, 'YYYY-MM') as mes,
      COUNT(*) as registros
    FROM core_interactiondetail
    WHERE date_time_medition >= '2025-01-01'
    GROUP BY TO_CHAR(date_time_medition, 'YYYY-MM')
    ORDER BY mes;
    """)

    cluster_data = {}
    for row in remote_cursor.fetchall():
        mes, count = row
        cluster_data[mes] = count
        print(f"  {mes}: {count:>8,} registros")
        sys.stdout.flush()

    # Ver datos actuales en local
    print("\n📊 DATOS EN LOCAL:")
    sys.stdout.flush()

    local_cursor.execute("""
    SELECT
      TO_CHAR(date_time_medition, 'YYYY-MM') as mes,
      COUNT(*) as registros
    FROM core_interactiondetail
    WHERE date_time_medition >= '2025-01-01'
    GROUP BY TO_CHAR(date_time_medition, 'YYYY-MM')
    ORDER BY mes;
    """)

    local_data = {}
    for row in local_cursor.fetchall():
        mes, count = row
        local_data[mes] = count
        print(f"  {mes}: {count:>8,} registros")
        sys.stdout.flush()

    # Calcular faltantes
    print("\n🔍 ANÁLISIS:")
    sys.stdout.flush()

    total_faltantes = 0
    meses_a_copiar = []

    for mes in sorted(cluster_data.keys()):
        local_count = local_data.get(mes, 0)
        cluster_count = cluster_data[mes]
        diff = cluster_count - local_count

        if diff > 0:
            print(f"  {mes}: FALTAN {diff:>8,} registros")
            total_faltantes += diff
            meses_a_copiar.append(mes)
        else:
            print(f"  {mes}: ✅ OK")
        sys.stdout.flush()

    print(f"\n📊 TOTAL A RECUPERAR: {total_faltantes:,} registros")
    print(f"📅 Meses a copiar: {', '.join(meses_a_copiar)}")
    sys.stdout.flush()

    if total_faltantes == 0:
        print("\n✅ No hay datos faltantes!")
        remote_cursor.close()
        local_cursor.close()
        remote_conn.close()
        local_conn.close()
        return

    # RECUPERAR DATOS
    print(f"\n🚀 INICIANDO RECUPERACIÓN...")
    print(f"Hora inicio: {datetime.now().strftime('%H:%M:%S')}")
    sys.stdout.flush()

    batch_size = 10000
    total_copiados = 0

    for mes in meses_a_copiar:
        print(f"\n📥 Copiando mes {mes}...")
        sys.stdout.flush()

        # Obtener rango del mes
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

            # Insertar en local (ignorar duplicados)
            for row in rows:
                try:
                    local_cursor.execute("""
                        INSERT INTO core_interactiondetail (
                            catchment_point_id, date_time_medition, send_dga, flow, nivel,
                            total, total_diff, created, days_not_conection, pulses,
                            date_time_last_logger
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (catchment_point_id, date_time_medition) DO NOTHING
                    """, row)
                except Exception as e:
                    # Ignorar errores de FK (puntos que no existen)
                    pass

            local_conn.commit()
            mes_copiados += len(rows)
            total_copiados += len(rows)

            print(f"  ✓ {mes}: {mes_copiados:>8,} registros", end='\r')
            sys.stdout.flush()

            offset += batch_size

        print(f"  ✅ {mes}: {mes_copiados:>8,} registros COMPLETO")
        sys.stdout.flush()

    print(f"\n🎉 RECUPERACIÓN COMPLETADA")
    print(f"Total copiado: {total_copiados:,} registros")
    print(f"Hora fin: {datetime.now().strftime('%H:%M:%S')}")
    sys.stdout.flush()

    # VALIDAR
    print("\n🔍 VALIDANDO...")
    sys.stdout.flush()

    local_cursor.execute("""
    SELECT
      TO_CHAR(date_time_medition, 'YYYY-MM') as mes,
      COUNT(*) as registros
    FROM core_interactiondetail
    WHERE date_time_medition >= '2025-01-01'
    GROUP BY TO_CHAR(date_time_medition, 'YYYY-MM')
    ORDER BY mes;
    """)

    print("\n📊 DATOS FINALES EN LOCAL:")
    for row in local_cursor.fetchall():
        print(f"  {row[0]}: {row[1]:>8,} registros")
        sys.stdout.flush()

    remote_cursor.close()
    local_cursor.close()
    remote_conn.close()
    local_conn.close()

    print("\n✅ PROCESO COMPLETADO")
    sys.stdout.flush()

if __name__ == '__main__':
    main()
