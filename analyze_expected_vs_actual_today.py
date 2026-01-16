#!/usr/bin/env python
"""
Analiza cuántos datos debería tener cada punto hoy según su frecuencia
versus cuántos datos tiene realmente.
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
from django.db.models import Count, Max

def parse_frecuency(frecuency_str):
    """Convierte string de frecuencia a minutos."""
    if not frecuency_str:
        return None

    frecuency_str = str(frecuency_str).strip().upper()

    # Mapeo de frecuencias conocidas
    frecuency_map = {
        '60MIN': 60,
        '60': 60,
        '10MIN': 10,
        '10': 10,
        '5MIN': 5,
        '5': 5,
        '1MIN': 1,
        '1': 1,
        'HOURLY': 60,
        'DAILY': 1440,
    }

    return frecuency_map.get(frecuency_str, None)

def calculate_expected_records(frecuency_minutes, hours=24):
    """Calcula registros esperados según frecuencia."""
    if not frecuency_minutes or frecuency_minutes == 0:
        return 0

    total_minutes = hours * 60
    return total_minutes // frecuency_minutes

def main():
    # Fecha de hoy (desde 00:00:00 hasta 23:59:59)
    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)

    print(f"\n{'='*100}")
    print(f"ANÁLISIS DE DATOS ESPERADOS VS REALES - {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*100}")
    print(f"Período analizado: {today_start.strftime('%Y-%m-%d %H:%M')} hasta {today_end.strftime('%Y-%m-%d %H:%M')}")
    print(f"Hora actual: {now.strftime('%H:%M:%S')} (se esperan datos hasta esta hora)\n")

    # Obtener todos los puntos (no hay campo is_active en CatchmentPoint)
    points = CatchmentPoint.objects.all().order_by('pk')

    print(f"Total de puntos activos: {points.count()}\n")
    print(f"{'ID':<6} {'Nombre':<35} {'Frecuencia':<12} {'Esperados':<12} {'Reales':<12} {'Diferencia':<12} {'%':<8} {'Último dato':<20}")
    print(f"{'-'*6} {'-'*35} {'-'*12} {'-'*12} {'-'*12} {'-'*12} {'-'*8} {'-'*20}")

    total_expected = 0
    total_actual = 0
    points_with_data = 0
    points_without_data = 0
    points_with_missing_data = 0

    for point in points:
        # Obtener frecuencia en minutos
        frecuency_minutes = parse_frecuency(point.frecuency)

        if not frecuency_minutes:
            # Si no tiene frecuencia configurada, saltar
            continue

        # Calcular registros esperados (solo hasta la hora actual)
        hours_elapsed = (now - today_start).total_seconds() / 3600
        expected = calculate_expected_records(frecuency_minutes, hours_elapsed)

        # Contar registros reales de hoy
        actual = InteractionDetail.objects.filter(
            catchment_point=point,
            created__gte=today_start,
            created__lte=now
        ).count()

        # Obtener último dato
        last_record = InteractionDetail.objects.filter(
            catchment_point=point
        ).aggregate(Max('created'))['created__max']

        last_str = last_record.strftime('%Y-%m-%d %H:%M') if last_record else 'Sin datos'

        # Calcular diferencia
        diff = actual - expected
        percentage = (actual / expected * 100) if expected > 0 else 0

        # Estadísticas
        total_expected += expected
        total_actual += actual

        if actual > 0:
            points_with_data += 1
        else:
            points_without_data += 1

        if actual < expected * 0.9:  # Menos del 90% de datos esperados
            points_with_missing_data += 1

        # Color coding para la terminal
        if actual == 0:
            status = "🔴"
        elif actual < expected * 0.5:
            status = "🟠"
        elif actual < expected * 0.9:
            status = "🟡"
        else:
            status = "🟢"

        name = (point.title or f"Punto {point.pk}")[:34]
        print(f"{point.pk:<6} {name:<35} {point.frecuency or 'N/A':<12} {expected:<12} {actual:<12} {diff:+<12} {percentage:>6.1f}% {last_str:<20} {status}")

    # Resumen
    print(f"\n{'='*100}")
    print(f"RESUMEN")
    print(f"{'='*100}")
    print(f"Total registros esperados (parcial): {total_expected:,}")
    print(f"Total registros reales:               {total_actual:,}")
    print(f"Diferencia:                           {total_actual - total_expected:+,}")
    print(f"Porcentaje de completitud:            {(total_actual / total_expected * 100) if total_expected > 0 else 0:.1f}%")
    print(f"\nPuntos con datos hoy:                 {points_with_data}")
    print(f"Puntos sin datos hoy:                 {points_without_data}")
    print(f"Puntos con datos faltantes (< 90%):   {points_with_missing_data}")

    # Análisis por frecuencia
    print(f"\n{'='*100}")
    print(f"ANÁLISIS POR FRECUENCIA")
    print(f"{'='*100}")
    print(f"{'Frecuencia':<15} {'Puntos':<10} {'Esperados':<15} {'Reales':<15} {'Completitud':<15}")
    print(f"{'-'*15} {'-'*10} {'-'*15} {'-'*15} {'-'*15}")

    # Agrupar por frecuencia
    frecuency_stats = {}
    for point in points:
        freq = point.frecuency or 'N/A'
        frecuency_minutes = parse_frecuency(freq)

        if not frecuency_minutes:
            continue

        hours_elapsed = (now - today_start).total_seconds() / 3600
        expected = calculate_expected_records(frecuency_minutes, hours_elapsed)
        actual = InteractionDetail.objects.filter(
            catchment_point=point,
            created__gte=today_start,
            created__lte=now
        ).count()

        if freq not in frecuency_stats:
            frecuency_stats[freq] = {
                'points': 0,
                'expected': 0,
                'actual': 0
            }

        frecuency_stats[freq]['points'] += 1
        frecuency_stats[freq]['expected'] += expected
        frecuency_stats[freq]['actual'] += actual

    for freq, stats in sorted(frecuency_stats.items()):
        completeness = (stats['actual'] / stats['expected'] * 100) if stats['expected'] > 0 else 0
        print(f"{freq:<15} {stats['points']:<10} {stats['expected']:<15,} {stats['actual']:<15,} {completeness:>13.1f}%")

    print(f"\n{'='*100}")
    print(f"Leyenda: 🟢 >= 90% | 🟡 50-90% | 🟠 < 50% | 🔴 Sin datos")
    print(f"{'='*100}\n")

if __name__ == '__main__':
    main()
