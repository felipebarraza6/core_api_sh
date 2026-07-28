#!/usr/bin/env python3
"""
Recálculo para punto 61 (Planta 1 P1) - Productos Fernandez.
Rango: 2026-05-20 00:00 UTC hasta 2026-05-22 12:25 UTC (último backfill).
"""

import os
import sys
import csv
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

sys.path.insert(0, "/app")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.settings")
import django
django.setup()

import pytz
from django.db import transaction
from api.core.models import InteractionDetail, Variable


POINT_ID = 61
FACTOR = 1000
UTC = pytz.UTC
START_DT = UTC.localize(datetime(2026, 5, 20, 0, 0, 0))
END_DT = UTC.localize(datetime(2026, 5, 22, 16, 0, 0))
FORCE = os.environ.get("FORCE_FIX", "0") == "1"


def log(msg):
    print(msg, flush=True)


def round_total(val):
    return int(Decimal(str(val)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def safe_float(s, default=0.0):
    try:
        return float(s) if s not in (None, "", "None") else default
    except (ValueError, TypeError):
        return default


def main():
    log("=" * 60)
    log(f"Recálculo punto {POINT_ID} (Planta 1 P1) - Productos Fernandez")
    log("=" * 60)
    log(f"Rango backfill: {START_DT.isoformat()} → {END_DT.isoformat()}")
    log(f"Modo: {'APLICAR' if FORCE else 'DRY-RUN'}")
    log("")

    # Último backfill (minuto múltiplo de 5)
    candidate = (
        InteractionDetail.objects.filter(
            catchment_point_id=POINT_ID,
            date_time_medition__gte=START_DT,
            date_time_medition__lt=END_DT,
        )
        .order_by("-date_time_medition")
        .values("id", "date_time_medition")
        .first()
    )
    last_backfill_dt = None
    while candidate:
        if candidate["date_time_medition"].minute % 5 == 0:
            last_backfill_dt = candidate["date_time_medition"]
            break
        candidate = (
            InteractionDetail.objects.filter(
                catchment_point_id=POINT_ID,
                date_time_medition__gte=START_DT,
                date_time_medition__lt=candidate["date_time_medition"],
            )
            .order_by("-date_time_medition")
            .values("id", "date_time_medition")
            .first()
        )
    if not last_backfill_dt:
        log("⚠️ No se encontró registro de backfill. Abortando.")
        return
    log(f"Último registro backfill: {last_backfill_dt.isoformat()}")

    # Backup de registros a modificar
    to_backup = list(
        InteractionDetail.objects.filter(
            catchment_point_id=POINT_ID,
            date_time_medition__gte=START_DT,
            date_time_medition__lte=last_backfill_dt,
        ).values(
            "id", "date_time_medition", "pulses", "total",
            "total_diff", "total_today_diff",
        )
    )
    if not to_backup:
        log("⚠️ No hay registros para recalcular.")
        return

    backup_dir = "/app/backups"
    os.makedirs(backup_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{backup_dir}/fix_punto61_antes_{ts}.csv"
    with open(backup_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "id", "date_time_medition", "pulses", "total",
            "total_diff", "total_today_diff",
        ])
        writer.writeheader()
        writer.writerows(to_backup)
    log(f"💾 Backup: {backup_path} ({len(to_backup)} registros)")

    # Último registro válido antes del backfill
    prev = (
        InteractionDetail.objects.filter(
            catchment_point_id=POINT_ID,
            date_time_medition__lt=START_DT,
        )
        .exclude(total__isnull=True)
        .exclude(total="")
        .exclude(total="None")
        .order_by("-date_time_medition")
        .values("id", "pulses", "total", "date_time_medition")
        .first()
    )
    if not prev:
        log("⚠️ No se encontró registro previo válido. Abortando.")
        return
    log(f"Último previo válido: {prev['date_time_medition'].isoformat()} pulses={prev['pulses']} total={prev['total']}")

    # Recalcular en memoria
    records = list(
        InteractionDetail.objects.filter(
            catchment_point_id=POINT_ID,
            date_time_medition__gte=prev["date_time_medition"],
            date_time_medition__lte=last_backfill_dt,
        ).order_by("date_time_medition").values(
            "id", "date_time_medition", "pulses", "total",
            "total_diff", "total_today_diff",
        )
    )
    # Saltar el previo
    records = [r for r in records if r["id"] != prev["id"]]

    prev_total = safe_float(prev["total"], 0.0)
    prev_pulses = safe_float(prev["pulses"], 0.0)
    current_day = prev["date_time_medition"].date()
    first_total_of_day = prev_total

    updates = []
    log("📝 Primeras filas de simulación:")
    for i, r in enumerate(records):
        rid = r["id"]
        dt = r["date_time_medition"]
        cp = safe_float(r["pulses"], 0.0)
        old_total = safe_float(r["total"], 0.0)
        old_diff = r["total_diff"] or 0
        old_today = r["total_today_diff"] or 0

        if dt.date() != current_day:
            current_day = dt.date()
            first_total_of_day = None  # se define con el primer registro del día

        if cp == 0:
            pulse_diff = 0
            new_total = prev_total
            skip_baseline = True
        elif cp >= prev_pulses:
            pulse_diff = cp - prev_pulses
            skip_baseline = False
        else:
            pulse_diff = cp
            skip_baseline = False

        new_total = prev_total + (pulse_diff * FACTOR) / 1000.0
        new_total_r = round_total(new_total)
        new_diff = max(0, new_total_r - round_total(prev_total))
        if first_total_of_day is None:
            new_today = 0
            first_total_of_day = new_total_r
        else:
            new_today = max(0, new_total_r - round_total(first_total_of_day))

        if i < 10:
            log(f"   {dt.isoformat()} pulses={int(cp)} old_total={int(round_total(old_total))}→{new_total_r} "
                f"old_diff={old_diff}→{new_diff} old_today={old_today}→{new_today}")

        changes = {}
        if new_total_r != round_total(old_total):
            changes["total"] = str(new_total_r)
        if new_diff != old_diff:
            changes["total_diff"] = new_diff
        if new_today != old_today:
            changes["total_today_diff"] = new_today

        if changes:
            updates.append((rid, changes))

        prev_total = new_total
        if not skip_baseline:
            prev_pulses = cp

    total_ch = sum(1 for _, c in updates if "total" in c)
    diff_ch = sum(1 for _, c in updates if "total_diff" in c)
    today_ch = sum(1 for _, c in updates if "total_today_diff" in c)

    log("")
    log(f"Registros a ajustar: {len(updates)}")
    log(f"  - total: {total_ch}")
    log(f"  - total_diff: {diff_ch}")
    log(f"  - total_today_diff: {today_ch}")

    if not FORCE:
        log("")
        log("⚠️  Esto fue simulación. Para aplicar re-ejecuta con FORCE_FIX=1")
        return

    # Aplicar
    with transaction.atomic():
        for rid, changes in updates:
            InteractionDetail.objects.filter(id=rid).update(**changes)

    log("")
    log(f"✅ Aplicados {len(updates)} ajustes al punto {POINT_ID}.")


if __name__ == "__main__":
    main()
