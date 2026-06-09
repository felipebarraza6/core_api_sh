#!/usr/bin/env python3
"""
RECALCULO POST-BACKFILL — Crisis Redis 19-22 mayo 2026
=======================================================

Recalcula totales, total_diff y total_today_diff SOLO para los registros creados
por el backfill de TWIN (aquellos con total vacío/None/"0" pero con pulses > 0).

ESTRATEGIA:
1. Para cada punto, obtener TODOS los registros en orden cronológico (pre-rango + rango).
2. Identificar registros del backfill: total vacío/None/"0" pero pulses > 0.
3. Calcular total en cascada desde el último registro válido.
4. Segunda pasada: recalcular total_diff y total_today_diff para registros afectados.

USO (dry-run por defecto):
    docker exec -u root -w /app django_api_secure python scripts/recalcular_backfill_crisis_mayo2026.py

USO (aplicar):
    docker exec -u root -w /app -e FORCE_CORRECTION=1 django_api_secure python scripts/recalcular_backfill_crisis_mayo2026.py
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

from django.db import transaction, models
from api.core.models import InteractionDetail, Variable


START_DT = "2026-05-19T20:00:00"
END_DT = "2026-05-22T12:00:00"
FORCE = os.environ.get("FORCE_CORRECTION", "0") == "1"


def log(msg):
    print(msg, flush=True)


def round_total(val):
    return int(Decimal(str(val)).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def is_empty_total(total):
    return total is None or total == "" or total == "0" or total == "None"


def main():
    start_time = datetime.now()
    log("=" * 70)
    log("RECALCULO POST-BACKFILL — Crisis Redis 19-22 mayo 2026")
    log("=" * 70)
    log(f"Rango backfill: {START_DT} → {END_DT}")
    log(f"Modo: {'APLICAR CAMBIOS REALES' if FORCE else 'DRY-RUN'}")
    log("")

    # Mapear puntos a factor
    point_factors = {}
    for v in Variable.objects.filter(type_variable="TOTALIZADO").select_related("scheme_catchment"):
        for p in v.scheme_catchment.points_catchment.all():
            point_factors[p.id] = v.pulses_factor or 1000
    log(f"🔍 {len(point_factors)} puntos con TOTALIZADO mapeados")

    # Identificar puntos afectados (tienen al menos un registro con total vacío en el rango)
    affected_point_ids = list(
        InteractionDetail.objects.filter(
            date_time_medition__gte=START_DT,
            date_time_medition__lt=END_DT,
            pulses__gt=0,
        ).filter(
            models.Q(total__isnull=True) | models.Q(total="") | models.Q(total="0") | models.Q(total="None")
        ).values_list("catchment_point_id", flat=True).distinct()
    )
    log(f"📍 Puntos con registros de backfill: {len(affected_point_ids)}")
    log("")

    backup_path = f"/app/backups/backup_recalculo_backfill_antes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    os.makedirs("/app/backups", exist_ok=True)
    fieldnames = [
        "id", "catchment_point_id", "date_time_medition",
        "pulses", "old_total", "new_total", "old_diff", "new_diff",
        "old_today_diff", "new_today_diff", "action",
    ]

    total_corrections = 0
    rows = []

    for pid in affected_point_ids:
        factor = point_factors.get(pid, 1000)

        # Obtener TODOS los registros del punto, ordenados cronológicamente
        all_records = list(
            InteractionDetail.objects.filter(
                catchment_point_id=pid,
            ).order_by("date_time_medition").values(
                "id", "date_time_medition", "pulses", "total",
                "total_diff", "total_today_diff",
            )
        )
        if not all_records:
            continue

        # Encontrar el último registro válido antes del primer registro del backfill
        # y calcular en cascada
        last_real_pulses = None
        last_total = None
        calculated = {}

        for r in all_records:
            rid = r["id"]
            current_pulses = r["pulses"]
            old_total_str = r["total"]
            dt = r["date_time_medition"]
            in_range = START_DT <= dt.strftime("%Y-%m-%dT%H:%M:%S") < END_DT

            # Si es un registro válido (total no vacío, pulses > 0), usarlo como base
            if current_pulses is not None and current_pulses > 0 and not is_empty_total(old_total_str):
                try:
                    last_total = float(old_total_str)
                    last_real_pulses = float(current_pulses)
                    continue
                except (ValueError, TypeError):
                    pass

            # Si no es del rango de backfill, ignorar
            if not in_range:
                continue

            # Si no tiene pulses o es 0, no recalcular total
            if current_pulses is None or current_pulses == 0:
                continue

            # Si llegamos aquí, es un registro del backfill con pulses > 0 y total vacío
            if last_real_pulses is None or last_total is None:
                # No hay base válida, saltar
                continue

            cp = float(current_pulses)
            if cp >= last_real_pulses:
                diff = cp - last_real_pulses
            else:
                diff = cp  # Reset detectado

            new_total = last_total + (diff * factor) / 1000.0
            calculated[rid] = new_total
            last_real_pulses = cp
            last_total = new_total

        if not calculated:
            continue

        # Verificar qué registros necesitan actualización
        for r in all_records:
            rid = r["id"]
            if rid not in calculated:
                continue

            new_total = calculated[rid]
            old_total_str = r["total"]

            try:
                old_total = float(old_total_str) if old_total_str not in (None, "", "None") else 0.0
            except (ValueError, TypeError):
                old_total = 0.0

            new_total_rounded = round_total(new_total)
            old_total_rounded = round_total(old_total)

            if new_total_rounded != old_total_rounded:
                total_corrections += 1
                action = f"CORRECT_TOTAL_{old_total_rounded}_{new_total_rounded}"
            else:
                action = "KEEP_TOTAL"

            rows.append({
                "id": rid,
                "catchment_point_id": pid,
                "date_time_medition": r["date_time_medition"].strftime("%Y-%m-%d %H:%M:%S"),
                "pulses": r["pulses"],
                "old_total": old_total_str,
                "new_total": str(new_total_rounded),
                "old_diff": r["total_diff"],
                "new_diff": None,
                "old_today_diff": r["total_today_diff"],
                "new_today_diff": None,
                "action": action,
            })

    log(f"📊 Correcciones de total necesarias: {total_corrections} de {len(rows)} registros del backfill")

    if total_corrections == 0:
        log("✅ No hay correcciones necesarias.")
        return

    sample = [r for r in rows if r["action"].startswith("CORRECT")][:10]
    log("\n📝 Muestra de correcciones:")
    for r in sample:
        log(f"   Punto {r['catchment_point_id']} @ {r['date_time_medition']}: "
            f"total {repr(r['old_total'])} → {r['new_total']}")

    # Guardar backup CSV
    with open(backup_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    log(f"\n💾 Backup CSV: {backup_path}")

    if not FORCE:
        log("\n⚠️  Para aplicar correcciones, re-ejecuta con FORCE_CORRECTION=1")
        return

    # Aplicar correcciones de total
    log(f"\n🔧 Aplicando {total_corrections} correcciones de total...")
    updated = 0
    errors = 0
    with transaction.atomic():
        for r in rows:
            if not r["action"].startswith("CORRECT"):
                continue
            try:
                InteractionDetail.objects.filter(id=r["id"]).update(total=str(r["new_total"]))
                updated += 1
                if updated % 500 == 0:
                    log(f"   ... {updated} actualizados")
            except Exception as e:
                log(f"   ❌ Error id={r['id']}: {e}")
                errors += 1

    log(f"   Total actualizados: {updated}, errores: {errors}")

    # Recalcular total_diff y total_today_diff para registros afectados
    log("\n🔄 Recalculando total_diff y total_today_diff...")
    diff_updates = 0
    today_diff_updates = 0

    for pid in affected_point_ids:
        records = list(
            InteractionDetail.objects.filter(
                catchment_point_id=pid,
            ).order_by("date_time_medition").values(
                "id", "date_time_medition", "total", "total_diff", "total_today_diff"
            )
        )
        if not records:
            continue

        prev_total = 0.0
        first_total_of_day = {}
        current_day = None
        day_first_record = None

        for r in records:
            rid = r["id"]
            dt = r["date_time_medition"]
            in_range = START_DT <= dt.strftime("%Y-%m-%dT%H:%M:%S") < END_DT

            try:
                curr_total = float(r["total"]) if r["total"] not in (None, "", "None") else 0.0
            except (ValueError, TypeError):
                curr_total = 0.0

            # Detectar día nuevo
            day = dt.date()
            if current_day != day:
                current_day = day
                day_first_record = r
                first_total_of_day = curr_total

            # Solo recalcular si es del rango de backfill
            if not in_range:
                prev_total = curr_total
                continue

            # total_diff
            new_diff = max(0, round_total(curr_total) - round_total(prev_total))
            old_diff = r["total_diff"] or 0
            if new_diff != old_diff:
                try:
                    InteractionDetail.objects.filter(id=rid).update(total_diff=new_diff)
                    diff_updates += 1
                except Exception as e:
                    log(f"   ❌ Error diff id={rid}: {e}")

            # total_today_diff
            first_total = first_total_of_day if day_first_record else 0.0
            new_today_diff = max(0, round_total(curr_total) - round_total(first_total))
            old_today_diff = r["total_today_diff"] or 0
            if new_today_diff != old_today_diff:
                try:
                    InteractionDetail.objects.filter(id=rid).update(total_today_diff=new_today_diff)
                    today_diff_updates += 1
                except Exception as e:
                    log(f"   ❌ Error today_diff id={rid}: {e}")

            prev_total = curr_total

    log(f"   total_diff actualizados: {diff_updates}")
    log(f"   total_today_diff actualizados: {today_diff_updates}")

    log(f"\n✅ Recálculo completado!")
    log(f"   Total actualizados: {updated}")
    log(f"   diff actualizados: {diff_updates}")
    log(f"   today_diff actualizados: {today_diff_updates}")
    log(f"   Errores: {errors}")
    log(f"   Tiempo: {datetime.now() - start_time}")


if __name__ == "__main__":
    main()
