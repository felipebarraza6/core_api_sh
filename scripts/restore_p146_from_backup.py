#!/usr/bin/env python3
import os, sys, csv
sys.path.insert(0, "/app")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.settings")
import django
django.setup()
from django.db import transaction
from api.core.models import InteractionDetail

BACKUP = "/app/backups/fix_fernandez_renca_nivel_flow_antes_20260610_172249.csv"

def main():
    updates = []
    with open(BACKUP, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if int(row["catchment_point_id"]) != 146:
                continue
            updates.append((
                int(row["id"]),
                {
                    "total": row["total"] if row["total"] else "0",
                    "total_diff": int(row["total_diff"]) if row["total_diff"] else 0,
                    "total_today_diff": int(row["total_today_diff"]) if row["total_today_diff"] else 0,
                }
            ))
    print(f"Restaurando {len(updates)} registros del punto 146...")
    with transaction.atomic():
        for rid, changes in updates:
            InteractionDetail.objects.filter(id=rid).update(**changes)
    print("✅ Restauración completada.")

if __name__ == "__main__":
    main()
