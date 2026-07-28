#!/usr/bin/env python3
"""
Relleno hueco punto 61 (Planta 1 P1) — 22 mayo 12:30–16:00 UTC.
Elimina residuos erróneos e inserta registros de relleno (pulses=0, total congelado).
Luego recalcula diffs/today_diff para todo el rango continuo.
"""

import os, sys
sys.path.insert(0, "/app")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.settings")
import django
django.setup()

import pytz
from datetime import datetime, timedelta
from django.db import transaction
from api.core.models import InteractionDetail

POINT_ID = 61
FACTOR = 1000
UTC = pytz.UTC
GAP_START = UTC.localize(datetime(2026, 5, 22, 12, 30, 0))
GAP_END = UTC.localize(datetime(2026, 5, 22, 16, 0, 0))
FORCE = os.environ.get("FORCE_FIX", "0") == "1"


def log(msg):
    print(msg, flush=True)


def main():
    log("=" * 60)
    log(f"Relleno hueco punto {POINT_ID} — 22 mayo 12:30→16:00 UTC")
    log("=" * 60)
    log(f"Modo: {'APLICAR' if FORCE else 'DRY-RUN'}")

    # 1. Identificar y eliminar residuos erróneos en ese rango (minuto 1/6/11)
    residuos = list(
        InteractionDetail.objects.filter(
            catchment_point_id=POINT_ID,
            date_time_medition__gte=GAP_START,
            date_time_medition__lt=GAP_END,
        ).order_by("date_time_medition")
    )
    log(f"Residuos encontrados en hueco: {len(residuos)}")
    for r in residuos[:5]:
        log(f"   {r.date_time_medition.isoformat()} pulses={r.pulses} total={r.total}")

    # 2. Último total válido antes del hueco (12:25 UTC)
    prev = (
        InteractionDetail.objects.filter(
            catchment_point_id=POINT_ID,
            date_time_medition__lt=GAP_START,
        )
        .order_by("-date_time_medition")
        .first()
    )
    if not prev:
        log("⚠️ No se encontró registro previo. Abortando.")
        return
    log(f"Último previo: {prev.date_time_medition.isoformat()} total={prev.total}")

    # 3. Buckets faltantes (múltiplos de 5)
    existing_set = set(
        InteractionDetail.objects.filter(
            catchment_point_id=POINT_ID,
            date_time_medition__gte=GAP_START,
            date_time_medition__lt=GAP_END,
        ).values_list("date_time_medition", flat=True)
    )
    missing = []
    current = GAP_START
    while current < GAP_END:
        if current not in existing_set:
            missing.append(current)
        current += timedelta(minutes=5)
    log(f"Buckets faltantes: {len(missing)}")

    if not FORCE:
        log("⚠️  Esto fue simulación. Re-ejecuta con FORCE_FIX=1")
        return

    # 4. Eliminar residuos e insertar relleno
    with transaction.atomic():
        if residuos:
            ids_del = [r.id for r in residuos]
            InteractionDetail.objects.filter(id__in=ids_del).delete()
            log(f"🗑️  Eliminados {len(ids_del)} residuos.")

        last_total = prev.total
        last_pulses = prev.pulses
        created_count = 0
        for dt in missing:
            InteractionDetail.objects.create(
                catchment_point_id=POINT_ID,
                date_time_medition=dt,
                date_time_last_logger=dt,
                pulses=0,
                total=str(last_total),
                total_diff=0,
                total_today_diff=0,  # se recalculará después
                is_error=False,
                is_partial=False,
                variable_details=[],
                variable_values={},
            )
            created_count += 1
        log(f"➕ Insertados {created_count} registros de relleno.")

        # 5. Recalcular diffs para todo el rango continuo 12:25 → 16:05
        recs = list(
            InteractionDetail.objects.filter(
                catchment_point_id=POINT_ID,
                date_time_medition__gte=prev.date_time_medition,
                date_time_medition__lte=UTC.localize(datetime(2026, 5, 22, 16, 5, 0)),
            ).order_by("date_time_medition")
        )
        prev_total = float(prev.total) if prev.total not in (None, "", "None") else 0.0
        prev_pulses = float(prev.pulses) if prev.pulses is not None else 0.0
        current_day = prev.date_time_medition.date()
        first_total_of_day = None

        for r in recs:
            if r.id == prev.id:
                first_total_of_day = float(r.total) if r.total not in (None, "", "None") else 0.0
                continue
            dt = r.date_time_medition
            cp = float(r.pulses) if r.pulses is not None else 0.0
            if dt.date() != current_day:
                current_day = dt.date()
                first_total_of_day = None

            if cp == 0:
                pulse_diff = 0
                new_total = prev_total
                skip = True
            elif cp >= prev_pulses:
                pulse_diff = cp - prev_pulses
                skip = False
            else:
                pulse_diff = cp
                skip = False

            new_total = prev_total + (pulse_diff * FACTOR) / 1000.0
            new_total_r = int(round(new_total))
            new_diff = max(0, new_total_r - int(round(prev_total)))
            if first_total_of_day is None:
                new_today = 0
                first_total_of_day = new_total_r
            else:
                new_today = max(0, new_total_r - int(round(first_total_of_day)))

            r.total = str(new_total_r)
            r.total_diff = new_diff
            r.total_today_diff = new_today
            r.save(update_fields=["total", "total_diff", "total_today_diff"])

            prev_total = new_total
            if not skip:
                prev_pulses = cp

    log("✅ Relleno y recálculo completado.")


if __name__ == "__main__":
    main()
