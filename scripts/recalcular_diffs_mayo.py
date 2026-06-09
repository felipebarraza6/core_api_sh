#!/usr/bin/env python3
"""
Recalcula total_diff y total_today_diff para todos los registros de mayo 2026
en puntos TOTALIZADO, basándose en los totales ya corregidos.

Uso (simulación):
    docker exec -u root -w /app django_api_secure python scripts/recalcular_diffs_mayo.py

Uso (aplicar):
    docker exec -u root -w /app -e FORCE_CORRECTION=1 django_api_secure python scripts/recalcular_diffs_mayo.py
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

from django.db import transaction
from api.core.models import InteractionDetail, Variable


def log(msg):
    print(msg, flush=True)


def round_total(val):
    try:
        return int(Decimal(str(float(val))).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    except (ValueError, TypeError):
        return 0


def main():
    start_time = datetime.now()
    force = os.environ.get("FORCE_CORRECTION", "0") == "1"

    log("🔍 Identificando puntos TOTALIZADO...")
    points_with_totalizado = set()
    for v in Variable.objects.filter(type_variable="TOTALIZADO").select_related("scheme_catchment"):
        for p in v.scheme_catchment.points_catchment.all():
            points_with_totalizado.add(p.id)
    log(f"   {len(points_with_totalizado)} puntos")

    backup_path = f"/app/backups/backup_diffs_mayo_antes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    os.makedirs("/app/backups", exist_ok=True)

    fieldnames = [
        "id", "catchment_point_id", "date_time_medition",
        "total", "old_diff", "new_diff", "old_today_diff", "new_today_diff", "action",
    ]

    corrections = []

    for pid in points_with_totalizado:
        may_records = list(
            InteractionDetail.objects.filter(
                catchment_point_id=pid,
                date_time_medition__gte="2026-05-01",
                date_time_medition__lt="2026-06-01",
            ).order_by("date_time_medition").values(
                "id", "date_time_medition", "total", "total_diff", "total_today_diff"
            )
        )
        if not may_records:
            continue

        # Base pre-mayo
        prior = InteractionDetail.objects.filter(
            catchment_point_id=pid,
            date_time_medition__lt="2026-05-01",
        ).exclude(total__isnull=True).exclude(total="").exclude(total="None").order_by(
            "-date_time_medition"
        ).values("total").first()

        prev_total = round_total(prior["total"]) if prior else 0

        # Mapa de primer total del día
        first_total_of_day = {}
        for r in may_records:
            day = r["date_time_medition"].date()
            if day not in first_total_of_day:
                first_total_of_day[day] = round_total(r["total"])

        for r in may_records:
            rid = r["id"]
            curr_total = round_total(r["total"])
            day = r["date_time_medition"].date()
            first_total = first_total_of_day.get(day, 0)

            new_diff = max(0, curr_total - prev_total)
            new_today_diff = max(0, curr_total - first_total)

            old_diff = r["total_diff"] or 0
            old_today_diff = r["total_today_diff"] or 0

            needs_update = (new_diff != old_diff) or (new_today_diff != old_today_diff)

            if needs_update:
                corrections.append({
                    "id": rid,
                    "catchment_point_id": pid,
                    "date_time_medition": r["date_time_medition"].strftime("%Y-%m-%d %H:%M:%S"),
                    "total": r["total"],
                    "old_diff": old_diff,
                    "new_diff": new_diff,
                    "old_today_diff": old_today_diff,
                    "new_today_diff": new_today_diff,
                    "action": "UPDATE_DIFF",
                })

            prev_total = curr_total

    log(f"📊 Correcciones de diff necesarias: {len(corrections)}")

    if not corrections:
        log("✅ No hay correcciones de diff necesarias.")
        return

    # Backup CSV
    with open(backup_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(corrections)
    log(f"💾 Backup guardado en: {backup_path}")

    log("\n📝 Muestra:")
    for r in corrections[:10]:
        log(f"   Punto {r['catchment_point_id']} @ {r['date_time_medition']}: "
            f"diff {r['old_diff']}→{r['new_diff']}, today {r['old_today_diff']}→{r['new_today_diff']}")

    if not force:
        log("\n⚠️  Para aplicar, re-ejecuta con FORCE_CORRECTION=1")
        return

    # Aplicar
    log(f"\n🔧 Aplicando {len(corrections)} correcciones de diff...")
    updated = 0
    errors = 0
    with transaction.atomic():
        for r in corrections:
            try:
                InteractionDetail.objects.filter(id=r["id"]).update(
                    total_diff=r["new_diff"],
                    total_today_diff=r["new_today_diff"],
                )
                updated += 1
                if updated % 1000 == 0:
                    log(f"   ... {updated} actualizados")
            except Exception as e:
                log(f"   ❌ Error en id={r['id']}: {e}")
                errors += 1

    log(f"\n✅ Listo!")
    log(f"   Actualizados: {updated}")
    log(f"   Errores: {errors}")
    log(f"   Backup: {backup_path}")
    log(f"   Tiempo: {datetime.now() - start_time}")


if __name__ == "__main__":
    main()
