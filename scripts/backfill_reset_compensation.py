#!/usr/bin/env python3
"""
BACKFILL COMPENSACIÓN DE RESET — Punto 60 (CocaCola P4)
========================================================

Corrige un reset no compensado del contador ocurrido el 2026-01-22 20:00 UTC,
donde los pulsos pasaron de 956.186 a 0 y el total acumulado quedó congelado.

ESTRATEGIA:
1. Detecta el último registro válido antes del reset (pulsos > 0) cuyo
   siguiente registro tenga pulsos = 0 dentro del año en curso.
2. Calcula la compensación: amount_to_add = last_pulses * factor / 1000.
3. Suma esa compensación al `addition` del profile del punto.
4. Recalcula `total` para todos los registros desde el reset en adelante como:
   total = (pulses * factor / 1000) + new_addition.
5. Recalcula `total_diff` y `total_today_diff` en cascada para todo el año 2026.

USO (dry-run por defecto):
    docker exec -u root -w /app django_api_secure python scripts/backfill_reset_compensation.py --point-id 60 --year 2026

USO (aplicar):
    docker exec -u root -w /app django_api_secure python scripts/backfill_reset_compensation.py --point-id 60 --year 2026 --force
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

import pytz
from django.db import transaction
from django.utils import timezone
from api.core.models import (
    CatchmentPoint,
    InteractionDetail,
    ProfileDataConfigCatchment,
    Variable,
)

CHILE_TZ = pytz.timezone("America/Santiago")


def log(msg):
    print(msg, flush=True)


def round_total(val):
    return int(Decimal(str(val)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def get_pulses_factor(point):
    v = Variable.objects.filter(
        type_variable="TOTALIZADO",
        scheme_catchment__points_catchment=point,
    ).first()
    return v.pulses_factor if v and v.pulses_factor else 1000


def detect_reset(point_id, year_start, year_end):
    """
    Encuentra el registro inmediatamente anterior al reset (pulses=0).
    Retorna (reset_record, prior_record) o (None, None) si no hay reset.
    """
    qs = (
        InteractionDetail.objects.filter(
            catchment_point_id=point_id,
            date_time_medition__gte=year_start,
            date_time_medition__lte=year_end,
        )
        .exclude(total__isnull=True)
        .exclude(total="")
        .order_by("date_time_medition")
    )

    prior = None
    for r in qs:
        if r.pulses == 0 and prior is not None and prior.pulses > 0:
            return r, prior
        prior = r
    return None, None


def backfill_reset_compensation(point_id, year, dry_run=True):
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

    reset_record, prior_record = detect_reset(point.id, year_start, year_end)
    if not reset_record:
        log(f"⚠️ Punto {point_id}: no se detectó reset con pulsos=0 en {year}")
        return None

    last_pulses = float(prior_record.pulses)
    amount_to_add = (last_pulses * float(pulses_factor)) / 1000.0
    current_addition = float(profile.addition or 0)
    new_addition = current_addition + amount_to_add

    log("=" * 70)
    log(f"BACKFILL RESET — Punto {point.id} ({point.title})")
    log("=" * 70)
    log(f"Reset detectado: {reset_record.date_time_medition} (pulsos={reset_record.pulses})")
    log(f"Último registro previo: {prior_record.date_time_medition} (pulsos={prior_record.pulses}, total={prior_record.total})")
    log(f"Factor de pulsos: {pulses_factor}")
    log(f"Compensación a agregar: {amount_to_add:.3f} m³")
    log(f"Addition actual del profile: {current_addition:.3f} m³")
    log(f"Addition nuevo del profile: {new_addition:.3f} m³")
    log(f"Modo: {'DRY-RUN (no aplica)' if dry_run else 'APLICAR CAMBIOS REALES'}")
    log("")

    # Registros afectados: desde el reset en adelante (incluyendo el propio reset)
    affected = (
        InteractionDetail.objects.filter(
            catchment_point_id=point.id,
            date_time_medition__gte=reset_record.date_time_medition,
            date_time_medition__lte=year_end,
        )
        .exclude(total__isnull=True)
        .exclude(total="")
        .order_by("date_time_medition")
    )

    total_updates = 0
    sample = []

    for r in affected:
        pulses = float(r.pulses or 0)
        new_total = (pulses * float(pulses_factor)) / 1000.0 + new_addition
        new_total_int = round_total(new_total)
        try:
            old_total = float(r.total) if r.total not in (None, "", "None") else 0.0
        except (ValueError, TypeError):
            old_total = 0.0

        if len(sample) < 5 or r.id in (reset_record.id, affected.last().id):
            sample.append({
                "dt": r.date_time_medition,
                "pulses": r.pulses,
                "old_total": old_total,
                "new_total": new_total_int,
            })

        if not dry_run and abs(int(round(old_total)) - new_total_int) > 0:
            r.total = str(new_total_int)
            r.save(update_fields=["total"])
            total_updates += 1
        elif dry_run:
            total_updates += 1  # contar como "afectado" en dry-run

    log("Muestra de totales recalculados:")
    for s in sample:
        log(f"  {s['dt']}: pulses={s['pulses']}  {s['old_total']:.0f} → {s['new_total']} m³")

    if not dry_run:
        # Actualizar addition del profile
        profile.addition = Decimal(str(new_addition))
        profile.save(update_fields=["addition"])

        # Recalcular diffs en cascada para todo el año
        diff_updates, today_diff_updates = recalc_diffs_for_year(point.id, year_start, year_end)
        log(f"\nRegistros con total actualizado: {total_updates}")
        log(f"total_diff actualizados: {diff_updates}")
        log(f"total_today_diff actualizados: {today_diff_updates}")

        # Recalcular consumo anual
        first_total, last_total, annual = calculate_annual(point.id, year_start, year_end)
        log(f"\nConsumo anual {year}: {annual:.2f} m³")
        log(f"  Primer total: {first_total:.2f} m³")
        log(f"  Último total: {last_total:.2f} m³")
    else:
        # Simular consumo anual esperado
        first_total, last_total, annual = calculate_annual(
            point.id, year_start, year_end, simulated_addition=new_addition,
            reset_dt=reset_record.date_time_medition,
        )
        log(f"\n[DRY-RUN] Consumo anual estimado {year}: {annual:.2f} m³")
        log(f"  Primer total: {first_total:.2f} m³")
        log(f"  Último total (simulado): {last_total:.2f} m³")

    return {
        "point_id": point.id,
        "reset_dt": reset_record.date_time_medition,
        "amount_to_add": amount_to_add,
        "new_addition": new_addition,
        "affected_count": affected.count(),
        "total_updates": total_updates,
    }


def recalc_diffs_for_year(point_id, year_start, year_end):
    """Recalcula total_diff y total_today_diff para todo el año."""
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


def calculate_annual(point_id, year_start, year_end, simulated_addition=None, reset_dt=None):
    """
    Calcula consumo anual. Si se pasa simulated_addition, simula el resultado
    aplicando el offset a registros desde reset_dt.
    """
    qs = (
        InteractionDetail.objects.filter(
            catchment_point_id=point_id,
            date_time_medition__gte=year_start,
            date_time_medition__lte=year_end,
            is_error=False,
        )
        .exclude(total__isnull=True)
        .exclude(total="")
        .order_by("date_time_medition")
    )

    if simulated_addition is None:
        first = qs.first()
        last = qs.last()
        f = float(first.total) if first else 0.0
        l = float(last.total) if last else 0.0
        return f, l, max(0.0, l - f)

    # Simulación: recalcular totales con nuevo addition
    first_total = None
    last_total = None
    pulses_factor = get_pulses_factor(CatchmentPoint.objects.get(id=point_id))
    for r in qs:
        pulses = float(r.pulses or 0)
        if reset_dt and r.date_time_medition >= reset_dt:
            total = (pulses * float(pulses_factor)) / 1000.0 + simulated_addition
        else:
            total = float(r.total) if r.total not in (None, "", "None") else 0.0
        if first_total is None:
            first_total = total
        last_total = total
    return first_total or 0.0, last_total or 0.0, max(0.0, (last_total or 0.0) - (first_total or 0.0))


def main():
    parser = argparse.ArgumentParser(description="Compensar reset no detectado en totalizador")
    parser.add_argument("--point-id", type=int, required=True)
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument("--force", action="store_true", help="Aplicar cambios reales")
    args = parser.parse_args()

    result = backfill_reset_compensation(args.point_id, args.year, dry_run=not args.force)
    if not result:
        sys.exit(1)

    log("")
    if not args.force:
        log("⚠️  Esto fue DRY-RUN. Para aplicar cambios reales:")
        log(f"   docker exec -u root -w /app django_api_secure python scripts/backfill_reset_compensation.py --point-id {args.point_id} --year {args.year} --force")
    else:
        log("✅ Backfill aplicado.")


if __name__ == "__main__":
    main()
