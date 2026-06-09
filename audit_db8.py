import os, sys
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
import django
django.setup()

from django.db import connection

print("=== DGA - ESTADO DE ENVÍO POR DÍA (PUNTO 1) ===")
with connection.cursor() as cursor:
    cursor.execute("""
        SELECT 
            DATE(date_time_medition) as dia,
            COUNT(*) as total,
            SUM(CASE WHEN return_dga IS NOT NULL THEN 1 ELSE 0 END) as enviados,
            SUM(CASE WHEN return_dga IS NULL THEN 1 ELSE 0 END) as pendientes
        FROM core_interactiondetail
        WHERE catchment_point_id = 1
            AND date_time_medition > '2026-01-01'
        GROUP BY DATE(date_time_medition)
        ORDER BY dia DESC
        LIMIT 10
    """)
    for row in cursor.fetchall():
        pct = (row[2] / row[1] * 100) if row[1] > 0 else 0
        print(f"  {row[0]}: total={row[1]} | enviados={row[2]} | pendientes={row[3]} | {pct:.0f}% enviado")

print("\n=== DGA - PENDIENTES POR PUNTO (TOP 10) ===")
with connection.cursor() as cursor:
    cursor.execute("""
        SELECT 
            catchment_point_id,
            COUNT(*) as pendientes,
            MIN(date_time_medition) as mas_antiguo,
            MAX(date_time_medition) as mas_reciente
        FROM core_interactiondetail
        WHERE send_dga = true AND return_dga IS NULL
        GROUP BY catchment_point_id
        ORDER BY pendientes DESC
        LIMIT 10
    """)
    for row in cursor.fetchall():
        print(f"  Punto {row[0]}: {row[1]:,} pendientes | desde {row[2]} | hasta {row[3]}")

print("\n=== MASSIVE_JUMP - TENDENCIA SEMANAL ===")
with connection.cursor() as cursor:
    cursor.execute("""
        SELECT 
            DATE_TRUNC('week', date_time_medition) as semana,
            COUNT(*) as total
        FROM core_counterresetlog
        WHERE reset_type = 'MASSIVE_JUMP'
            AND date_time_medition > NOW() - INTERVAL '90 days'
        GROUP BY DATE_TRUNC('week', date_time_medition)
        ORDER BY semana DESC
    """)
    for row in cursor.fetchall():
        print(f"  Semana {row[0].date()}: {row[1]} saltos")

print("\n=== CONTEO DE PUNTOS POR ESTADO ===")
with connection.cursor() as cursor:
    cursor.execute("""
        WITH estado AS (
            SELECT 
                cp.id,
                MAX(i.date_time_medition) as ultima,
                COUNT(i.id) as total_regs
            FROM core_catchmentpoint cp
            LEFT JOIN core_interactiondetail i ON i.catchment_point_id = cp.id
            GROUP BY cp.id
        )
        SELECT 
            SUM(CASE WHEN ultima > NOW() - INTERVAL '2 hours' THEN 1 ELSE 0 END) as activos,
            SUM(CASE WHEN ultima BETWEEN NOW() - INTERVAL '24 hours' AND NOW() - INTERVAL '2 hours' THEN 1 ELSE 0 END) as retrasados,
            SUM(CASE WHEN ultima < NOW() - INTERVAL '24 hours' THEN 1 ELSE 0 END) as desconectados,
            SUM(CASE WHEN total_regs = 0 THEN 1 ELSE 0 END) as sin_datos
        FROM estado
    """)
    row = cursor.fetchone()
    print(f"  Activos (<2h): {row[0]}")
    print(f"  Retrasados (2-24h): {row[1]}")
    print(f"  Desconectados (>24h): {row[2]}")
    print(f"  Sin datos: {row[3]}")
