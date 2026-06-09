import os, sys
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
import django
django.setup()

from django.db import connection

print("=== PUNTOS CON PROVIDER PERO SIN TELEMETRÍA ACTIVA ===")
with connection.cursor() as cursor:
    cursor.execute("""
        SELECT cp.id, cp.title, t.name as provider
        FROM core_catchmentpoint cp
        JOIN core_telemetryprovider t ON t.id = cp.telemetry_provider_id
        LEFT JOIN core_profiledataconfigcatchment p ON p.point_catchment_id = cp.id AND p.is_telemetry = true
        WHERE p.id IS NULL AND cp.telemetry_provider_id IS NOT NULL
        ORDER BY cp.id
    """)
    rows = cursor.fetchall()
    if rows:
        for row in rows:
            print(f"  Punto {row[0]} ({row[1]}): provider={row[2]} pero telemetría INACTIVA")
    else:
        print("  Todos los puntos con provider tienen telemetría activa")

print("\n=== PUNTOS CON FRECUENCIA = 1 (cada minuto) ===")
with connection.cursor() as cursor:
    cursor.execute("""
        SELECT cp.id, cp.title
        FROM core_catchmentpoint cp
        JOIN core_profiledataconfigcatchment p ON p.point_catchment_id = cp.id AND p.is_telemetry = true
        WHERE cp.frecuency = '1'
        ORDER BY cp.id
    """)
    rows = cursor.fetchall()
    if rows:
        for row in rows:
            print(f"  Punto {row[0]} ({row[1]}): frecuencia 1 minuto")
    else:
        print("  Ningún punto con frecuencia 1 minuto")

print("\n=== DGA PENDIENTE POR PUNTO (top 10) ===")
with connection.cursor() as cursor:
    cursor.execute("""
        SELECT catchment_point_id, COUNT(*) as total
        FROM core_interactiondetail
        WHERE send_dga = true AND return_dga IS NULL
        GROUP BY catchment_point_id
        ORDER BY total DESC
        LIMIT 10
    """)
    for row in cursor.fetchall():
        print(f"  Punto {row[0]}: {row[1]:,} registros DGA pendientes")

print("\n=== TELEMETRÍA POR PROVIDER ===")
with connection.cursor() as cursor:
    cursor.execute("""
        SELECT 
            COALESCE(t.name, 'SIN PROVIDER') as provider,
            COUNT(DISTINCT cp.id) as puntos,
            COUNT(id.id) as registros_hoy
        FROM core_catchmentpoint cp
        LEFT JOIN core_telemetryprovider t ON t.id = cp.telemetry_provider_id
        LEFT JOIN core_interactiondetail id ON id.catchment_point_id = cp.id AND id.date_time_medition::date = CURRENT_DATE
        GROUP BY t.name
        ORDER BY puntos DESC
    """)
    for row in cursor.fetchall():
        print(f"  {row[0]}: {row[1]} puntos, {row[2] or 0} registros hoy")

print("\n=== PUNTOS CON MÁS DE 50 ERRORES EN 7 DÍAS (detalle) ===")
with connection.cursor() as cursor:
    cursor.execute("""
        SELECT 
            i.catchment_point_id,
            COUNT(*) as total_errores,
            MAX(i.date_time_medition) as ultimo_error,
            STRING_AGG(DISTINCT i.days_not_conection::text, ', ') as dias_desconexion
        FROM core_interactiondetail i
        WHERE i.is_error = true 
            AND i.date_time_medition > NOW() - INTERVAL '7 days'
        GROUP BY i.catchment_point_id
        HAVING COUNT(*) > 50
        ORDER BY total_errores DESC
    """)
    for row in cursor.fetchall():
        print(f"  Punto {row[0]}: {row[1]} errores | último={row[2]} | días_desc={row[3]}")
