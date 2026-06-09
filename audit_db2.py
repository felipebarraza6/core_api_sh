import os, sys
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
import django
django.setup()

from django.db import connection
from django.utils import timezone

print("=== PUNTOS CON TELEMETRÍA ACTIVA - ÚLTIMA MEDICIÓN ===")
with connection.cursor() as cursor:
    cursor.execute("""
        WITH ultimas AS (
            SELECT catchment_point_id, MAX(date_time_medition) as ultima
            FROM core_interactiondetail
            GROUP BY catchment_point_id
        )
        SELECT cp.id, cp.title, cp.frecuency, u.ultima,
            EXTRACT(EPOCH FROM (NOW() - u.ultima))/3600 as horas
        FROM core_catchmentpoint cp
        JOIN core_profiledataconfigcatchment p ON p.point_catchment_id = cp.id AND p.is_telemetry = true
        LEFT JOIN ultimas u ON u.catchment_point_id = cp.id
        ORDER BY horas DESC NULLS LAST
        LIMIT 20
    """)
    for row in cursor.fetchall():
        horas = row[4]
        estado = 'OK' if horas is not None and horas <= 2 else ('⚠️' if horas is not None and horas <= 24 else '🔴')
        horas_str = f"{horas:.1f}" if horas is not None else "N/A"
        print(f"  Punto {row[0]} ({row[1]}): frec={row[2]} | última={row[3]} | h={horas_str} | {estado}")

print("\n=== ERRORES RECIENTES EN TELEMETRÍA ===")
with connection.cursor() as cursor:
    cursor.execute("""
        SELECT catchment_point_id, COUNT(*) as errores
        FROM core_interactiondetail
        WHERE is_error = true AND date_time_medition > NOW() - INTERVAL '7 days'
        GROUP BY catchment_point_id
        ORDER BY errores DESC
        LIMIT 10
    """)
    rows = cursor.fetchall()
    if rows:
        for row in rows:
            print(f"  Punto {row[0]}: {row[1]} errores en últimos 7 días")
    else:
        print("  Sin errores recientes")

print("\n=== PUNTOS SIN REGISTROS (NUNCA TUVIERON TELEMETRÍA) ===")
with connection.cursor() as cursor:
    cursor.execute("""
        SELECT cp.id, cp.title
        FROM core_catchmentpoint cp
        JOIN core_profiledataconfigcatchment p ON p.point_catchment_id = cp.id AND p.is_telemetry = true
        LEFT JOIN core_interactiondetail id ON id.catchment_point_id = cp.id
        WHERE id.id IS NULL
        ORDER BY cp.id
    """)
    rows = cursor.fetchall()
    if rows:
        for row in rows:
            print(f"  Punto {row[0]} ({row[1]}): SIN REGISTROS")
    else:
        print("  Todos los puntos con telemetría activa tienen al menos un registro.")

print("\n=== TOP 10 PUNTOS CON MÁS REGISTROS ===")
with connection.cursor() as cursor:
    cursor.execute("""
        SELECT catchment_point_id, COUNT(*) as total
        FROM core_interactiondetail
        GROUP BY catchment_point_id
        ORDER BY total DESC
        LIMIT 10
    """)
    for row in cursor.fetchall():
        print(f"  Punto {row[0]}: {row[1]:,} registros")

print("\n=== RESETS RECIENTES ===")
with connection.cursor() as cursor:
    cursor.execute("""
        SELECT reset_type, COUNT(*) as total
        FROM core_counterresetlog
        WHERE date_time_medition > NOW() - INTERVAL '7 days'
        GROUP BY reset_type
        ORDER BY total DESC
    """)
    rows = cursor.fetchall()
    if rows:
        for row in rows:
            print(f"  {row[0]}: {row[1]} en últimos 7 días")
    else:
        print("  Sin resets recientes")

print("\n=== VARIABLES POR TIPO ===")
with connection.cursor() as cursor:
    cursor.execute("""
        SELECT type_variable, COUNT(*) as total
        FROM core_variable
        GROUP BY type_variable
        ORDER BY total DESC
    """)
    for row in cursor.fetchall():
        print(f"  {row[0]}: {row[1]}")

print("\n=== PUNTOS CON DGA PENDIENTE (más de 1000 registros) ===")
with connection.cursor() as cursor:
    cursor.execute("""
        SELECT catchment_point_id, COUNT(*) as total
        FROM core_interactiondetail
        WHERE send_dga = true AND return_dga IS NULL
        GROUP BY catchment_point_id
        HAVING COUNT(*) > 1000
        ORDER BY total DESC
        LIMIT 10
    """)
    rows = cursor.fetchall()
    if rows:
        for row in rows:
            print(f"  Punto {row[0]}: {row[1]:,} registros DGA pendientes")
    else:
        print("  Ningún punto con más de 1000 registros DGA pendientes")

print("\n=== PUNTOS CON ERRORES CRÓNICOS (>100 errores en 7 días) ===")
with connection.cursor() as cursor:
    cursor.execute("""
        SELECT catchment_point_id, COUNT(*) as total
        FROM core_interactiondetail
        WHERE is_error = true AND date_time_medition > NOW() - INTERVAL '7 days'
        GROUP BY catchment_point_id
        HAVING COUNT(*) > 100
        ORDER BY total DESC
        LIMIT 10
    """)
    rows = cursor.fetchall()
    if rows:
        for row in rows:
            print(f"  Punto {row[0]}: {row[1]} errores en 7 días")
    else:
        print("  Ningún punto con más de 100 errores en 7 días")
