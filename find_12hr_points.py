#!/usr/bin/env python
"""
Busca puntos con último dato alrededor de las 12:00
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
from django.db.models import Max

def main():
    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    print(f"\n{'='*120}")
    print(f"PUNTOS CON ÚLTIMO DATO ENTRE LAS 12:00 Y 13:00 DE HOY")
    print(f"{'='*120}\n")

    points = CatchmentPoint.objects.all()

    points_12hr = []

    for point in points:
        last_record = InteractionDetail.objects.filter(
            catchment_point=point
        ).order_by('-created').first()

        if last_record:
            # Si el último dato es de hoy y entre las 12:00 y 13:00
            if (last_record.created >= today_start and
                last_record.created.hour >= 12 and
                last_record.created.hour < 13):

                points_12hr.append({
                    'id': point.pk,
                    'name': point.title or f"Punto {point.pk}",
                    'last_time': last_record.created,
                    'frecuency': point.frecuency
                })

    if not points_12hr:
        print("❌ No se encontraron puntos con último dato entre 12:00 y 13:00")

        # Buscar cualquier punto con último dato de hoy antes de las 15:00
        print(f"\n{'='*120}")
        print(f"PUNTOS CON ÚLTIMO DATO HOY ANTES DE LAS 15:00")
        print(f"{'='*120}\n")

        points_early = []

        for point in points:
            last_record = InteractionDetail.objects.filter(
                catchment_point=point
            ).order_by('-created').first()

            if last_record:
                if (last_record.created >= today_start and
                    last_record.created.hour < 15):

                    points_early.append({
                        'id': point.pk,
                        'name': point.title or f"Punto {point.pk}",
                        'last_time': last_record.created,
                        'frecuency': point.frecuency
                    })

        if points_early:
            print(f"{'ID':<6} {'Nombre':<40} {'Frecuencia':<12} {'Último dato':<20}")
            print(f"{'-'*6} {'-'*40} {'-'*12} {'-'*20}")

            for p in sorted(points_early, key=lambda x: x['last_time']):
                print(f"{p['id']:<6} {p['name'][:39]:<40} {p['frecuency'] or 'N/A':<12} {p['last_time'].strftime('%H:%M:%S'):<20}")

        return

    print(f"Total de puntos encontrados: {len(points_12hr)}\n")
    print(f"{'ID':<6} {'Nombre':<40} {'Frecuencia':<12} {'Último dato':<20}")
    print(f"{'-'*6} {'-'*40} {'-'*12} {'-'*20}")

    for p in sorted(points_12hr, key=lambda x: x['last_time']):
        print(f"{p['id']:<6} {p['name'][:39]:<40} {p['frecuency'] or 'N/A':<12} {p['last_time'].strftime('%H:%M:%S'):<20}")

    # También buscar en nombres que puedan ser "jce"
    print(f"\n{'='*120}")
    print(f"BUSCANDO POSIBLES COINCIDENCIAS CON 'JCE'")
    print(f"{'='*120}\n")

    possible_matches = [
        'jce', 'j.c.e', 'j c e', 'jose', 'juanita', 'jorge',
        'san jose', 'juan', 'jacobo', 'jacinto'
    ]

    found_any = False
    for search_term in possible_matches:
        matches = CatchmentPoint.objects.filter(title__icontains=search_term)
        if matches.exists():
            found_any = True
            print(f"\n🔍 Coincidencias con '{search_term}':")
            for point in matches:
                last_record = InteractionDetail.objects.filter(
                    catchment_point=point
                ).order_by('-created').first()

                last_str = last_record.created.strftime('%Y-%m-%d %H:%M:%S') if last_record else 'Sin datos'
                print(f"   ID {point.pk}: {point.title} - Último: {last_str}")

    if not found_any:
        print("❌ No se encontraron coincidencias")

if __name__ == '__main__':
    main()
