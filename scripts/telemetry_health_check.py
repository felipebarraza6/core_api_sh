#!/usr/bin/env python3
"""
Auditoría de Salud de Telemetría — Validación Retroactiva
==========================================================

Este script realiza una auditoría completa de todos los puntos con telemetría activa
y corrige problemas históricos causados por falsos resets (PARTIAL con caída < 1%).

Problema conocido: fluctuaciones de pulsos < 1% se interpretaban como resets reales,
acumulando addition falsa. Este script:
1. Identifica todos los puntos con resets PARTIAL falsos
2. Calcula el addition acumulado falso
3. Restaura addition = 0 para esos puntos
4. Corrige los registros InteractionDetail afectados
5. Recalcula diffs (total_diff, total_today_diff)
6. Elimina CounterResetLog falsos
7. Genera reporte completo

Uso (dry-run por defecto):
    docker exec -u root -w /app django_api_secure python scripts/telemetry_health_check.py

Aplicar:
    docker exec -u root -w /app django_api_secure python scripts/telemetry_health_check.py --apply

Reporte solamente:
    docker exec -u root -w /app django_api_secure python scripts/telemetry_health_check.py --report
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime
from decimal import Decimal

sys.path.insert(0, "/app")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.settings")

import django
django.setup()

import pytz
from django.db import transaction
from django.db.models import Q, Count, Sum, Max
from api.core.models import (
    CatchmentPoint,
    CounterResetLog,
    InteractionDetail,
    ProfileDataConfigCatchment,
    SchemesCatchment,
    Variable,
)

# Umbral de caída para considerar un reset como falso positivo
NOISE_THRESHOLD = 0.01  # 1%


def log(msg, level="INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [{level}] {msg}", flush=True)


def safe_float(s, default=0.0):
    try:
        return float(s) if s not in (None, "", "None") else default
    except (ValueError, TypeError):
        return default


def find_false_resets():
    """Encontrar todos los resets PARTIAL que son falsos positivos (caída < 1%)."""
    false_resets = defaultdict(list)

    partials = CounterResetLog.objects.filter(
        reset_type="PARTIAL"
    ).select_related("point_catchment").order_by("point_catchment_id", "date_time_medition")

    for r in partials:
        if r.last_pulses and r.last_pulses > 0:
            drop_ratio = 1.0 - (float(r.current_pulses) / float(r.last_pulses))
        else:
            drop_ratio = 0

        if drop_ratio < NOISE_THRESHOLD:
            false_resets[r.point_catchment_id].append({
                "id": r.id,
                "date": r.date_time_medition,
                "last_pulses": float(r.last_pulses),
                "current_pulses": float(r.current_pulses),
                "drop_pct": round(drop_ratio * 100, 4),
                "amount_to_add": float(r.amount_to_add or 0),
                "addition_before": float(r.addition_before or 0),
                "addition_after": float(r.addition_after or 0),
            })

    return false_resets


def find_corrupted_interactions(point_id, false_resets):
    """Encontrar registros InteractionDetail con total corrupto por addition falsa."""
    if not false_resets:
        return []

    # Rango de fechas afectadas: desde el primer reset falso hasta el último
    dates = [r["date"] for r in false_resets]
    start_dt = min(dates)
    end_dt = max(dates)

    # Obtener todos los registros en ese rango
    regs = InteractionDetail.objects.filter(
        catchment_point_id=point_id,
        date_time_medition__gte=start_dt,
        date_time_medition__lte=end_dt,
        is_error=False,
    ).order_by("date_time_medition")

    # Obtener el addition acumulado falso para cada registro
    corrupted = []
    for reg in regs:
        pulses = safe_float(reg.pulses)
        actual_total = safe_float(reg.total)
        # Calcular total correcto sin addition falsa
        correct_total = int(round(pulses))  # pulses * factor / 1000, asumiendo factor=1000
        if actual_total != correct_total and reg.pulses is not None:
            corrupted.append({
                "id": reg.id,
                "date": reg.date_time_medition,
                "pulses": pulses,
                "total_current": actual_total,
                "total_correct": correct_total,
                "diff": actual_total - correct_total,
            })

    return corrupted


def audit_all_points():
    """Auditoría completa de todos los puntos con telemetría."""
    log("=" * 70)
    log("AUDITORÍA DE SALUD DE TELEMETRÍA")
    log("=" * 70)

    # Puntos con telemetría activa
    active_points = ProfileDataConfigCatchment.objects.filter(
        is_telemetry=True
    ).select_related("point_catchment")

    total_points = active_points.count()
    log(f"Puntos con telemetría activa: {total_points}")

    # Encontrar resets falsos
    false_resets = find_false_resets()
    log(f"Puntos con resets PARTIAL falsos (caída < {NOISE_THRESHOLD*100}%): {len(false_resets)}")

    # Estadísticas generales
    total_resets = CounterResetLog.objects.count()
    total_partials = CounterResetLog.objects.filter(reset_type="PARTIAL").count()
    total_noise = CounterResetLog.objects.filter(reset_type="NOISE_DROP").count()
    total_zero_kept = CounterResetLog.objects.filter(reset_type="ZERO_KEPT").count()
    total_negative = CounterResetLog.objects.filter(reset_type="NEGATIVE_PULSES").count()

    log(f"\n--- Estadísticas de Resets ---")
    log(f"  TOTAL resets: {total_resets}")
    log(f"  PARTIAL (reset real): {total_partials}")
    log(f"  NOISE_DROP (ruido, < 1%): {total_noise}")
    log(f"  ZERO_KEPT (pulsos=0): {total_zero_kept}")
    log(f"  NEGATIVE_PULSES: {total_negative}")

    # Puntos con addition > 0
    points_with_addition = active_points.filter(addition__gt=0)
    log(f"\n--- Puntos con addition > 0 ---")
    log(f"  Cantidad: {points_with_addition.count()}")
    for p in points_with_addition:
        cp = p.point_catchment
        resets_count = CounterResetLog.objects.filter(point_catchment=cp).count()
        log(f"  Punto {cp.id} ({cp.title}): addition={p.addition}, resets={resets_count}")

    # Detalle de puntos con falsos resets
    if false_resets:
        log(f"\n--- Puntos con Resets Falsos (requieren fix) ---")
        for pid, resets in sorted(false_resets.items()):
            try:
                cp = CatchmentPoint.objects.get(id=pid)
                total_false_addition = sum(r["amount_to_add"] for r in resets)
                corrupted = find_corrupted_interactions(pid, resets)
                log(f"\n  Punto {pid} ({cp.title}):")
                log(f"    Resets falsos: {len(resets)}")
                log(f"    Addition acumulado falso: {total_false_addition:.0f} m³")
                log(f"    Registros InteractionDetail corruptos: {len(corrupted)}")
                for r in resets:
                    log(f"      {r['date']} | {r['last_pulses']:.0f} -> {r['current_pulses']:.0f} ({r['drop_pct']:.2f}%) | +{r['amount_to_add']:.0f} m³")
            except CatchmentPoint.DoesNotExist:
                log(f"  Punto {pid}: NO EXISTE en CatchmentPoint")

    # Verificar monotonicidad en todos los puntos activos
    log(f"\n--- Verificación de Monotonicidad ---")
    non_monotonic = []
    for profile in active_points:
        cp = profile.point_catchment
        last_total = None
        last_date = None
        issues = 0
        # Muestrear últimos 100 registros para performance
        regs = InteractionDetail.objects.filter(
            catchment_point=cp,
            is_error=False,
        ).exclude(total__isnull=True).order_by("-date_time_medition")[:100]

        for reg in regs:
            if reg.total is not None:
                current_total = safe_float(reg.total)
                if last_total is not None and current_total > last_total:
                    issues += 1
                last_total = current_total
                last_date = reg.date_time_medition

        if issues > 0:
            non_monotonic.append({"point_id": cp.id, "title": cp.title, "issues": issues})

    if non_monotonic:
        log(f"  Puntos con total no-monotónico (últimos 100 registros):")
        for nm in non_monotonic:
            log(f"    Punto {nm['point_id']} ({nm['title']}): {nm['issues']} caídas")
    else:
        log(f"  Todos los puntos tienen total monotónico ✓")

    # Verificar registros con total=0 y pulses>0 (solo donde expected > 0)
    log(f"\n--- Registros con total=0 y pulses>0 (expected > 0) ---")
    zero_total_count = 0
    zero_total_points = 0
    for profile in active_points:
        cp = profile.point_catchment
        scheme = SchemesCatchment.objects.filter(points_catchment=cp).first()
        if not scheme:
            continue
        totalizador = Variable.objects.filter(
            scheme_catchment=scheme, type_variable='TOTALIZADO'
        ).first()
        if not totalizador:
            continue
        factor = totalizador.pulses_factor

        bad = InteractionDetail.objects.filter(
            catchment_point=cp,
            is_error=False,
            pulses__gt=0,
        ).filter(Q(total__isnull=True) | Q(total="0") | Q(total=0))

        count = 0
        for b in bad:
            expected = int((float(b.pulses) * factor) / 1000)
            if expected > 0:
                count += 1

        if count > 0:
            zero_total_count += count
            zero_total_points += 1
            log(f"  ⚠️ Punto {cp.id:>3} ({cp.title:<35}): {count:>6} registros (total=0 pero pulses×factor/1000 > 0)")
    log(f"  TOTAL: {zero_total_count} registros en {zero_total_points} puntos")

    return false_resets


def fix_false_resets(false_resets, apply=False):
    """Corregir los resets falsos en la base de datos."""
    if not false_resets:
        log("\nNo hay resets falsos para corregir.")
        return

    log("\n" + "=" * 70)
    log(f"MODO: {'APLICAR' if apply else 'DRY-RUN'}")
    log("=" * 70)

    for pid, resets in sorted(false_resets.items()):
        try:
            cp = CatchmentPoint.objects.get(id=pid)
        except CatchmentPoint.DoesNotExist:
            log(f"Punto {pid}: NO EXISTE, saltando")
            continue

        log(f"\n--- Punto {pid} ({cp.title}) ---")

        # 1. Obtener perfil
        profile = ProfileDataConfigCatchment.objects.filter(
            point_catchment=cp, is_telemetry=True
        ).first()
        if not profile:
            log(f"  No hay perfil de telemetría, saltando")
            continue

        current_addition = float(profile.addition or 0)
        log(f"  Addition actual: {current_addition:.0f} m³")

        # 2. Calcular addition acumulado falso
        false_addition_sum = sum(r["amount_to_add"] for r in resets)
        log(f"  Addition falso acumulado: {false_addition_sum:.0f} m³")

        # 3. Encontrar registros corruptos
        corrupted = find_corrupted_interactions(pid, resets)
        log(f"  Registros a corregir: {len(corrupted)}")

        if not apply:
            for c in corrupted[:5]:
                log(f"    {c['date']}: {c['total_current']:.0f} -> {c['total_correct']:.0f} (diff={c['diff']:.0f})")
            if len(corrupted) > 5:
                log(f"    ... y {len(corrupted) - 5} más")
            continue

        # 4. Aplicar fixes
        with transaction.atomic():
            # Resetear addition a 0
            profile.addition = 0
            profile.save(update_fields=["addition"])
            log(f"  ✓ Addition reseteado a 0")

            # Corregir registros InteractionDetail
            corrected = 0
            for c in corrupted:
                updated = InteractionDetail.objects.filter(id=c["id"]).update(
                    total=str(int(c["total_correct"]))
                )
                corrected += updated
            log(f"  ✓ {corrected} registros InteractionDetail corregidos")

            # Eliminar CounterResetLog falsos
            reset_ids = [r["id"] for r in resets]
            deleted, _ = CounterResetLog.objects.filter(id__in=reset_ids).delete()
            log(f"  ✓ {deleted} CounterResetLog falsos eliminados")

        # 5. Recalcular diffs (fuera de la transacción para no bloquear tanto)
        if corrupted:
            log(f"  Recalculando diffs...")
            first_date = min(c["date"] for c in corrupted)
            # Buscar registro anterior al rango afectado
            prev_reg = InteractionDetail.objects.filter(
                catchment_point=cp,
                date_time_medition__lt=first_date,
                is_error=False,
            ).exclude(total__isnull=True).order_by("-date_time_medition").first()

            prev_total = safe_float(prev_reg.total) if prev_reg else 0
            prev_day = prev_reg.date_time_medition.date() if prev_reg else None

            # Obtener todos los registros desde el anterior hasta el último del rango
            last_date = max(c["date"] for c in corrupted)
            all_regs = InteractionDetail.objects.filter(
                catchment_point=cp,
                date_time_medition__gte=first_date if not prev_reg else prev_reg.date_time_medition,
                date_time_medition__lte=last_date,
                is_error=False,
            ).exclude(total__isnull=True).order_by("date_time_medition")

            first_total_of_day = {}
            diff_updates = 0
            for reg in all_regs:
                curr_total = safe_float(reg.total)
                day = reg.date_time_medition.date()

                if day not in first_total_of_day:
                    first_total_of_day[day] = curr_total

                new_diff = max(0, int(round(curr_total - prev_total)))
                new_today = max(0, int(round(curr_total - first_total_of_day[day])))

                changed = False
                if (reg.total_diff or 0) != new_diff:
                    reg.total_diff = new_diff
                    changed = True
                    diff_updates += 1
                if (reg.total_today_diff or 0) != new_today:
                    reg.total_today_diff = new_today
                    changed = True

                if changed:
                    reg.save(update_fields=["total_diff", "total_today_diff"])

                prev_total = curr_total

            log(f"  ✓ Diffs recalculados: {diff_updates} registros actualizados")

        log(f"  ✓ Punto {pid} corregido exitosamente")


def main():
    parser = argparse.ArgumentParser(description="Auditoría de salud de telemetría")
    parser.add_argument("--apply", action="store_true", help="Aplicar fixes (sin esto es dry-run)")
    parser.add_argument("--report", action="store_true", help="Solo generar reporte, sin fixes")
    args = parser.parse_args()

    if args.report:
        false_resets = audit_all_points()
        log("\n--- REPORTE COMPLETADO ---")
        return

    # Encontrar problemas
    false_resets = audit_all_points()

    # Aplicar fixes si se pide
    if args.apply:
        log("\n⚠️  MODO APLICAR: Se modificarán datos en producción")
        log("    Asegúrate de tener un backup antes de continuar.")
        fix_false_resets(false_resets, apply=True)
    else:
        log("\n--- DRY-RUN: No se modificaron datos ---")
        log("    Usa --apply para aplicar los fixes.")
        fix_false_resets(false_resets, apply=False)


if __name__ == "__main__":
    main()
