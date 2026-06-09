import os, sys
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
import django
django.setup()

from django.db import connection
from api.core.models import CatchmentPoint, InteractionDetail, CounterResetLog, AlertRule, SupportTicket
from api.core.models import ProfileDataConfigCatchment
from django.db.models import Max, Count, Q, F
from django.utils import timezone
from datetime import timedelta

print("=== ESTADÍSTICAS GENERALES ===")
print(f"Total puntos: {CatchmentPoint.objects.count()}")
print(f"Puntos con telemetría activa: {ProfileDataConfigCatchment.objects.filter(is_telemetry=True).count()}")
print(f"Puntos con provider asignado: {CatchmentPoint.objects.filter(telemetry_provider__isnull=False).count()}")
print(f"Puntos sin provider: {CatchmentPoint.objects.filter(telemetry_provider__isnull=True).count()}")
print(f"Puntos sin proyecto: {CatchmentPoint.objects.filter(project__isnull=True).count()}")
print(f"Puntos sin owner: {CatchmentPoint.objects.filter(owner_user__isnull=True).count()}")
print(f"Total registros telemetry: {InteractionDetail.objects.count()}")
print(f"Registros hoy: {InteractionDetail.objects.filter(date_time_medition__date=timezone.now().date()).count()}")
print(f"Registros con is_error=true: {InteractionDetail.objects.filter(is_error=True).count()}")
print(f"Registros sin enviar DGA: {InteractionDetail.objects.filter(send_dga=True, return_dga__isnull=True).count()}")
print(f"Logs de reset: {CounterResetLog.objects.count()}")
print(f"AlertRules activas: {AlertRule.objects.filter(is_active=True).count()}")
print(f"Tickets abiertos: {SupportTicket.objects.filter(status__in=['ABIERTO','EN_ANALISIS'], is_active=True).count()}")

print("\n=== PUNTOS CON TELEMETRÍA ACTIVA - ÚLTIMA MEDICIÓN ===")
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
        estado = 'OK' if row[4] is not None and row[4] <= 2 else ('⚠️' if row[4] is not None and row[4] <= 24 else '🔴')
        print(f"  Punto {row[0]} ({row[1]}): frec={row[2]} | última={row[3]} | h={row[4]:.1f if row[4] else 'N/A'} | {estado}")

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
    for row in cursor.fetchall():
        print(f"  Punto {row[0]}: {row[1]} errores en últimos 7 días")

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
    for row in cursor.fetchall():
        print(f"  {row[0]}: {row[1]} en últimos 7 días")

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
