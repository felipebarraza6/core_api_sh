#!/usr/bin/env python3
"""
Corregir total_diff y total_today_diff post-crisis punto 64.
Recalcula desde el primer registro del 22 mayo en adelante.
"""
import os, sys
from datetime import datetime
import pytz
sys.path.insert(0, "/app")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.settings")
import django; django.setup()
from django.db import transaction
from api.core.models import InteractionDetail

POINT_ID = 64
START_DT = pytz.UTC.localize(datetime(2026, 5, 22, 0, 0, 0))
FORCE = os.environ.get("FORCE_FIX", "0") == "1"

def log(msg): print(msg, flush=True)
def safe_float(s, d=0.0):
    try: return float(s) if s not in (None, "", "None") else d
    except: return d

def main():
    log(f"{'='*60}\nCorrección post-crisis punto {POINT_ID}\n{'='*60}")
    records = list(
        InteractionDetail.objects
        .filter(catchment_point_id=POINT_ID, date_time_medition__gte=START_DT)
        .order_by("date_time_medition")
        .values("id", "date_time_medition", "total", "total_diff", "total_today_diff")
    )
    if not records:
        log("Sin registros."); return

    first_total_of_day = safe_float(records[0]["total"], 0.0)
    log(f"Primer registro 22 mayo: {records[0]['date_time_medition']} total={first_total_of_day}")

    current_day = None
    day_total = None
    prev_total = None
    updates = []

    for r in records:
        rid = r["id"]
        dt = r["date_time_medition"]
        total = safe_float(r["total"], 0.0)

        if dt.date() != current_day:
            current_day = dt.date()
            day_total = total

        new_diff = max(0, int(total) - int(prev_total)) if prev_total is not None else 0
        new_today = max(0, int(total) - int(day_total))

        changes = {}
        if int(safe_float(r["total_diff"], 0)) != new_diff:
            changes["total_diff"] = new_diff
        if int(safe_float(r["total_today_diff"], 0)) != new_today:
            changes["total_today_diff"] = new_today
        if changes:
            updates.append((rid, changes))
        prev_total = total

    log(f"Registros a revisar: {len(records)}  → AJUSTAR {len(updates)}")
    if not FORCE:
        for rid, ch in updates[:15]:
            log(f"  → AJUSTAR id={rid} {ch}")
        if len(updates) > 15: log(f"  ... y {len(updates)-15} más")
        log("DRY-RUN. Usar FORCE_FIX=1 para aplicar.")
        return

    with transaction.atomic():
        for rid, ch in updates:
            InteractionDetail.objects.filter(id=rid).update(**ch)
    log(f"✅ Corrección post-crisis aplicada ({len(updates)} registros).")

if __name__ == "__main__":
    main()
