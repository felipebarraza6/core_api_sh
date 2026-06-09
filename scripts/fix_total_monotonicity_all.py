#!/usr/bin/env python3
"""
FIX MONOTONICIDAD TOTAL — Todos los providers
=============================================

Para registros con total=NULL (cualquier provider), propaga el último total válido
para mantener monotonicidad. Soporta TWIN, NOVUS, y cualquier punto con historial.

USO:
    docker exec -u root -w /app django_api_secure python scripts/fix_total_monotonicity_all.py --dry-run
    docker exec -u root -w /app django_api_secure python scripts/fix_total_monotonicity_all.py --force
"""

import os
import sys
import argparse

sys.path.insert(0, "/app")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.settings")
import django
django.setup()

from django.db import transaction
from api.core.models import InteractionDetail, CatchmentPoint, ProfileDataConfigCatchment


def log(msg):
    print(msg, flush=True)


def fix_point(point_id, dry_run=True):
    """
    Para un punto, encuentra registros con total=NULL y propaga el último total válido.
    También recalcula total_diff y total_today_diff para registros corregidos.
    """
    records = list(
        InteractionDetail.objects.filter(
            catchment_point_id=point_id,
        ).order_by("date_time_medition").values(
            "id", "date_time_medition", "pulses", "total", "total_diff", "total_today_diff"
        )
    )

    if not records:
        return 0, 0

    last_valid_total = None
    affected = []

    for r in records:
        total_str = r["total"]
        pulses = r["pulses"]

        # Verificar si es un total válido
        is_valid = False
        current_total = None
        if total_str not in (None, "", "None"):
            try:
                current_total = float(total_str)
                if current_total > 0 or (current_total == 0 and last_valid_total is not None):
                    is_valid = True
            except (ValueError, TypeError):
                pass

        if is_valid:
            last_valid_total = current_total

        if not is_valid and last_valid_total is not None:
            affected.append({
                "id": r["id"],
                "dt": r["date_time_medition"],
                "pulses": pulses,
                "last_total": last_valid_total,
            })

    if not affected:
        return 0, 0

    log(f"  Punto {point_id}: {len(affected)} registros a corregir (ultimo_total={last_valid_total})")

    if dry_run:
        return len(affected), 0

    # Actualizar en bloques para no saturar la BD
    updated = 0
    for item in affected:
        InteractionDetail.objects.filter(id=item["id"]).update(
            total=str(int(item["last_total"])),
            total_diff=0,
        )
        updated += 1

    return len(affected), updated


def recalc_diffs_for_point(point_id):
    """
    Recalcula total_diff y total_today_diff para TODOS los registros del punto
    que tienen total válido, en orden cronológico.
    """
    records = list(
        InteractionDetail.objects.filter(
            catchment_point_id=point_id,
        ).exclude(
            total__isnull=True
        ).exclude(
            total=""
        ).exclude(
            total="None"
        ).order_by("date_time_medition").values(
            "id", "date_time_medition", "total"
        )
    )

    if len(records) < 2:
        return 0, 0

    prev_total = None
    first_of_day = {}
    diff_updates = 0
    today_updates = 0

    for r in records:
        rid = r["id"]
        try:
            curr = float(r["total"])
        except (ValueError, TypeError):
            continue

        day = r["date_time_medition"].date()

        # total_diff = diferencia con registro anterior
        if prev_total is not None:
            diff = max(0, curr - prev_total)
        else:
            diff = 0

        # total_today_diff = acumulado desde primera medición del día
        if day not in first_of_day:
            first_of_day[day] = curr
        today_diff = max(0, curr - first_of_day[day])

        InteractionDetail.objects.filter(id=rid).update(
            total_diff=int(diff),
            total_today_diff=int(today_diff),
        )
        diff_updates += 1
        today_updates += 1
        prev_total = curr

    return diff_updates, today_updates


def main():
    parser = argparse.ArgumentParser(description="Fix monotonicidad total todos providers")
    parser.add_argument("--force", action="store_true", help="Aplicar cambios")
    parser.add_argument("--point-id", type=int, default=None, help="Solo un punto")
    parser.add_argument("--recalc-diffs", action="store_true", help="Recalcular diffs post-fix")
    args = parser.parse_args()

    dry_run = not args.force

    # Encontrar puntos con telemetría activa que tienen total=NULL
    query = InteractionDetail.objects.filter(
        total__isnull=True,
        catchment_point__data_config_profiles__is_telemetry=True,
    )

    if args.point_id:
        query = query.filter(catchment_point_id=args.point_id)

    affected_points = query.values_list("catchment_point_id", flat=True).distinct()
    affected_points = sorted(set(affected_points))

    log(f"{'[DRY-RUN] ' if dry_run else ''}Puntos afectados: {len(affected_points)}")
    log("")

    total_affected = 0
    total_updated = 0

    for point_id in affected_points:
        affected, updated = fix_point(point_id, dry_run)
        total_affected += affected
        total_updated += updated

        if updated > 0 and args.recalc_diffs and not dry_run:
            d, t = recalc_diffs_for_point(point_id)
            log(f"    → diffs recalculados: {d} registros")

    log("")
    log(f"{'[DRY-RUN] ' if dry_run else ''}Total registros afectados: {total_affected}")
    log(f"{'[DRY-RUN] ' if dry_run else ''}Total registros actualizados: {total_updated}")


if __name__ == "__main__":
    main()
