#!/usr/bin/env python3
"""
Bulk Fix: Corregir total != pulses en todos los puntos con addition=0.

Problema: Puntos que tuvieron addition > 0 en el pasado (por resets reales o
falsos NOISE_DROP), se les reseteó addition a 0, pero los registros históricos
quedaron con total = pulses + addition (inflado).

Fix: total = pulses para todos los registros con pulses > 0 y addition=0.
"""
import os, sys, argparse
from datetime import datetime, timedelta
from decimal import Decimal

sys.path.insert(0, "/app")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.settings")
import django
django.setup()

from django.db import transaction
from api.core.models import InteractionDetail, ProfileDataConfigCatchment, CounterResetLog


def log(msg, level="INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [{level}] {msg}", flush=True)


def fix_point(cp_id, title, apply=False):
    """Fix all records where total != pulses for a point with addition=0."""
    regs = InteractionDetail.objects.filter(
        catchment_point_id=cp_id, is_error=False
    ).exclude(pulses=0).exclude(total__isnull=True).exclude(pulses__lt=0).order_by('date_time_medition')

    fixable = []
    for r in regs:
        expected = int(float(r.pulses))
        actual = int(float(r.total))
        if expected != actual:
            fixable.append((r.id, r.date_time_medition, float(r.pulses), float(r.total), expected))

    if not fixable:
        return 0, 0

    log(f"Punto {cp_id} ({title}): {len(fixable)} registros a corregir")

    if not apply:
        # Dry-run: show sample
        for i, (rid, dt, pulses, old_total, new_total) in enumerate(fixable[:5]):
            log(f"  {dt} | pulses={pulses:.0f} | total={old_total:.0f} -> {new_total:.0f}")
        if len(fixable) > 5:
            log(f"  ... y {len(fixable) - 5} más")
        return 0, len(fixable)

    # Apply fix in batches
    total_fixed = 0
    batch_size = 500
    batches = [fixable[i:i + batch_size] for i in range(0, len(fixable), batch_size)]

    for batch_idx, batch in enumerate(batches):
        with transaction.atomic():
            for rid, dt, pulses, old_total, new_total in batch:
                InteractionDetail.objects.filter(id=rid).update(
                    total=str(int(new_total))
                )
            total_fixed += len(batch)
        if (batch_idx + 1) % 10 == 0:
            log(f"  Progreso: {total_fixed}/{len(fixable)}")

    log(f"  ✓ {total_fixed} registros corregidos en Punto {cp_id}")

    return total_fixed, len(fixable)


def main():
    parser = argparse.ArgumentParser(description="Bulk fix total != pulses")
    parser.add_argument("--apply", action="store_true", help="Aplicar fixes")
    parser.add_argument("--point", type=int, help="Solo un punto específico")
    parser.add_argument("--batch", action="store_true", help="Procesar en lote (sin confirmación)")
    args = parser.parse_args()

    profiles = ProfileDataConfigCatchment.objects.filter(
        is_telemetry=True, addition=0
    ).select_related('point_catchment')

    total_records = 0
    total_points = 0
    fixed_records = 0

    log("=" * 60)
    log(f"MODO: {'APLICAR' if args.apply else 'DRY-RUN'}")
    log("=" * 60)

    for p in profiles:
        cp = p.point_catchment
        if args.point and cp.id != args.point:
            continue

        # Quick check: any mismatches?
        has_issues = InteractionDetail.objects.filter(
            catchment_point=cp, is_error=False
        ).exclude(pulses=0).exclude(total__isnull=True).exclude(pulses__lt=0).extra(
            where=["CAST(total AS NUMERIC) != CAST(pulses AS NUMERIC)"]
        ).exists()

        if not has_issues:
            continue

        total_points += 1
        fixed, total = fix_point(cp.id, cp.title, apply=args.apply)
        total_records += total
        fixed_records += fixed

    log("=" * 60)
    if args.apply:
        log(f"✓ {fixed_records} registros corregidos en {total_points} puntos")
    else:
        log(f"Registros a corregir: {total_records} en {total_points} puntos")
        log("Usa --apply para aplicar los fixes.")
    log("=" * 60)


if __name__ == "__main__":
    main()
