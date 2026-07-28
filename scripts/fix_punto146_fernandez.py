#!/usr/bin/env python3
"""
CORRECCIÓN CRISIS REDIS — Punto 146 (PF Renca)
==============================================
1. Elimina capa errónea (minuto 1/6/11) en rango crisis.
2. Recalcula total/diff/today para capa backfill (minuto 0/5/10).
3. Recalcula flow.
4. Corrige nivel (÷10 si >100 y .00, interpola si 0).

USO (dry-run por defecto):
    docker exec -u root -w /app django_api_secure python scripts/fix_punto146_fernandez.py

USO (aplicar):
    docker exec -u root -w /app -e FORCE_FIX=1 django_api_secure python scripts/fix_punto146_fernandez.py
"""

import os
import sys
import csv
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

import pytz

sys.path.insert(0, "/app")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.settings")
import django
django.setup()

from django.db import transaction
from api.core.models import InteractionDetail


POINT_ID = 146
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
    log("CORRECCIÓN CRISIS REDIS — Punto 146 (PF Renca)")
    log("=" * 60)
    log(f"Rango crisis (UTC): {START_DT} → {END_DT}")
    log(f"Modo: {'APLICAR CAMBIOS REALES' if FORCE else 'DRY-RUN'}")
    log("")

    # -------------------------------------------------------------------------
    # 1. IDENTIFICAR Y BACKUP
    # -------------------------------------------------------------------------
    all_records = list(
        InteractionDetail.objects.filter(
            catchment_point_id=POINT_ID,
            date_time_medition__gte=START_DT,
            date_time_medition__lt=END_DT,
        ).order_by("date_time_medition").values(
            "id", "date_time_medition", "pulses", "total",
            "total_diff", "total_today_diff", "flow", "nivel",
        )
    )

    batch_erroneo = [r for r in all_records if r["date_time_medition"].minute % 5 == 1]
    batch_backfill = [r for r in all_records if r["date_time_medition"].minute % 5 == 0]

    log(f"📊 Registros en rango: {len(all_records)}")
    log(f"   Capa errónea (minuto 1/6/11): {len(batch_erroneo)}")
    log(f"   Capa backfill (minuto 0/5/10): {len(batch_backfill)}")
    log("")

    # Backup CSV
    backup_dir = "/app/backups"
    os.makedirs(backup_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{backup_dir}/fix_punto146_antes_{ts}.csv"
    fieldnames = [
        "id", "date_time_medition", "pulses", "total",
        "total_diff", "total_today_diff", "flow", "nivel",
    ]
    with open(backup_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in all_records:
            writer.writerow({k: r[k] for k in fieldnames})
    log(f"💾 Backup guardado: {backup_path}")
    log("")

    if not FORCE:
        log("📝 Muestra de registros erróneos a eliminar:")
        for r in batch_erroneo[:5]:
            log(f"   id={r['id']} {r['date_time_medition']} pulses={r['pulses']} total={r['total']}")
        if len(batch_erroneo) > 5:
            log(f"   ... y {len(batch_erroneo)-5} más")
        log("")
        log("⚠️  Para aplicar correcciones reales, re-ejecuta con FORCE_FIX=1")
        return

    # -------------------------------------------------------------------------
    # 2. ELIMINAR CAPA ERRÓNEA
    # -------------------------------------------------------------------------
    ids_erroneos = [r["id"] for r in batch_erroneo]
    if ids_erroneos:
        deleted, _ = InteractionDetail.objects.filter(id__in=ids_erroneos).delete()
        log(f"🗑️  Registros erróneos eliminados: {deleted}")

    # -------------------------------------------------------------------------
    # 3. RECALCULAR TOTAL / DIFF / TODAY PARA BACKFILL
    # -------------------------------------------------------------------------
    prev_record = (
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
    if not prev_record:
        log("⚠️ No se encontró registro previo válido. Abortando.")
        return

    log(f"Último previo válido: {prev_record['date_time_medition']} pulses={prev_record['pulses']} total={prev_record['total']}")

    # Tomar TODOS los registros del punto desde justo después del previo hasta END_DT
    records = list(
        InteractionDetail.objects.filter(
            catchment_point_id=POINT_ID,
            date_time_medition__gte=prev_record["date_time_medition"],
            date_time_medition__lte=END_DT,
        ).order_by("date_time_medition").values(
            "id", "date_time_medition", "pulses", "total",
            "total_diff", "total_today_diff", "flow", "nivel",
        )
    )
    # Saltar el previo
    records = [r for r in records if r["id"] != prev_record.get("id")]

    prev_total = safe_float(prev_record["total"], 0.0)
    prev_pulses = safe_float(prev_record["pulses"], 0.0)
    current_day = prev_record["date_time_medition"].date()
    first_total_of_day = prev_total
    day_first_id = None

    total_updates = 0
    flow_updates = 0
    nivel_updates = 0

    # Preparar interpolación de nivel
    post_record = (
        InteractionDetail.objects.filter(
            catchment_point_id=POINT_ID,
            date_time_medition__gt=END_DT,
        )
        .exclude(nivel__isnull=True)
        .order_by("date_time_medition")
        .values("date_time_medition", "nivel")
        .first()
    )
    post_nivel = safe_float(post_record["nivel"], None) if post_record else None
    post_dt = post_record["date_time_medition"] if post_record else None
    prev_dt = prev_record["date_time_medition"]
    prev_nivel = safe_float(
        InteractionDetail.objects.filter(id=prev_record["id"]).values_list("nivel", flat=True).first(),
        None,
    )

    with transaction.atomic():
        for i, r in enumerate(records):
            rid = r["id"]
            dt = r["date_time_medition"]
            cp = safe_float(r["pulses"], 0.0)
            old_total = safe_float(r["total"], 0.0)
            old_diff = r["total_diff"] or 0
            old_today = r["total_today_diff"] or 0
            old_flow = safe_float(r["flow"], 0.0)
            old_nivel = safe_float(r["nivel"], 0.0)

            # Detectar día nuevo
            if dt.date() != current_day:
                current_day = dt.date()
                first_total_of_day = prev_total
                day_first_id = rid

            # Calcular diff de pulsos (con anti-ruido)
            if cp == 0:
                pulse_diff = 0
                new_total = prev_total
                skip_baseline = True
            elif cp >= prev_pulses:
                pulse_diff = cp - prev_pulses
                skip_baseline = False
            else:
                # Si el decremento es pequeño (< 10), tratar como ruido (diff=0)
                if prev_pulses - cp < 10:
                    pulse_diff = 0
                    skip_baseline = True
                else:
                    pulse_diff = cp
                    skip_baseline = False

            new_total = prev_total + (pulse_diff * FACTOR) / 1000.0
            new_total_r = round_total(new_total)
            new_diff = max(0, new_total_r - round_total(prev_total))
            new_today = max(0, new_total_r - round_total(first_total_of_day)) if day_first_id != rid else 0

            changes = {}
            if new_total_r != round_total(old_total):
                changes["total"] = str(new_total_r)
            if new_diff != old_diff:
                changes["total_diff"] = new_diff
            if new_today != old_today:
                changes["total_today_diff"] = new_today

            # Recalcular flow
            calc_flow = 0.0
            if i > 0 or prev_total > 0:
                dt_seconds = (dt - prev_dt).total_seconds()
                if dt_seconds > 0:
                    diff_total = new_total_r - round_total(prev_total)
                    if diff_total > 0:
                        calc_flow = round((diff_total / dt_seconds) * 1000.0, 2)
                        if calc_flow > 150.0:
                            calc_flow = 0.0
            if abs(calc_flow - old_flow) > 0.005:
                changes["flow"] = calc_flow

            # Corregir nivel
            new_nivel = old_nivel
            if 100 <= old_nivel <= 999.99 and abs(old_nivel - round(old_nivel)) < 0.001:
                new_nivel = round(old_nivel / 10.0, 2)
            elif old_nivel == 0.0 and prev_nivel is not None and post_nivel is not None:
                total_span = (post_dt - prev_dt).total_seconds()
                curr_span = (dt - prev_dt).total_seconds()
                if total_span > 0:
                    ratio = curr_span / total_span
                    new_nivel = round(prev_nivel + (post_nivel - prev_nivel) * ratio, 2)

            if abs(new_nivel - old_nivel) > 0.005:
                changes["nivel"] = new_nivel

            if changes:
                InteractionDetail.objects.filter(id=rid).update(**changes)
                if "total" in changes or "total_diff" in changes or "total_today_diff" in changes:
                    total_updates += 1
                if "flow" in changes:
                    flow_updates += 1
                if "nivel" in changes:
                    nivel_updates += 1

            prev_total = new_total
            if not skip_baseline:
                prev_pulses = cp
            prev_dt = dt

    log(f"✅ Punto {POINT_ID} ajustado:")
    log(f"   Total/diff/today: {total_updates}")
    log(f"   Flow: {flow_updates}")
    log(f"   Nivel: {nivel_updates}")
    log(f"   Backup: {backup_path}")


if __name__ == "__main__":
    main()
