import os, sys
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
import django
django.setup()

from django.db import connection

print("=== PUNTO 1 - ADDITION HISTÓRICO ===")
with connection.cursor() as cursor:
    cursor.execute("""
        SELECT 
            DATE(date_time_medition) as dia,
            COUNT(*) as registros,
            MAX(total) as max_total,
            MIN(total) as min_total,
            MAX(total_diff) as max_diff
        FROM core_interactiondetail
        WHERE catchment_point_id = 1
            AND date_time_medition > NOW() - INTERVAL '7 days'
        GROUP BY DATE(date_time_medition)
        ORDER BY dia DESC
    """)
    for row in cursor.fetchall():
        print(f"  {row[0]}: regs={row[1]} | total_max={row[2]} | total_min={row[3]} | max_diff={row[4]}")

print("\n=== FLOW=0 CON TOTAL_DIFF>0 (últimos 7 días) ===")
with connection.cursor() as cursor:
    cursor.execute("""
        SELECT 
            catchment_point_id,
            COUNT(*) as total,
            AVG(total_diff) as avg_diff,
            MAX(total_diff) as max_diff
        FROM core_interactiondetail
        WHERE flow = 0 
            AND total_diff > 0
            AND date_time_medition > NOW() - INTERVAL '7 days'
        GROUP BY catchment_point_id
        HAVING COUNT(*) > 10
        ORDER BY total DESC
        LIMIT 10
    """)
    for row in cursor.fetchall():
        print(f"  Punto {row[0]}: {row[1]} casos | avg_diff={row[2]:.1f} | max_diff={row[3]}")

print("\n=== VARIABLES POR PUNTO PROBLEMÁTICO ===")
with connection.cursor() as cursor:
    cursor.execute("""
        SELECT 
            v.id, v.str_variable, v.type_variable, v.token_service, v.pulses_factor,
            s.name as scheme_name
        FROM core_variable v
        JOIN core_schemescatchment s ON s.id = v.scheme_catchment_id
        JOIN core_schemescatchment_points_catchment scp ON scp.schemescatchment_id = s.id
        WHERE scp.catchmentpoint_id IN (1, 41, 125, 127, 128, 135)
        ORDER BY scp.catchmentpoint_id, v.type_variable
    """)
    for row in cursor.fetchall():
        print(f"  Var {row[0]} ({row[1]}): type={row[2]} | token={row[3] if row[3] else 'SIN_TOKEN'} | factor={row[4]} | scheme={row[5]}")
