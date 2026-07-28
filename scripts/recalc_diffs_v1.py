#!/usr/bin/env python3
"""
Recalcula total_diff y total_today_diff para todos los puntos.

Después de corregir total (bulk_fix_totals_v2.py), los campos derivados
total_diff y total_today_diff quedan stale. Este script los recalcula.

Fórmulas:
  total_diff = max(0, current_total - previous_total)
  total_today_diff = max(0, current_total - first_total_of_day)

Usa bulk_update para eficiencia.
"""
import os, sys
from datetime import datetime

sys.path.insert(0, "/app")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.settings")
import django
django.setup()

from django.db import transaction
from api.core.models import InteractionDetail, ProfileDataConfigCatchment, SchemesCatchment, Variable


def log(msg, level="INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [{level}] {msg}", flush=True)


def calc_diffs_for_point(pid, apply):
    records = list(
        InteractionDetail.objects.filter(
            catchment_point_id=pid, is_error=False
        ).exclude(total__isnull=True).exclude(total="").exclude(total="None")
        .order_by("date_time_medition")
        .values("id", "total", "date_time_medition", "total_diff", "total_today_diff")
    )

    if not records:
        return 0

    prev_total = 0.0
    current_day = None
    first_of_day = 0.0
    updates = []

    for r in records:
        try:
            curr_total = float(r["total"]) if r["total"] not in (None, "", "None") else 0.0
        except (ValueError, TypeError):
            curr_total = 0.0

        day = r["date_time_medition"].date()
        if current_day != day:
            current_day = day
            first_of_day = curr_total

        new_diff = max(0, int(curr_total) - int(prev_total))
        new_today = max(0, int(curr_total) - int(first_of_day))
        old_diff = r["total_diff"] or 0
        old_today = r["total_today_diff"] or 0

        if new_diff != old_diff or new_today != old_today:
            updates.append((r["id"], new_diff, new_today))

        prev_total = curr_total

    if not updates:
        return 0

    if not apply:
        return len(updates)

    # Batch update
    batch_size = 500
    total_updated = 0
    for i in range(0, len(updates), batch_size):
        chunk = updates[i:i + batch_size]
        objs = []
        for rid, nd, nt in chunk:
            obj = InteractionDetail(id=rid)
            obj.total_diff = nd
            obj.total_today_diff = nt
            objs.append(obj)
        with transaction.atomic():
            InteractionDetail.objects.bulk_update(
                objs, ["total_diff", "total_today_diff"]
            )
        total_updated += len(chunk)
        if (i // batch_size + 1) % 20 == 0:
            log(f"  Progreso Punto {pid}: {total_updated}/{len(updates)}")

    return total_updated


def main():
    apply = "--apply" in sys.argv
    point_filter = None
    for arg in sys.argv:
        if arg.startswith("--point="):
            point_filter = int(arg.split("=")[1])

    profiles = ProfileDataConfigCatchment.objects.filter(
        is_telemetry=True, addition=0
    ).select_related("point_catchment")

    log("=" * 60)
    log(f"RECALC DIFS - MODO: {'APLICAR' if apply else 'DRY-RUN'}")
    log("=" * 60)

    total_updates = 0
    total_points = 0

    for p in profiles:
        cp = p.point_catchment
        if point_filter and cp.id != point_filter:
            continue

        n = calc_diffs_for_point(cp.id, apply)
        if n == 0:
            continue

        total_points += 1
        total_updates += n
        log(f"{'✓' if apply else ' '} Punto {cp.id:>3} ({cp.title:<35}): {n:>7} registros")

    log("=" * 60)
    if apply:
        log(f"✓ {total_updates} registros actualizados en {total_points} puntos")
    else:
        log(f"Registros a actualizar: {total_updates} en {total_points} puntos")
        log("Usa --apply para aplicar.")
    log("=" * 60)


if __name__ == "__main__":
    main()
