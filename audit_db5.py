import os, sys
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
import django
django.setup()

from django.db import connection

print("=== PUNTO 1 - DGA PENDIENTE (primeros 5 registros) ===")
with connection.cursor() as cursor:
    cursor.execute("""
        SELECT id, date_time_medition, total, flow, is_error, send_dga, return_dga
        FROM core_interactiondetail
        WHERE catchment_point_id = 1 AND send_dga = true AND return_dga IS NULL
        ORDER BY date_time_medition
        LIMIT 5
    """)
    for row in cursor.fetchall():
        print(f"  ID={row[0]} | fecha={row[1]} | total={row[2]} | flow={row[3]} | error={row[4]} | send={row[5]} | return={row[6]}")

print("\n=== PUNTO 1 - DGA PENDIENTE POR FECHA ===")
with connection.cursor() as cursor:
    cursor.execute("""
        SELECT DATE(date_time_medition) as dia, COUNT(*) as total
        FROM core_interactiondetail
        WHERE catchment_point_id = 1 AND send_dga = true AND return_dga IS NULL
        GROUP BY DATE(date_time_medition)
        ORDER BY dia
        LIMIT 10
    """)
    for row in cursor.fetchall():
        print(f"  {row[0]}: {row[1]:,} registros")

print("\n=== PUNTOS 125-128, 41, 135 - DETALLE DE ERRORES ===")
with connection.cursor() as cursor:
    cursor.execute("""
        SELECT 
            catchment_point_id,
            COUNT(*) as total,
            SUM(CASE WHEN total_diff < 0 THEN 1 ELSE 0 END) as neg_diff,
            SUM(CASE WHEN flow = 0 AND total_diff > 0 THEN 1 ELSE 0 END) as flow_zero_diff_pos,
            SUM(CASE WHEN total_diff > 10000 THEN 1 ELSE 0 END) as diff_masivo,
            AVG(total_diff) as avg_diff,
            MAX(total_diff) as max_diff
        FROM core_interactiondetail
        WHERE is_error = true 
            AND date_time_medition > NOW() - INTERVAL '7 days'
            AND catchment_point_id IN (41, 125, 126, 127, 128, 135)
        GROUP BY catchment_point_id
        ORDER BY total DESC
    """)
    for row in cursor.fetchall():
        print(f"  Punto {row[0]}: total={row[1]} | neg_diff={row[2]} | flow_zero={row[3]} | diff_masivo={row[4]} | avg_diff={row[5]:.1f} | max_diff={row[6]}")

print("\n=== PUNTOS SIN REGISTROS - DETALLE ===")
with connection.cursor() as cursor:
    cursor.execute("""
        SELECT cp.id, cp.title, cp.frecuency, t.name as provider
        FROM core_catchmentpoint cp
        LEFT JOIN core_telemetryprovider t ON t.id = cp.telemetry_provider_id
        JOIN core_profiledataconfigcatchment p ON p.point_catchment_id = cp.id AND p.is_telemetry = true
        LEFT JOIN core_interactiondetail id ON id.catchment_point_id = cp.id
        WHERE id.id IS NULL
        ORDER BY cp.id
    """)
    for row in cursor.fetchall():
        print(f"  Punto {row[0]} ({row[1]}): frec={row[2]} | provider={row[3]}")

print("\n=== PUNTOS DESCONECTADOS > 30 DÍAS ===")
with connection.cursor() as cursor:
    cursor.execute("""
        WITH ultimas AS (
            SELECT catchment_point_id, MAX(date_time_medition) as ultima
            FROM core_interactiondetail
            GROUP BY catchment_point_id
        )
        SELECT cp.id, cp.title, cp.frecuency, u.ultima,
            ROUND(EXTRACT(EPOCH FROM (NOW() - u.ultima))/3600/24, 1) as dias
        FROM core_catchmentpoint cp
        JOIN core_profiledataconfigcatchment p ON p.point_catchment_id = cp.id AND p.is_telemetry = true
        LEFT JOIN ultimas u ON u.catchment_point_id = cp.id
        WHERE EXTRACT(EPOCH FROM (NOW() - u.ultima))/3600/24 > 30 OR u.ultima IS NULL
        ORDER BY dias DESC NULLS LAST
    """)
    for row in cursor.fetchall():
        print(f"  Punto {row[0]} ({row[1]}): frec={row[2]} | última={row[3]} | días={row[4]}")

print("\n=== CONFIG DGA POR PUNTO (puntos con mucho pendiente) ===")
with connection.cursor() as cursor:
    cursor.execute("""
        SELECT cp.id, cp.title, d.send_dga, d.standard, d.type_dga
        FROM core_catchmentpoint cp
        LEFT JOIN core_dgadataconfigcatchment d ON d.point_catchment_id = cp.id
        WHERE cp.id IN (1, 41, 135, 141)
    """)
    for row in cursor.fetchall():
        print(f"  Punto {row[0]} ({row[1]}): send_dga={row[2]} | standard={row[3]} | type={row[4]}")
