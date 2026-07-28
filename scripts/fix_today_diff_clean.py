#!/usr/bin/env python3
"""
CORRECCIÓN LIMPIA DE total_today_diff
=====================================

Recalcula total_today_diff para un rango de fechas usando el primer registro
de cada día (por date_time_medition) como baseline. No toca total, total_diff,
flow, nivel ni ningún otro campo.

Uso (dry-run por defecto):
    python scripts/fix_today_diff_clean.py --start 2026-07-02 --end 2026-07-07
    python scripts/fix_today_diff_clean.py --start 2026-07-02 --end 2026-07-07 --point-id 14
    python scripts/fix_today_diff_clean.py --start 2026-07-02 --end 2026-07-07 --apply
"""

import os
import sys
import argparse
from datetime import datetime, timedelta

sys.path.append('/app')
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.settings")

import django
django.setup()

import pytz
from django.db import transaction
from api.core.models import InteractionDetail, CatchmentPoint

UTC = pytz.UTC


def safe_float(val, default=0.0):
    try:
        return float(val) if val is not None else default
    except (ValueError, TypeError):
        return default


def fix_point(point_id, start_dt, end_dt, apply=False):
    records = list(
        InteractionDetail.objects.filter(
            catchment_point_id=point_id,
            date_time_medition__gte=start_dt,
            date_time_medition__lte=end_dt,
        ).order_by("date_time_medition").values("id", "date_time_medition", "total", "total_today_diff")
    )

    if not records:
        return 0

    current_day = None
    first_total_of_day = None
    updates = []

    for r in records:
        dt = r["date_time_medition"]
        day = dt.date()
        total = safe_float(r["total"], 0.0)

        if day != current_day:
            current_day = day
            first_total_of_day = total

        if first_total_of_day is not None:
            expected_today = max(0, round(total - first_total_of_day))
        else:
            expected_today = 0

        current_today = r["total_today_diff"] or 0
        if current_today != expected_today:
            updates.append((r["id"], expected_today))

    if apply and updates:
        with transaction.atomic():
            for rid, new_today in updates:
                InteractionDetail.objects.filter(id=rid).update(total_today_diff=new_today)

    return len(updates)


def main():
    parser = argparse.ArgumentParser(description="Corrección limpia de total_today_diff")
    parser.add_argument("--start", required=True, help="YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="YYYY-MM-DD")
    parser.add_argument("--point-id", type=int, help="Filtrar por punto")
    parser.add_argument("--apply", action="store_true", help="Aplicar cambios reales")
    args = parser.parse_args()

    start_dt = UTC.localize(datetime.strptime(args.start, "%Y-%m-%d"))
    end_dt = UTC.localize(datetime.strptime(args.end, "%Y-%m-%d")) + timedelta(days=1)

    qs = CatchmentPoint.objects.filter(data_config_profiles__is_telemetry=True).distinct()
    if args.point_id:
        qs = qs.filter(id=args.point_id)

    mode = "APLICANDO CAMBIOS REALES" if args.apply else "DRY-RUN"
    print(f"=== CORRECCIÓN total_today_diff | {mode} ===")
    print(f"Rango: {args.start} -> {args.end}")
    print(f"Puntos: {qs.count()}")
    print()

    total_updates = 0
    for point in qs.order_by("id"):
        n = fix_point(point.id, start_dt, end_dt, apply=args.apply)
        if n > 0:
            print(f"📍 Punto {point.id}: {n} correcciones")
            total_updates += n

    print()
    print(f"Total correcciones: {total_updates}")
    if not args.apply:
        print("Modo dry-run. Ningún cambio aplicado. Usa --apply para ejecutar.")
    else:
        print("✅ Cambios aplicados.")


if __name__ == "__main__":
    main()
