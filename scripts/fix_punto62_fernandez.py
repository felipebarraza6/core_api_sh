#!/usr/bin/env python3
"""
Recalcular backfill punto 62 (Planta 1 P2) — crisis Redis 19-22 mayo 2026.
Base: 2026-05-19 23:56 UTC, total=113468, pulses=113468, factor=1000.
"""
import os, sys, csv
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
import pytz
sys.path.insert(0, "/app")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.settings")
import django; django.setup()
from django.db import transaction
from api.core.models import InteractionDetail

POINT_ID = 62
BASE_PULSES = 113468.0
BASE_TOTAL = 113468.0
FACTOR = 1000
START_DT = pytz.UTC.localize(datetime(2026, 5, 20, 0, 0, 0))
END_DT = pytz.UTC.localize(datetime(2026, 5, 22, 16, 0, 0))
FORCE = os.environ.get("FORCE_FIX", "0") == "1"

def log(msg): print(msg, flush=True)
def round_total(val): return int(Decimal(str(val)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
def safe_float(s, d=0.0):
    try: return float(s) if s not in (None, "", "None") else d
    except: return d

def main():
    log(f"{'='*60}\nRecalcular backfill punto {POINT_ID}\n{'='*60}")
    records = list(
        InteractionDetail.objects
        .filter(catchment_point_id=POINT_ID, date_time_medition__gte=START_DT, date_time_medition__lt=END_DT)
        .order_by("date_time_medition")
        .values("id", "date_time_medition", "pulses", "total", "total_diff", "total_today_diff")
    )
    backfill = [r for r in records if r["date_time_medition"].minute % 5 == 0]
    err = [r for r in records if r["date_time_medition"].minute % 5 == 1]
    log(f"Registros en rango: {len(records)} (backfill {len(backfill)}, erróneos {len(err)})")
    if not backfill:
        log("No hay backfill."); return
    log(f"Primer backfill: {backfill[0]['date_time_medition']} total={backfill[0]['total']}")
    log(f"Último backfill: {backfill[-1]['date_time_medition']} total={backfill[-1]['total']}")

    # backup
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = f"/app/backups/backfill_p{POINT_ID}_{ts}.csv"
    os.makedirs("/app/backups", exist_ok=True)
    with open(backup, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=backfill[0].keys())
        w.writeheader(); w.writerows(backfill)
    log(f"Backup: {backup} ({len(backfill)} registros)")

    if err:
        ids_err = [r["id"] for r in err]
        log(f"Eliminando {len(ids_err)} registros erróneos...")
        if FORCE:
            InteractionDetail.objects.filter(id__in=ids_err).delete()
            log("Eliminados.")
        else:
            log("[DRY-RUN] no se eliminan.")

    # recalcular
    prev_total = BASE_TOTAL
    prev_pulses = BASE_PULSES
    current_day = None
    first_total_of_day = None
    day_first_id = None
    updates = []

    for r in backfill:
        rid = r["id"]
        dt = r["date_time_medition"]
        cp = safe_float(r["pulses"], 0.0)

        if dt.date() != current_day:
            current_day = dt.date()
            first_total_of_day = prev_total
            day_first_id = rid

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
        new_today = max(0, new_total_r - round_total(first_total_of_day)) if day_first_id != rid else 0

        changes = {}
        if safe_float(r["total"], 0) != new_total_r: changes["total"] = str(new_total_r)
        if safe_float(r["total_diff"], 0) != new_diff: changes["total_diff"] = new_diff
        if safe_float(r["total_today_diff"], 0) != new_today: changes["total_today_diff"] = new_today
        if changes:
            updates.append((rid, changes))
        if not skip_baseline:
            prev_pulses = cp
        prev_total = new_total

    log(f"Registros a ajustar: {len(updates)}")
    if not FORCE:
        for rid, ch in updates[:10]:
            log(f"  id={rid} → {ch}")
        if len(updates) > 10: log(f"  ... y {len(updates)-10} más")
        log("DRY-RUN. Usar FORCE_FIX=1 para aplicar.")
        return

    with transaction.atomic():
        for rid, ch in updates:
            InteractionDetail.objects.filter(id=rid).update(**ch)
    log(f"✅ {len(updates)} registros actualizados.")

if __name__ == "__main__":
    main()
