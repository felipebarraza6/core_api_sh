#!/usr/bin/env python
"""
Busca y analiza el punto JCE
"""
import os
import sys
import django
from datetime import datetime, timedelta
from django.utils import timezone

# Setup Django
sys.path.insert(0, '/root/core_api_sh')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import CatchmentPoint, InteractionDetail
from django.db.models import Count, Max, Min

def main():
    # Buscar puntos con "jce" en el nombre
    points = CatchmentPoint.objects.filter(title__icontains='jce')

    if not points.exists():
        print("No se encontraron puntos con 'jce' en el nombre")
        print("\nBuscando otros posibles puntos...")
        # Buscar por similares
        similar = CatchmentPoint.objects.filter(
            title__icontains='j'
        ).filter(
            title__icontains='c'
        ).filter(
            title__icontains='e'
        )
        if similar.exists():
            print(f"\nPuntos similares encontrados: {similar.count()}")
            for p in similar[:20]:
                print(f"  ID {p.pk}: {p.title}")
        return

    print(f"{'='*120}")
    print(f"ANÁLISIS DE PUNTOS JCE")
    print(f"{'='*120}\n")

    for point in points:
        print(f"\n{'='*120}")
        print(f"PUNTO ID: {point.pk}")
        print(f"Nombre: {point.title}")
        print(f"Frecuencia: {point.frecuency}")
        print(f"Proyecto: {point.project.name if point.project else 'N/A'}")
        print(f"Propietario: {point.owner_user}")
        print(f"Provider: TWIN={point.is_tdata}, NETTRA={point.is_thethings}, NOVUS={point.is_novus}")
        print(f"{'='*120}")

        # Obtener estadísticas de datos
        total_records = InteractionDetail.objects.filter(catchment_point=point).count()

        if total_records == 0:
            print("\n❌ NO HAY DATOS PARA ESTE PUNTO")
            continue

        print(f"\nTotal de registros históricos: {total_records:,}")

        # Último dato
        last_record = InteractionDetail.objects.filter(
            catchment_point=point
        ).order_by('-created').first()

        if last_record:
            print(f"\n📅 ÚLTIMO DATO REGISTRADO:")
            print(f"   Fecha/hora creación: {last_record.created}")
            print(f"   Fecha/hora medición: {last_record.date_time_medition}")
            print(f"   Fecha/hora logger: {last_record.date_time_last_logger}")
            print(f"   Caudal: {last_record.flow}")
            print(f"   Total: {last_record.total}")
            print(f"   Total diff: {last_record.total_diff}")
            print(f"   Nivel: {last_record.nivel}")
            print(f"   Pulsos: {last_record.pulses}")
            print(f"   Send DGA: {last_record.send_dga}")
            print(f"   Is error: {last_record.is_error}")

            # Calcular tiempo desde último dato
            now = timezone.now()
            time_since = now - last_record.created
            hours_since = time_since.total_seconds() / 3600

            print(f"\n⏰ TIEMPO TRANSCURRIDO:")
            print(f"   Hace: {hours_since:.1f} horas ({time_since.days} días, {time_since.seconds // 3600} horas, {(time_since.seconds % 3600) // 60} minutos)")

            if hours_since > 6:
                print(f"   ⚠️ ALERTA: Más de 6 horas sin datos")

        # Datos de hoy
        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_records = InteractionDetail.objects.filter(
            catchment_point=point,
            created__gte=today_start
        ).order_by('created')

        print(f"\n📊 DATOS DE HOY ({today_start.strftime('%Y-%m-%d')}):")
        print(f"   Total registros hoy: {today_records.count()}")

        if today_records.exists():
            first_today = today_records.first()
            last_today = today_records.last()

            print(f"   Primer dato: {first_today.created.strftime('%H:%M:%S')}")
            print(f"   Último dato: {last_today.created.strftime('%H:%M:%S')}")

            # Últimos 10 registros de hoy
            print(f"\n   📋 ÚLTIMOS 10 REGISTROS DE HOY:")
            print(f"   {'Hora':<20} {'Caudal':<10} {'Total':<15} {'Diff':<10} {'Nivel':<10} {'Error':<8}")
            print(f"   {'-'*20} {'-'*10} {'-'*15} {'-'*10} {'-'*10} {'-'*8}")

            for record in today_records.order_by('-created')[:10]:
                print(f"   {record.created.strftime('%Y-%m-%d %H:%M:%S'):<20} "
                      f"{str(record.flow):<10} "
                      f"{str(record.total or 'N/A'):<15} "
                      f"{record.total_diff:<10} "
                      f"{str(record.nivel):<10} "
                      f"{'❌' if record.is_error else '✅':<8}")
        else:
            print(f"   ❌ NO HAY DATOS HOY")

        # Datos de ayer
        yesterday_start = today_start - timedelta(days=1)
        yesterday_records = InteractionDetail.objects.filter(
            catchment_point=point,
            created__gte=yesterday_start,
            created__lt=today_start
        )

        print(f"\n📊 DATOS DE AYER ({yesterday_start.strftime('%Y-%m-%d')}):")
        print(f"   Total registros ayer: {yesterday_records.count()}")

        # Últimos 7 días
        week_ago = today_start - timedelta(days=7)
        week_records = InteractionDetail.objects.filter(
            catchment_point=point,
            created__gte=week_ago
        )

        print(f"\n📊 ÚLTIMOS 7 DÍAS:")
        print(f"   Total registros: {week_records.count()}")

        # Datos por día
        for i in range(7):
            day_start = today_start - timedelta(days=i)
            day_end = day_start + timedelta(days=1)
            day_count = InteractionDetail.objects.filter(
                catchment_point=point,
                created__gte=day_start,
                created__lt=day_end
            ).count()

            day_label = "HOY" if i == 0 else f"Hace {i} día{'s' if i > 1 else ''}"
            print(f"   {day_start.strftime('%Y-%m-%d')} ({day_label:<15}): {day_count:>4} registros")

        print(f"\n{'='*120}\n")

if __name__ == '__main__':
    main()
