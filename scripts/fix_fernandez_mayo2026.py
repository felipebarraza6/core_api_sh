#!/usr/bin/env python3
"""
CORRECCIÓN CRISIS REDIS — Productos Fernandez (puntos 61-64)
============================================================

Problema detectado:
- Durante la crisis Redis 19-22 mayo 2026 se generaron DOS capas de registros
  para los puntos TWIN del proyecto Productos Fernandez:
    * Capa errónea (batch 1): ids ~2966384-2970149, minutos 1/6/11...
      Guardó en `pulses` el valor total acumulado devuelto por TDATA y
      propagó `total` en cascada, generando totales irreales (~millones).
    * Capa backfill (batch 2): ids ~2974698-2985491, minutos 0/5/10...
      Trajo los pulsos correctos, pero como usó como base el total erróneo
      del batch 1, los `total` también quedaron inflados.

Estrategia:
1. Backup CSV de todos los registros afectados.
2. Eliminar la capa errónea (batch 1) en el rango de crisis.
3. Recalcular `total`, `total_diff` y `total_today_diff` para la capa
   backfill (batch 2) usando el último total válido previo al 20 may.
4. Opcionalmente recalcular `total_diff`/`total_today_diff` para los
   registros post-crisis para que sean coherentes (sin tocar `total`).

USO (dry-run por defecto):
    docker exec -u root -w /app django_api_secure python scripts/fix_fernandez_mayo2026.py

USO (aplicar):
    docker exec -u root -w /app -e FORCE_FIX=1 django_api_secure python scripts/fix_fernandez_mayo2026.py
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
from api.core.models import InteractionDetail, Variable, CatchmentPoint


POINT_IDS = [61, 62, 63, 64]
UTC = pytz.UTC
# Rango crisis en UTC: 19 may 20:00 CL = 20 may 00:00 UTC
#                       22 may 12:00 CL = 22 may 16:00 UTC
START_DT = UTC.localize(datetime(2026, 5, 20, 0, 0, 0))
END_DT = UTC.localize(datetime(2026, 5, 22, 16, 0, 0))
FORCE = os.environ.get("FORCE_FIX", "0") == "1"


def log(msg):
    print(msg, flush=True)


def round_total(val):
    return int(Decimal(str(val)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def get_factor_for_point(point_id):
    var = (
        Variable.objects.filter(
            scheme_catchment__points_catchment__id=point_id,
            type_variable="TOTALIZADO",
        )
        .select_related("scheme_catchment")
        .first()
    )
    return var.pulses_factor if var and var.pulses_factor else 1000


def safe_float(s, default=0.0):
    try:
        return float(s) if s not in (None, "", "None") else default
    except (ValueError, TypeError):
        return default


def main():
    log("=" * 70)
    log("CORRECCIÓN CRISIS REDIS — Productos Fernandez (puntos 61-64)")
    log("=" * 70)
    log(f"Rango crisis (UTC): {START_DT} → {END_DT}")
    log(f"Modo: {'APLICAR CAMBIOS REALES' if FORCE else 'DRY-RUN'}")
    log("")

    # -------------------------------------------------------------------------
    # 1. AUDITAR Y REPORTAR
    # -------------------------------------------------------------------------
    all_records = list(
        InteractionDetail.objects.filter(
            catchment_point_id__in=POINT_IDS,
            date_time_medition__gte=START_DT,
            date_time_medition__lt=END_DT,
        ).order_by("catchment_point_id", "date_time_medition").values(
            "id", "catchment_point_id", "date_time_medition",
            "pulses", "total", "total_diff", "total_today_diff",
        )
    )

    log(f"📊 Registros en rango: {len(all_records)}")

    # Identificar batch erróneo: minuto % 5 == 1  (la serie falsa)
    # Usamos además total_diff > 10000 como confirmación de anomalía grave.
    batch_erroneo = []
    batch_backfill = []
    for r in all_records:
        dt = r["date_time_medition"]
        minute = dt.minute
        if minute % 5 == 1:
            # Confirmar que es anómalo (total_diff descomunal)
            if (r["total_diff"] or 0) > 10000:
                batch_erroneo.append(r)
            else:
                # Puede ser post-crisis normal; no tocar
                pass
        elif minute % 5 == 0:
            batch_backfill.append(r)

    log(f"   Capa errónea (minuto 1/6/11, diff>10000): {len(batch_erroneo)}")
    log(f"   Capa backfill (minuto 0/5/10):             {len(batch_backfill)}")
    log("")

    if len(batch_erroneo) == 0 and len(batch_backfill) == 0:
        log("✅ No hay registros a corregir.")
        return

    # -------------------------------------------------------------------------
    # 2. BACKUP CSV
    # -------------------------------------------------------------------------
    backup_dir = "/app/backups"
    os.makedirs(backup_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{backup_dir}/fix_fernandez_mayo2026_antes_{ts}.csv"

    fieldnames = [
        "id", "catchment_point_id", "date_time_medition",
        "pulses", "total", "total_diff", "total_today_diff",
    ]
    with open(backup_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in all_records:
            writer.writerow({k: r[k] for k in fieldnames})
    log(f"💾 Backup guardado: {backup_path}")
    log("")

    if not FORCE:
        # Muestra de lo que haría
        log("📝 Muestra de correcciones que se aplicarían:")
        for pid in POINT_IDS:
            factor = get_factor_for_point(pid)
            prev = (
                InteractionDetail.objects.filter(
                    catchment_point_id=pid,
                    date_time_medition__lt=START_DT,
                )
                .exclude(total__isnull=True)
                .exclude(total="")
                .exclude(total="None")
                .order_by("-date_time_medition")
                .values("pulses", "total", "date_time_medition")
                .first()
            )
            if prev:
                log(f"   Punto {pid}: último válido previo @ {prev['date_time_medition']} "
                    f"pulses={prev['pulses']} total={prev['total']} factor={factor}")
            else:
                log(f"   Punto {pid}: NO se encontró registro previo válido")

            muestra = [r for r in batch_backfill if r["catchment_point_id"] == pid][:5]
            for r in muestra:
                log(f"      → {r['date_time_medition']} pulses={r['pulses']} "
                    f"old_total={r['total']} old_diff={r['total_diff']}")
        log("")
        log("⚠️  Para aplicar correcciones reales, re-ejecuta con FORCE_FIX=1")
        return

    # -------------------------------------------------------------------------
    # 3. APLICAR CORRECCIONES
    # -------------------------------------------------------------------------
    log("🔧 Aplicando correcciones...")

    # 3.1 Eliminar capa errónea
    ids_erroneos = [r["id"] for r in batch_erroneo]
    if ids_erroneos:
        deleted, _ = InteractionDetail.objects.filter(id__in=ids_erroneos).delete()
        log(f"   🗑️  Registros erróneos eliminados: {deleted}")

    # 3.2 Recalcular total / diff / today_diff por punto
    total_updates = 0
    diff_updates = 0
    today_updates = 0

    for pid in POINT_IDS:
        factor = get_factor_for_point(pid)

        # Último registro del batch 2 (backfill) para este punto;
        # recalculamos solo hasta ahí para no tocar datos post-crisis
        # del cron normal.
        last_backfill = (
            InteractionDetail.objects.filter(
                catchment_point_id=pid,
                date_time_medition__gte=START_DT,
                date_time_medition__lt=END_DT,
            )
            .extra(where=["EXTRACT(MINUTE FROM date_time_medition)::int % 5 = 0"])
            .order_by("-date_time_medition")
            .values("date_time_medition")
            .first()
        )
        recalc_end = last_backfill["date_time_medition"] if last_backfill else END_DT

        # Último registro válido ANTES del rango crisis
        prev_record = (
            InteractionDetail.objects.filter(
                catchment_point_id=pid,
                date_time_medition__lt=START_DT,
            )
            .exclude(total__isnull=True)
            .exclude(total="")
            .exclude(total="None")
            .order_by("-date_time_medition")
            .values("pulses", "total", "date_time_medition")
            .first()
        )
        if not prev_record:
            log(f"   ⚠️ Punto {pid}: sin registro previo válido, se omite.")
            continue

        prev_total = safe_float(prev_record["total"], 0.0)
        prev_pulses = safe_float(prev_record["pulses"], 0.0)

        # Tomamos TODOS los registros del punto en orden cronológico,
        # desde justo después del último válido hasta END_DT.
        records = list(
            InteractionDetail.objects.filter(
                catchment_point_id=pid,
                date_time_medition__gte=prev_record["date_time_medition"],
                date_time_medition__lte=recalc_end,
            ).order_by("date_time_medition").values(
                "id", "date_time_medition", "pulses", "total",
                "total_diff", "total_today_diff",
            )
        )

        # Saltamos el primer registro (es prev_record) para no recalcularlo
        records = [r for r in records if r["id"] != prev_record.get("id")]

        current_day = prev_record["date_time_medition"].date()
        first_total_of_day = prev_total
        day_first_id = None

        updates = []

        for r in records:
            rid = r["id"]
            dt = r["date_time_medition"]
            cp = safe_float(r["pulses"], 0.0)
            old_total = safe_float(r["total"], 0.0)
            old_diff = r["total_diff"] or 0
            old_today = r["total_today_diff"] or 0

            # Detectar día nuevo
            if dt.date() != current_day:
                current_day = dt.date()
                first_total_of_day = prev_total
                day_first_id = rid

            # Calcular diff de pulsos
            if cp == 0:
                # Hueco sin datos: conservar baseline anterior
                pulse_diff = 0
                new_total = prev_total
                skip_baseline_update = True
            elif cp >= prev_pulses:
                pulse_diff = cp - prev_pulses
                skip_baseline_update = False
            else:
                # Reset detectado: asumimos que el contador se reinició
                pulse_diff = cp
                skip_baseline_update = False

            new_total = prev_total + (pulse_diff * factor) / 1000.0
            new_total_rounded = round_total(new_total)

            new_diff = max(0, new_total_rounded - round_total(prev_total))
            new_today = max(0, new_total_rounded - round_total(first_total_of_day))
            # El primer registro del día debe tener today_diff=0
            if day_first_id == rid:
                new_today = 0

            changes = {}
            if abs(new_total_rounded - round_total(old_total)) > 0:
                changes["total"] = str(new_total_rounded)
            if new_diff != old_diff:
                changes["total_diff"] = new_diff
            if new_today != old_today:
                changes["total_today_diff"] = new_today

            if changes:
                updates.append((rid, changes))

            prev_total = new_total
            if not skip_baseline_update:
                prev_pulses = cp

        # Aplicar actualizaciones en bloques
        with transaction.atomic():
            for rid, changes in updates:
                InteractionDetail.objects.filter(id=rid).update(**changes)

        total_updates += sum(1 for _, c in updates if "total" in c)
        diff_updates += sum(1 for _, c in updates if "total_diff" in c)
        today_updates += sum(1 for _, c in updates if "total_today_diff" in c)

        log(f"   ✅ Punto {pid}: {len(updates)} registros ajustados "
            f"(total={sum(1 for _,c in updates if 'total' in c)}, "
            f"diff={sum(1 for _,c in updates if 'total_diff' in c)}, "
            f"today={sum(1 for _,c in updates if 'total_today_diff' in c)})")

    log("")
    log("=" * 70)
    log("RESUMEN DE CORRECCIÓN")
    log("=" * 70)
    log(f"Registros erróneos eliminados: {len(ids_erroneos)}")
    log(f"Registros con total corregido:  {total_updates}")
    log(f"Registros con total_diff corregido: {diff_updates}")
    log(f"Registros con total_today_diff corregido: {today_updates}")
    log(f"Backup: {backup_path}")
    log("✅ Proceso completado.")


if __name__ == "__main__":
    main()
