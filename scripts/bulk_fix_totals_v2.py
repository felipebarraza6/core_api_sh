#!/usr/bin/env python3
"""
Bulk Fix v2: Corregir total en puntos con addition=0.

Fórmula correcta: total = (pulses * pulses_factor) / 1000

Solo corrige puntos con addition=0 (donde no hay adición dinámica).
"""
import os, sys
from datetime import datetime
from collections import defaultdict

sys.path.insert(0, "/app")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.settings")
import django
django.setup()

from django.db import transaction
from api.core.models import InteractionDetail, ProfileDataConfigCatchment, SchemesCatchment, Variable


def log(msg, level="INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [{level}] {msg}", flush=True)


def main():
    apply = "--apply" in sys.argv
    point_filter = None
    for arg in sys.argv:
        if arg.startswith("--point="):
            point_filter = int(arg.split("=")[1])

    profiles = ProfileDataConfigCatchment.objects.filter(
        is_telemetry=True, addition=0
    ).select_related('point_catchment')

    total_fixed = 0
    total_points = 0
    total_records = 0

    log("=" * 60)
    log(f"MODO: {'APLICAR' if apply else 'DRY-RUN'}")
    log("=" * 60)

    for p in profiles:
        cp = p.point_catchment
        if point_filter and cp.id != point_filter:
            continue

        scheme = SchemesCatchment.objects.filter(points_catchment=cp).first()
        if not scheme:
            continue
        totalizador = Variable.objects.filter(
            scheme_catchment=scheme, type_variable='TOTALIZADO'
        ).first()
        if not totalizador:
            continue

        factor = totalizador.pulses_factor

        regs = InteractionDetail.objects.filter(
            catchment_point=cp, is_error=False
        ).exclude(pulses=0).exclude(pulses__lt=0).exclude(total__isnull=True)

        fixable = []
        for r in regs:
            if r.pulses and r.total:
                expected = int(round((float(r.pulses) * factor) / 1000.0))
                actual = int(float(r.total))
                if expected != actual:
                    fixable.append((r.id, r.date_time_medition, float(r.pulses), float(r.total), expected))

        if not fixable:
            continue

        total_points += 1
        total_records += len(fixable)

        if not apply:
            log(f"Punto {cp.id} ({cp.title}) factor={factor}: {len(fixable)} registros")
            for i, (rid, dt, pulses, old_t, new_t) in enumerate(fixable[:3]):
                log(f"  {dt} | pulses={pulses:.0f} | total={old_t:.0f} -> {new_t:.0f}")
            if len(fixable) > 3:
                log(f"  ... y {len(fixable) - 3} más")
            continue

        # Apply fix
        batch_size = 500
        batches = [fixable[i:i + batch_size] for i in range(0, len(fixable), batch_size)]
        fixed = 0
        for batch_idx, batch in enumerate(batches):
            with transaction.atomic():
                for rid, dt, pulses, old_t, new_t in batch:
                    InteractionDetail.objects.filter(id=rid).update(total=str(int(new_t)))
                fixed += len(batch)
            if (batch_idx + 1) % 10 == 0:
                log(f"  Progreso Punto {cp.id}: {fixed}/{len(fixable)}")
        log(f"✓ Punto {cp.id} ({cp.title}): {fixed} registros corregidos")
        total_fixed += fixed

    log("=" * 60)
    if apply:
        log(f"✓ {total_fixed} registros corregidos en {total_points} puntos")
    else:
        log(f"Registros a corregir: {total_records} en {total_points} puntos")
        log("Usa --apply para aplicar los fixes.")
    log("=" * 60)


if __name__ == "__main__":
    main()
