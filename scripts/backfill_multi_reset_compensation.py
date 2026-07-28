#!/usr/bin/env python3
"""
BACKFILL MULTI-RESET COMPENSATION
=================================

Compensa múltiples resets de contador en un punto durante un año.
A diferencia de backfill_reset_compensation.py (que compensa un solo reset),
este script detecta TODOS los resets no compensados recorriendo la serie
de totales y ajustando el addition del profile de forma acumulativa.

USO (dry-run por defecto):
    docker exec -u root -w /app django_api_secure python scripts/backfill_multi_reset_compensation.py --point-id 110 --year 2026

USO (aplicar):
    docker exec -u root -w /app django_api_secure python scripts/backfill_multi_reset_compensation.py --point-id 110 --year 2026 --force
"""

import os
import sys
import argparse
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

sys.path.insert(0, "/app")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.settings")
import django

django.setup()

from django.db import transaction
from django.utils import timezone
from api.core.models import CatchmentPoint, InteractionDetail, ProfileDataConfigCatchment, Variable


def log(msg):
    print(msg, flush=True)


def round_total(val):
    try:
        return int(Decimal(str(val)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except Exception:
        raise ValueError(f"Cannot round value: {val!r} (type={type(val).__name__})")


def get_pulses_factor(point):
    v = Variable.objects.filter(
        type_variable="TOTALIZADO",
        scheme_catchment__points_catchment=point,
    ).first()
    return v.pulses_factor if v and v.pulses_factor else 1000


def recalc_diffs_for_year(point_id, year_start, year_end):
    records = list(
        InteractionDetail.objects.filter(
            catchment_point_id=point_id,
            date_time_medition__gte=year_start,
            date_time_medition__lte=year_end,
        )
        .exclude(total__isnull=True)
        .exclude(total="")
        .order_by("date_time_medition")
        .values("id", "date_time_medition", "total", "total_diff", "total_today_diff")
    )
    if not records:
        return 0, 0

    prior = (
        InteractionDetail.objects.filter(
            catchment_point_id=point_id,
            date_time_medition__lt=year_start,
        )
        .exclude(total__isnull=True)
        .exclude(total="")
        .exclude(total="None")
        .order_by("-date_time_medition")
        .values("total")
        .first()
    )
    prev_total = float(prior["total"]) if prior else 0.0
    diff_updates = 0
    today_diff_updates = 0
    first_total_of_day = {}
    current_day = None

    for r in records:
        rid = r["id"]
        try:
            curr_total = float(r["total"]) if r["total"] not in (None, "", "None") else 0.0
        except (ValueError, TypeError):
            curr_total = 0.0

        day = r["date_time_medition"].date()
        if current_day != day:
            current_day = day
            first_total_of_day[day] = curr_total

        new_diff = max(0, round_total(curr_total) - round_total(prev_total))
        old_diff = r["total_diff"] or 0
        if new_diff != old_diff:
            InteractionDetail.objects.filter(id=rid).update(total_diff=new_diff)
            diff_updates += 1

        first_total = first_total_of_day.get(day, 0.0)
        new_today_diff = max(0, round_total(curr_total) - round_total(first_total))
        old_today_diff = r["total_today_diff"] or 0
        if new_today_diff != old_today_diff:
            InteractionDetail.objects.filter(id=rid).update(total_today_diff=new_today_diff)
            today_diff_updates += 1

        prev_total = curr_total

    return diff_updates, today_diff_updates


def backfill_multi_reset(point_id, year, dry_run=True, min_offset_m3=100):
    try:
        point = CatchmentPoint.objects.get(id=point_id)
    except CatchmentPoint.DoesNotExist:
        log(f"❌ Punto {point_id} no existe")
        return None

    profile = point.data_config_profiles.filter(is_telemetry=True).first()
    if not profile:
        log(f"❌ Punto {point_id}: sin perfil de telemetría")
        return None

    year_start = timezone.make_aware(datetime(year, 1, 1, 0, 0, 0))
    year_end = timezone.make_aware(datetime(year, 12, 31, 23, 59, 59))

    pulses_factor = get_pulses_factor(point)

    records = list(
        InteractionDetail.objects.filter(
            catchment_point=point,
            date_time_medition__gte=year_start,
            date_time_medition__lte=year_end,
        )
        .exclude(total__isnull=True)
        .exclude(total="")
        .exclude(is_error=True)
        .order_by("date_time_medition")
    )

    if not records:
        log(f"⚠️ Punto {point_id}: sin registros en {year}")
        return None

    running_addition = float(profile.addition or 0)
    initial_addition = running_addition
    last_expected_total = None
    last_actual_total = None
    reset_active = False
    resets = []
    total_updates = 0

    log("=" * 70)
    log(f"BACKFILL MULTI-RESET — Punto {point.id} ({point.title})")
    log(f"Año: {year} | Factor pulsos: {pulses_factor}")
    log(f"Addition inicial: {initial_addition:.3f} m³")
    log(f"Modo: {'DRY-RUN' if dry_run else 'APLICAR CAMBIOS REALES'}")
    log("=" * 70)

    for i, r in enumerate(records):
        try:
            pulses = float(r.pulses or 0)
            actual_total = float(r.total) if r.total not in (None, "", "None") else 0.0
        except (ValueError, TypeError):
            continue

        raw_total = (pulses * float(pulses_factor)) / 1000.0
        expected_total = raw_total + running_addition

        # Detectar reset no compensado:
        # - El total actual cayó fuertemente respecto al actual anterior
        # - Y el total actual está cerca del raw_total (sin compensación)
        # - Y no estamos ya dentro de un reset activo
        if not reset_active and last_actual_total is not None and last_actual_total > 0:
            drop = last_actual_total - actual_total
            near_raw = abs(actual_total - raw_total) < max(1.0, last_actual_total * 0.05)
            significant_drop = drop > min_offset_m3 and actual_total < last_actual_total * 0.5

            if significant_drop and near_raw:
                # Compensar para mantener continuidad con last_expected_total
                compensation = last_expected_total - raw_total
                running_addition += compensation
                expected_total = raw_total + running_addition
                resets.append({
                    "dt": r.date_time_medition,
                    "last_expected": last_expected_total,
                    "last_actual": last_actual_total,
                    "actual_total": actual_total,
                    "raw_total": raw_total,
                    "compensation": compensation,
                    "new_addition": running_addition,
                })
                reset_active = True

        # Desactivar reset_active cuando la serie vuelve a crecer
        if reset_active:
            if last_actual_total is not None and actual_total > last_actual_total:
                reset_active = False

        new_total_int = round_total(expected_total)
        old_total_int = round_total(actual_total)

        if dry_run:
            if abs(new_total_int - old_total_int) > 0:
                total_updates += 1
        else:
            if abs(new_total_int - old_total_int) > 0:
                r.total = str(new_total_int)
                r.save(update_fields=["total"])
                total_updates += 1

        last_expected_total = expected_total
        last_actual_total = actual_total

    if not resets:
        log(f"⚠️ No se detectaron resets no compensados")
        return None

    log(f"\nResets detectados: {len(resets)}")
    for idx, rst in enumerate(resets, 1):
        log(f"  {idx}. {rst['dt']}: compensación {rst['compensation']:.3f} m³ "
            f"(last={rst['last_expected']:.0f} → actual={rst['actual_total']:.0f})")

    log(f"\nAddition final: {running_addition:.3f} m³ "
        f"(se agregan {running_addition - initial_addition:.3f} m³)")

    if not dry_run:
        profile.addition = Decimal(str(running_addition))
        profile.save(update_fields=["addition"])
        diff_upd, today_upd = recalc_diffs_for_year(point.id, year_start, year_end)
        log(f"\nRegistros con total actualizado: {total_updates}")
        log(f"total_diff actualizados: {diff_upd}")
        log(f"total_today_diff actualizados: {today_upd}")
    else:
        log(f"\n[DRY-RUN] Registros que se actualizarían: {total_updates}")

    # Calcular consumo anual
    first_total = float(records[0].total) if records[0].total not in (None, "", "None") else 0.0
    last_total = last_expected_total if last_expected_total is not None else 0.0
    if dry_run:
        # Simular: el último registro tendría el nuevo total
        last_record = records[-1]
        try:
            last_pulses = float(last_record.pulses or 0)
            last_total = (last_pulses * float(pulses_factor)) / 1000.0 + running_addition
        except (ValueError, TypeError):
            last_total = 0.0
    annual = max(0.0, last_total - first_total)
    log(f"\nConsumo anual {year}: {annual:.2f} m³")
    log(f"  Primer total: {first_total:.2f} m³")
    log(f"  Último total: {last_total:.2f} m³")

    return {
        "point_id": point.id,
        "resets": resets,
        "initial_addition": initial_addition,
        "final_addition": running_addition,
        "total_updates": total_updates,
        "annual_m3": annual,
    }


def main():
    parser = argparse.ArgumentParser(description="Compensar múltiples resets de contador")
    parser.add_argument("--point-id", type=int, required=True)
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument("--force", action="store_true", help="Aplicar cambios reales")
    parser.add_argument("--min-offset", type=float, default=100.0, help="Umbral mínimo de compensación (m³)")
    args = parser.parse_args()

    result = backfill_multi_reset(args.point_id, args.year, dry_run=not args.force, min_offset_m3=args.min_offset)
    if not result:
        sys.exit(1)

    log("")
    if not args.force:
        log("⚠️  Esto fue DRY-RUN. Para aplicar cambios reales:")
        log(f"   docker exec -u root -w /app django_api_secure python scripts/backfill_multi_reset_compensation.py --point-id {args.point_id} --year {args.year} --force")
    else:
        log("✅ Backfill multi-reset aplicado.")


if __name__ == "__main__":
    main()
