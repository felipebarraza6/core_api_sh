#!/usr/bin/env python3
"""
Cleanup Punto 8 — Remove false PARTIAL reset accumulation.

Bug: .exclude(is_error=True) in last_interaction query caused the system to
re-detect the same PARTIAL reset every hour, growing addition by ~3,150 m³ each
time (27 times, +67,123 m³ excess).

Fix applied to total.py. This script cleans up existing data.

User chose: keep 1 real reset (addition=5322.8).
"""

import os, sys, math
sys.path.insert(0, "/app")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.settings")
import django
django.setup()

from datetime import datetime
import pytz
from api.core.models import InteractionDetail, ProfileDataConfigCatchment

CP_ID = 8
FACTOR = 100
NEW_ADDITION = 5322.8
FIRST_RESET_DT = pytz.UTC.localize(
    datetime(2026, 6, 24, 18, 0, 0)
)

def fix_totals(dry_run=True):
    print(f"{'[DRY-RUN] ' if dry_run else ''}Limpiando Punto {CP_ID}...")

    # 1. Update addition in ProfileDataConfigCatchment
    profile = ProfileDataConfigCatchment.objects.filter(point_catchment_id=CP_ID).first()
    old_addition = float(profile.addition)
    if not dry_run:
        profile.addition = NEW_ADDITION
        profile.save(update_fields=["addition"])
    print(f"  Addition: {old_addition} -> {NEW_ADDITION} {'(dry-run)' if dry_run else '(applied)'}")

    # 2. Recalculate totals for all records from FIRST_RESET_DT onward
    records = InteractionDetail.objects.filter(
        catchment_point_id=CP_ID,
        date_time_medition__gte=FIRST_RESET_DT
    ).order_by("date_time_medition")

    total = records.count()
    print(f"  Records to fix: {total}")

    # Check for records with negative pulses that should be excluded
    negative = records.filter(pulses__lt=0).count()
    zero_pulses = records.filter(pulses=0).count()
    print(f"    pulses<0: {negative}, pulses=0: {zero_pulses}")

    to_update = []
    for r in records:
        if r.pulses is None or r.pulses < 0:
            continue
        new_total = int(round(float(r.pulses) * FACTOR / 1000.0)) + NEW_ADDITION
        to_update.append((r.id, new_total))

    print(f"  Records with valid pulses: {len(to_update)}")

    if not dry_run:
        batch = []
        for rid, new_total in to_update:
            batch.append(InteractionDetail(id=rid, total=str(int(round(new_total)))))
        InteractionDetail.objects.bulk_update(batch, ["total"])
        print(f"  Updated {len(batch)} records")

    # 3. Set is_error=False for all records that had false PARTIAL errors
    affected = records.filter(is_error=True)
    err_count = affected.count()
    print(f"  Records with is_error=True to clear: {err_count}")
    if not dry_run and err_count > 0:
        affected.update(is_error=False)
        print(f"  Cleared is_error={err_count} records")

    print(f"\n{'[DRY-RUN] ' if dry_run else ''}✅ Done")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Cleanup Punto 8 false resets")
    parser.add_argument("--apply", action="store_true", help="Apply changes")
    args = parser.parse_args()
    fix_totals(dry_run=not args.apply)
