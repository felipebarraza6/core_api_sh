#!/usr/bin/env python3
"""
Fix extendido para Punto 62 — Corrige registros desde primer reset falso
hasta el último registro con total incorrecto.

El fix anterior solo cubrió el rango de fechas de los resets falsos (jun 18-23),
pero la addition falsa persistió hasta jun 24 cuando el usuario la reseteó.

Este script corrige TODOS los registros donde total != pulses en el rango afectado.
"""

import os
import sys
from datetime import datetime

sys.path.insert(0, "/app")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.settings")

import django
django.setup()

from django.db import transaction
from api.core.models import InteractionDetail, CounterResetLog, ProfileDataConfigCatchment

POINT_ID = 62
START_DT = "2026-06-18T21:26:00+00:00"
END_DT = "2026-06-24T19:01:00+00:00"


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def main():
    log(f"Fix extendido Punto {POINT_ID}")
    log(f"Rango: {START_DT} -> {END_DT}")

    # Encontrar registros a corregir
    regs = InteractionDetail.objects.filter(
        catchment_point_id=POINT_ID,
        is_error=False,
        date_time_medition__gte=START_DT,
        date_time_medition__lte=END_DT,
    ).exclude(total__isnull=True).order_by("date_time_medition")

    to_fix = []
    for r in regs:
        if r.pulses is not None:
            expected = int(float(r.pulses))
            actual = int(float(r.total))
            if expected != actual:
                to_fix.append((r.id, expected))

    log(f"Registros a corregir: {len(to_fix)}")

    if not to_fix:
        log("No hay registros para corregir.")
        return

    # Ejemplo
    for rid, exp in to_fix[:5]:
        reg = InteractionDetail.objects.get(id=rid)
        log(f"  id={rid}: {reg.date_time_medition} total={reg.total} -> {exp}")
    if len(to_fix) > 5:
        log(f"  ... y {len(to_fix) - 5} más")

    # Aplicar
    with transaction.atomic():
        corrected = 0
        for rid, new_total in to_fix:
            updated = InteractionDetail.objects.filter(id=rid).update(total=str(new_total))
            corrected += updated
        log(f"✓ {corrected} registros corregidos")

    # Verificar post-fix
    mismatches = 0
    regs_check = InteractionDetail.objects.filter(
        catchment_point_id=POINT_ID,
        is_error=False,
        date_time_medition__gte=START_DT,
        date_time_medition__lte=END_DT,
    ).exclude(total__isnull=True)

    for r in regs_check:
        if r.pulses is not None:
            expected = int(float(r.pulses))
            actual = int(float(r.total))
            if expected != actual:
                mismatches += 1

    log(f"Mismatches restantes en rango: {mismatches}")

    # Verificar últimos registros
    last_regs = InteractionDetail.objects.filter(
        catchment_point_id=POINT_ID,
        is_error=False,
    ).exclude(total__isnull=True).order_by("-date_time_medition")[:10]

    log("Últimos 10 registros:")
    for r in last_regs:
        exp = int(float(r.pulses)) if r.pulses else 0
        act = int(float(r.total)) if r.total else 0
        ok = "✓" if exp == act else "✗"
        log(f"  {r.date_time_medition} | pulses={r.pulses} | total={r.total} {ok}")


if __name__ == "__main__":
    main()
