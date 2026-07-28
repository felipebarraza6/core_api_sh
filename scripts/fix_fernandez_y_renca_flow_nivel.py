#!/usr/bin/env python3
"""
CORRECCIÓN CRISIS REDIS — Productos Fernandez (61-64) + PF Renca (146)
======================================================================
1. Recalcula total/total_diff/total_today_diff para punto 146 (igual que 61-64).
2. Recalcula flow para todos los puntos desde los totales corregidos.
3. Corrige nivel: si está entre 100-999 y termina en .00 -> /10.
   Si es 0.00 durante la crisis -> interpolación lineal.

USO (dry-run por defecto):
    docker exec -u root -w /app django_api_secure python scripts/fix_fernandez_y_renca_flow_nivel.py

USO (aplicar):
    docker exec -u root -w /app -e FORCE_FIX=1 django_api_secure python scripts/fix_fernandez_y_renca_flow_nivel.py
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


POINT_IDS = [61, 62, 63, 64, 146]
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


def recalc_totals_for_point(pid, factor):
    """Recalcular total/diff/today para punto 146 (misma lógica que fix_fernandez_mayo2026)."""
    # Solo punto 146 necesita recalcular totales; 61-64 ya fueron corregidos
    if pid != 146:
        return []

    prev_record = (
        InteractionDetail.objects.filter(
            catchment_point_id=pid,
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
        log(f"   ⚠️ Punto {pid}: sin registro previo válido, se omite total.")
        return []

    prev_total = safe_float(prev_record["total"], 0.0)
    prev_pulses = safe_float(prev_record["pulses"], 0.0)
    current_day = prev_record["date_time_medition"].date()
    first_total_of_day = prev_total
    day_first_id = None

    records = list(
        InteractionDetail.objects.filter(
            catchment_point_id=pid,
            date_time_medition__gte=prev_record["date_time_medition"],
            date_time_medition__lte=END_DT,
        ).order_by("date_time_medition").values(
            "id", "date_time_medition", "pulses", "total",
            "total_diff", "total_today_diff",
        )
    )
    # Saltar el previo
    records = [r for r in records if r["id"] != prev_record.get("id")]

    updates = []
    for r in records:
        rid = r["id"]
        dt = r["date_time_medition"]
        cp = safe_float(r["pulses"], 0.0)
        old_total = safe_float(r["total"], 0.0)
        old_diff = r["total_diff"] or 0
        old_today = r["total_today_diff"] or 0

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

        new_total = prev_total + (pulse_diff * factor) / 1000.0
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
        if changes:
            updates.append((rid, changes))

        prev_total = new_total
        if not skip_baseline:
            prev_pulses = cp

    return updates


def recalc_flow_for_point(pid):
    """Recalcular flow desde totales corregidos."""
    records = list(
        InteractionDetail.objects.filter(
            catchment_point_id=pid,
            date_time_medition__gte=START_DT,
            date_time_medition__lte=END_DT,
        ).order_by("date_time_medition").values(
            "id", "date_time_medition", "total", "flow"
        )
    )
    if not records:
        return []

    # Obtener el registro inmediatamente anterior a START_DT para calcular el primer diff
    prev = (
        InteractionDetail.objects.filter(
            catchment_point_id=pid,
            date_time_medition__lt=START_DT,
        )
        .exclude(total__isnull=True)
        .exclude(total="")
        .exclude(total="None")
        .order_by("-date_time_medition")
        .values("id", "date_time_medition", "total")
        .first()
    )
    prev_total = safe_float(prev["total"], 0.0) if prev else 0.0
    prev_dt = prev["date_time_medition"] if prev else None

    updates = []
    for r in records:
        rid = r["id"]
        dt = r["date_time_medition"]
        curr_total = safe_float(r["total"], 0.0)
        old_flow = safe_float(r["flow"], 0.0)

        new_flow = 0.0
        if prev_dt and dt and curr_total >= prev_total:
            dt_seconds = (dt - prev_dt).total_seconds()
            if dt_seconds > 0:
                diff = curr_total - prev_total
                if diff >= 0:
                    new_flow = round((diff / dt_seconds) * 1000.0, 2)

        # Clamp anti-spike básico
        if new_flow > 150.0:
            new_flow = 0.0

        if abs(new_flow - old_flow) > 0.005:
            updates.append((rid, {"flow": new_flow}))

        prev_total = curr_total
        prev_dt = dt

    return updates


def fix_nivel_for_point(pid):
    """
    Corregir nivel:
    - Si valor entre 100 y 999 y termina en .00 -> dividir por 10.
    - Si es 0.00 durante la crisis (excepto primer/ultimo registro del rango) -> interpolar.
    """
    records = list(
        InteractionDetail.objects.filter(
            catchment_point_id=pid,
            date_time_medition__gte=START_DT,
            date_time_medition__lte=END_DT,
        ).order_by("date_time_medition").values(
            "id", "date_time_medition", "nivel"
        )
    )
    if not records:
        return []

    # Buscar nivel pre-crisis (último antes de START_DT)
    prev = (
        InteractionDetail.objects.filter(
            catchment_point_id=pid,
            date_time_medition__lt=START_DT,
        )
        .exclude(nivel__isnull=True)
        .order_by("-date_time_medition")
        .values("date_time_medition", "nivel")
        .first()
    )
    # Buscar nivel post-crisis (primero después de END_DT)
    post = (
        InteractionDetail.objects.filter(
            catchment_point_id=pid,
            date_time_medition__gt=END_DT,
        )
        .exclude(nivel__isnull=True)
        .order_by("date_time_medition")
        .values("date_time_medition", "nivel")
        .first()
    )

    prev_nivel = safe_float(prev["nivel"], None) if prev else None
    post_nivel = safe_float(post["nivel"], None) if post else None
    prev_dt = prev["date_time_medition"] if prev else None
    post_dt = post["date_time_medition"] if post else None

    updates = []
    recs_count = len(records)

    for idx, r in enumerate(records):
        rid = r["id"]
        dt = r["date_time_medition"]
        old_nivel = safe_float(r["nivel"], 0.0)
        new_nivel = old_nivel

        # Regla 1: si está entre 100 y 999.99 y termina en .00 exacto -> probablemente ×10
        if 100 <= old_nivel <= 999.99 and abs(old_nivel - round(old_nivel)) < 0.001:
            new_nivel = round(old_nivel / 10.0, 2)
        # Regla 2: si es 0.00 y tenemos ambos extremos, interpolar
        elif old_nivel == 0.0 and prev_nivel is not None and post_nivel is not None and prev_dt and post_dt:
            total_span = (post_dt - prev_dt).total_seconds()
            curr_span = (dt - prev_dt).total_seconds()
            if total_span > 0:
                ratio = curr_span / total_span
                new_nivel = round(prev_nivel + (post_nivel - prev_nivel) * ratio, 2)

        if abs(new_nivel - old_nivel) > 0.005:
            updates.append((rid, {"nivel": new_nivel}))

    return updates


def main():
    log("=" * 70)
    log("CORRECCIÓN CRISIS REDIS — Fernandez (61-64) + Renca (146)")
    log("=" * 70)
    log(f"Rango crisis (UTC): {START_DT} → {END_DT}")
    log(f"Modo: {'APLICAR CAMBIOS REALES' if FORCE else 'DRY-RUN'}")
    log("")

    backup_dir = "/app/backups"
    os.makedirs(backup_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{backup_dir}/fix_fernandez_renca_nivel_flow_antes_{ts}.csv"

    # Backup de todos los registros afectados (incluyendo nivel y flow)
    all_records = list(
        InteractionDetail.objects.filter(
            catchment_point_id__in=POINT_IDS,
            date_time_medition__gte=START_DT,
            date_time_medition__lte=END_DT,
        ).order_by("catchment_point_id", "date_time_medition").values(
            "id", "catchment_point_id", "date_time_medition",
            "pulses", "total", "total_diff", "total_today_diff",
            "flow", "nivel",
        )
    )
    fieldnames = [
        "id", "catchment_point_id", "date_time_medition",
        "pulses", "total", "total_diff", "total_today_diff",
        "flow", "nivel",
    ]
    with open(backup_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in all_records:
            writer.writerow({k: r[k] for k in fieldnames})
    log(f"💾 Backup guardado: {backup_path} ({len(all_records)} registros)")
    log("")

    total_all_updates = 0

    for pid in POINT_IDS:
        log(f"🔧 Procesando punto {pid}...")
        factor = get_factor_for_point(pid)

        # 1. Totales (solo 146 necesita recalcular totales; 61-64 ya están OK)
        total_updates = recalc_totals_for_point(pid, factor)
        log(f"   Totales a ajustar: {len(total_updates)}")

        # 2. Flow
        flow_updates = recalc_flow_for_point(pid)
        log(f"   Flow a ajustar: {len(flow_updates)}")

        # 3. Nivel
        nivel_updates = fix_nivel_for_point(pid)
        log(f"   Nivel a ajustar: {len(nivel_updates)}")

        # Merge updates por id
        merged = {}
        for rid, changes in total_updates + flow_updates + nivel_updates:
            if rid not in merged:
                merged[rid] = {}
            merged[rid].update(changes)

        if merged:
            log(f"   → Total registros a modificar: {len(merged)}")
            if not FORCE:
                # Mostrar muestra
                for rid, changes in list(merged.items())[:5]:
                    log(f"      id={rid} → {changes}")
                if len(merged) > 5:
                    log(f"      ... y {len(merged)-5} más")
            else:
                with transaction.atomic():
                    for rid, changes in merged.items():
                        InteractionDetail.objects.filter(id=rid).update(**changes)
                total_all_updates += len(merged)
        else:
            log(f"   → Sin cambios necesarios")
        log("")

    log("=" * 70)
    log("RESUMEN")
    log("=" * 70)
    log(f"Registros modificados: {total_all_updates}")
    log(f"Backup: {backup_path}")
    if not FORCE:
        log("⚠️  Esto fue simulación. Para aplicar re-ejecuta con FORCE_FIX=1")
    else:
        log("✅ Cambios aplicados.")


if __name__ == "__main__":
    main()
