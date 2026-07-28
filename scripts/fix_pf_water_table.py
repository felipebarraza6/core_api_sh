#!/usr/bin/env python3
import os, sys
sys.path.insert(0, "/app")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.settings")
import django
django.setup()

from django.db import transaction
from api.core.models import InteractionDetail, ProfileDataConfigCatchment
import pytz
from datetime import datetime

UTC = pytz.UTC
START_DT = UTC.localize(datetime(2026, 5, 20, 0, 0, 0))
END_DT = UTC.localize(datetime(2026, 5, 22, 16, 0, 0))
POINT_IDS = [61, 62, 63, 64, 146]
FORCE = os.environ.get("FORCE_FIX", "0") == "1"

def main():
    d3_map = {}
    for pid in POINT_IDS:
        p = ProfileDataConfigCatchment.objects.filter(point_catchment_id=pid).first()
        d3_map[pid] = float(p.d3) if p and p.d3 else 0.0

    print("Recalculando water_table para PF (Fernandez + Renca)...")
    total_changes = 0

    for pid in POINT_IDS:
        d3 = d3_map[pid]
        if d3 <= 0:
            print(f"  Punto {pid}: d3 inválido ({d3}), se omite.")
            continue

        records = list(
            InteractionDetail.objects.filter(
                catchment_point_id=pid,
                date_time_medition__gte=START_DT,
                date_time_medition__lt=END_DT,
            ).values("id", "nivel", "water_table")
        )

        updates = []
        for r in records:
            nivel = float(r["nivel"]) if r["nivel"] is not None else 0.0
            old_wt = float(r["water_table"]) if r["water_table"] is not None else 0.0
            new_wt = d3 - nivel
            if new_wt < 0:
                new_wt = 0.0
            new_wt = round(new_wt, 2)
            if abs(new_wt - old_wt) > 0.005:
                updates.append((r["id"], {"water_table": new_wt}))

        print(f"  Punto {pid}: {len(updates)} registros a ajustar (d3={d3})")
        if updates and not FORCE:
            for rid, ch in updates[:3]:
                print(f"    id={rid} → {ch}")
            if len(updates) > 3:
                print(f"    ... y {len(updates)-3} más")
        elif updates and FORCE:
            with transaction.atomic():
                for rid, ch in updates:
                    InteractionDetail.objects.filter(id=rid).update(**ch)
            total_changes += len(updates)

    if FORCE:
        print(f"✅ Aplicados {total_changes} cambios.")
    else:
        print("⚠️  Esto fue simulación. Para aplicar: FORCE_FIX=1 python scripts/fix_pf_water_table.py")

if __name__ == "__main__":
    main()
