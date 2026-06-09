#!/usr/bin/env python3
"""
FIX MONOTONICIDAD TOTAL — NOVUS/TagoIO
======================================

Para registros con pulses=0 + total vacío durante la crisis,
propaga el último total válido para mantener monotonicidad.

USO:
    docker exec -u root -w /app django_api_secure python scripts/fix_total_monotonicity_novus.py --dry-run
    docker exec -u root -w /app django_api_secure python scripts/fix_total_monotonicity_novus.py --force
"""

import os
import sys
import argparse

sys.path.insert(0, "/app")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.settings")
import django
django.setup()

from api.core.models import InteractionDetail


def log(msg):
    print(msg, flush=True)


def fix_point_monotonicity(point_id, start_dt, end_dt, dry_run=True):
    """
    Para un punto, encuentra registros con pulses=0 + total vacío en el rango
    y propaga el último total válido.
    """
    # Obtener TODOS los registros del punto ordenados
    records = list(
        InteractionDetail.objects.filter(
            catchment_point_id=point_id,
        ).order_by("date_time_medition").values(
            "id", "date_time_medition", "pulses", "total", "total_diff"
        )
    )

    if not records:
        return 0, 0

    last_valid_total = None
    affected_in_range = []

    for r in records:
        dt = r["date_time_medition"]
        in_range = start_dt <= dt < end_dt
        pulses = r["pulses"]
        total_str = r["total"]

        # Verificar si es un total válido
        is_valid_total = False
        current_total = None
        if total_str not in (None, "", "None"):
            try:
                current_total = float(total_str)
                if current_total > 0:
                    is_valid_total = True
            except (ValueError, TypeError):
                pass

        if is_valid_total:
            last_valid_total = current_total

        if in_range and pulses == 0 and not is_valid_total and last_valid_total is not None:
            affected_in_range.append({
                "id": r["id"],
                "dt": dt,
                "last_total": last_valid_total,
            })

    if not affected_in_range:
        return 0, 0

    log(f"  Punto {point_id}: {len(affected_in_range)} registros a corregir (ultimo_total={last_valid_total})")

    if dry_run:
        return len(affected_in_range), 0

    updated = 0
    for item in affected_in_range:
        InteractionDetail.objects.filter(id=item["id"]).update(
            total=str(int(item["last_total"])),
            total_diff=0,
        )
        updated += 1

    return len(affected_in_range), updated


def main():
    parser = argparse.ArgumentParser(description="Fix monotonicidad total NOVUS")
    parser.add_argument("--force", action="store_true", help="Aplicar cambios")
    parser.add_argument("--start", default="2026-05-19T00:00:00", help="Inicio rango")
    parser.add_argument("--end", default="2026-05-23T00:00:00", help="Fin rango")
    args = parser.parse_args()

    dry_run = not args.force
    from datetime import datetime, timezone
    start_dt = datetime.fromisoformat(args.start).replace(tzinfo=timezone.utc)
    end_dt = datetime.fromisoformat(args.end).replace(tzinfo=timezone.utc)

    # Encontrar puntos afectados (cualquier provider con pulses=0 + total vacío en rango)
    affected_points = InteractionDetail.objects.filter(
        date_time_medition__gte=start_dt,
        date_time_medition__lt=end_dt,
        pulses=0,
    ).filter(
        total__isnull=True
    ).values_list("catchment_point_id", flat=True).distinct()

    affected_points = sorted(set(affected_points))

    log(f"{'[DRY-RUN] ' if dry_run else ''}Puntos NOVUS afectados: {len(affected_points)}")
    log(f"Rango: {start_dt} → {end_dt}")
    log("")

    total_affected = 0
    total_updated = 0

    for point_id in affected_points:
        affected, updated = fix_point_monotonicity(point_id, start_dt, end_dt, dry_run)
        total_affected += affected
        total_updated += updated

    log("")
    log(f"{'[DRY-RUN] ' if dry_run else ''}Total registros afectados: {total_affected}")
    log(f"{'[DRY-RUN] ' if dry_run else ''}Total registros actualizados: {total_updated}")


if __name__ == "__main__":
    main()
