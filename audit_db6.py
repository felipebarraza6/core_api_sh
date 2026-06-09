import os, sys
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
import django
django.setup()

from django.db import connection

print("=== PUNTO 1 - DGA: ÚLTIMO ENVÍO EXITOSO ===")
with connection.cursor() as cursor:
    cursor.execute("""
        SELECT MAX(date_time_medition) as ultimo_enviado
        FROM core_interactiondetail
        WHERE catchment_point_id = 1 AND return_dga IS NOT NULL
    """)
    row = cursor.fetchone()
    print(f"  Último envío DGA exitoso: {row[0]}")

print("\n=== PUNTO 1 - DGA: ERRORES DE ENVÍO ===")
with connection.cursor() as cursor:
    cursor.execute("""
        SELECT COUNT(*) as total
        FROM core_interactiondetail
        WHERE catchment_point_id = 1 AND send_dga = true AND return_dga IS NULL
            AND date_time_medition < NOW() - INTERVAL '1 day'
    """)
    row = cursor.fetchone()
    print(f"  Registros DGA pendientes >24h: {row[0]:,}")

print("\n=== PUNTOS CON MASSIVE_JUMP > 30 EN 7 DÍAS - CONFIG ===")
with connection.cursor() as cursor:
    cursor.execute("""
        SELECT 
            cp.id, cp.title, cp.frecuency,
            p.addition, p.max_diff_m3_per_hour, p.max_flow_ls,
            p.max_time_gap_hours, p.reconnection_threshold_hours
        FROM core_catchmentpoint cp
        JOIN core_profiledataconfigcatchment p ON p.point_catchment_id = cp.id
        WHERE cp.id IN (41, 135, 141, 1, 146, 64, 61, 62, 63, 125)
    """)
    for row in cursor.fetchall():
        print(f"  Punto {row[0]} ({row[1]}): frec={row[2]} | addition={row[3]} | max_diff={row[4]} | max_flow={row[5]} | max_gap={row[6]}h | recon={row[7]}h")

print("\n=== ERRORES 'is_error' ÚLTIMOS 30 DÍAS - TENDENCIA ===")
with connection.cursor() as cursor:
    cursor.execute("""
        SELECT DATE(date_time_medition) as dia, COUNT(*) as total
        FROM core_interactiondetail
        WHERE is_error = true AND date_time_medition > NOW() - INTERVAL '30 days'
        GROUP BY DATE(date_time_medition)
        ORDER BY dia DESC
        LIMIT 10
    """)
    for row in cursor.fetchall():
        print(f"  {row[0]}: {row[1]} errores")

print("\n=== PUNTOS CON VARIABLES MAL CONFIGURADAS ===")
with connection.cursor() as cursor:
    cursor.execute("""
        SELECT 
            v.scheme_catchment_id,
            COUNT(*) as total_vars,
            SUM(CASE WHEN v.token_service IS NULL OR v.token_service = '' THEN 1 ELSE 0 END) as sin_token,
            SUM(CASE WHEN v.pulses_factor IS NULL OR v.pulses_factor = 0 THEN 1 ELSE 0 END) as sin_factor
        FROM core_variable v
        GROUP BY v.scheme_catchment_id
        HAVING COUNT(*) > 0
        ORDER BY sin_token DESC
        LIMIT 10
    """)
    for row in cursor.fetchall():
        print(f"  Esquema {row[0]}: {row[1]} vars | sin_token={row[2]} | sin_factor={row[3]}")
