#!/usr/bin/env python3
"""
RECALCULO MASIVO DE COHERENCIA DE TELEMETRÍA
=============================================

Corrige indulgencias históricas en InteractionDetail de forma segura:
- total_diff inconsistente con (total - total_anterior)
- total_today_diff inconsistente con (total - primer_total_del_dia)
- flow inconsistente con total_diff y Δt
- total=0 con pulses>0 (recupera desde total anterior válido)

MODO SEGURO POR DEFECTO (dry-run):
    python scripts/recalcular_coherencia_masivo.py --days 7

PARA APLICAR CAMBIOS REALES:
    python scripts/recalcular_coherencia_masivo.py --days 7 --force

FILTRAR POR PROYECTO O PUNTO:
    python scripts/recalcular_coherencia_masivo.py --days 7 --project-id 2 --force
    python scripts/recalcular_coherencia_masivo.py --days 7 --point-id 113 --force
"""

import os
import sys
import csv
import argparse
from datetime import datetime, timedelta
from collections import defaultdict

sys.path.append('/app')
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.settings")

import django
django.setup()

import pytz
from django.db import transaction
from api.core.models import InteractionDetail, CatchmentPoint


def safe_float(val, default=0.0):
    try:
        return float(val) if val is not None else default
    except (ValueError, TypeError):
        return default


def recalc_point(point, start_dt, end_dt, dry_run=True, csv_writer=None):
    """Recalcula coherencia para un punto. Retorna conteo de correcciones."""
    records = InteractionDetail.objects.filter(
        catchment_point=point,
        date_time_medition__gte=start_dt,
        date_time_medition__lte=end_dt,
    ).exclude(is_error=True).order_by("date_time_medition")

    total_records = records.count()
    if total_records == 0:
        return 0

    corrections = 0
    prev = None
    day_first = None
    current_day = None
    updates = []

    for r in records:
        dt = r.date_time_medition
        total = safe_float(r.total)
        pulses = safe_float(r.pulses)

        # Detectar día nuevo
        if current_day != dt.date():
            current_day = dt.date()
            day_first = r

        changes = {}

        # 1. CORREGIR total=0 con pulses>0 (si hay total anterior válido)
        if total == 0 and pulses > 0 and prev is not None:
            prev_total = safe_float(prev.total)
            if prev_total > 0:
                # Calcular lo que debería ser el total
                expected_total = int(round((pulses * 1000) / 1000.0))  # placeholder
                # En realidad necesitamos factor; si no hay factor, usar 1000
                # Mejor: mantener el total anterior si no hay evidencia de reset
                expected_total = int(prev_total)
                changes["total"] = str(expected_total)
                total = expected_total
                print(f"  [CORRECCIÓN] Punto {point.id} @ {dt}: total=0 con pulses={pulses}. "
                      f"Recuperando total anterior {prev_total:.0f}")

        # 2. RECALCULAR total_diff
        if prev is not None:
            prev_total = safe_float(prev.total)
            expected_diff = total - prev_total
            if expected_diff < 0:
                expected_diff = 0
            current_diff = safe_float(r.total_diff)
            if abs(current_diff - expected_diff) > 1:
                changes["total_diff"] = int(round(expected_diff))
                print(f"  [CORRECCIÓN] Punto {point.id} @ {dt}: total_diff "
                      f"{current_diff:.0f} -> {expected_diff:.0f}")

            # 3. RECALCULAR flow (solo si hay diff y tiempo)
            time_delta_hours = max((dt - prev.date_time_medition).total_seconds() / 3600.0, 0.001)
            if changes.get("total_diff") is not None:
                diff_for_flow = changes["total_diff"]
            else:
                diff_for_flow = safe_float(r.total_diff)

            if diff_for_flow > 0 and time_delta_hours > 0:
                expected_flow = round((diff_for_flow / (time_delta_hours * 3600)) * 1000.0, 2)
                # Cap a máximo soportado por BD (numeric(5,2) = max 999.99)
                expected_flow = min(expected_flow, 999.99)
                current_flow = safe_float(r.flow)
                # Solo corregir si hay una discrepancia clara (>50%)
                if current_flow > 0 and abs(current_flow - expected_flow) / max(current_flow, 0.01) > 0.5:
                    changes["flow"] = expected_flow
                    print(f"  [CORRECCIÓN] Punto {point.id} @ {dt}: flow "
                          f"{current_flow:.2f} -> {expected_flow:.2f} L/s")
                elif current_flow == 0 and expected_flow > 0.1:
                    # flow estaba en 0 pero debería tener valor
                    changes["flow"] = expected_flow
                    print(f"  [CORRECCIÓN] Punto {point.id} @ {dt}: flow "
                          f"0.00 -> {expected_flow:.2f} L/s")

        # 4. RECALCULAR total_today_diff
        if day_first is not None and r.id != day_first.id:
            first_total = safe_float(day_first.total)
            expected_today = total - first_total
            if expected_today < 0:
                expected_today = 0
            current_today = safe_float(r.total_today_diff)
            if abs(current_today - expected_today) > 1:
                changes["total_today_diff"] = int(round(expected_today))
                print(f"  [CORRECCIÓN] Punto {point.id} @ {dt}: total_today_diff "
                      f"{current_today:.0f} -> {expected_today:.0f}")

        if changes:
            corrections += 1
            updates.append((r, changes))
            if csv_writer:
                csv_writer.writerow([
                    point.id, point.title, dt.isoformat(),
                    "; ".join([f"{k}={v}" for k, v in changes.items()])
                ])

        prev = r

    # Aplicar cambios si no es dry-run
    if not dry_run and updates:
        print(f"  Aplicando {len(updates)} correcciones en punto {point.id}...")
        with transaction.atomic():
            for record, changes in updates:
                for field, value in changes.items():
                    setattr(record, field, value)
                record.save(update_fields=list(changes.keys()))
        print(f"  ✅ Guardado.")
    elif dry_run and updates:
        print(f"  [DRY-RUN] Se habrían aplicado {len(updates)} correcciones. "
              f"Usa --force para aplicar.")

    return corrections


def main():
    parser = argparse.ArgumentParser(description="Recálculo masivo de coherencia de telemetría")
    parser.add_argument("--days", type=int, default=7, help="Días hacia atrás a procesar")
    parser.add_argument("--project-id", type=int, help="Filtrar por proyecto")
    parser.add_argument("--point-id", type=int, help="Filtrar por punto específico")
    parser.add_argument("--force", action="store_true", help="Aplicar cambios reales (sin esto es dry-run)")
    parser.add_argument("--csv", default="/tmp/recalc_corrections.csv", help="Ruta del reporte CSV")
    args = parser.parse_args()

    chile = pytz.timezone("America/Santiago")
    end_dt = datetime.now(chile)
    start_dt = end_dt - timedelta(days=args.days)

    qs = CatchmentPoint.objects.filter(data_config_profiles__is_telemetry=True).distinct()
    if args.project_id:
        qs = qs.filter(project_id=args.project_id)
    if args.point_id:
        qs = qs.filter(id=args.point_id)

    mode = "APLICANDO CAMBIOS REALES" if args.force else "DRY-RUN (solo reporta)"
    print(f"=== RECÁLCULO DE COHERENCIA | {mode} ===")
    print(f"Rango: {start_dt.strftime('%Y-%m-%d %H:%M')} -> {end_dt.strftime('%Y-%m-%d %H:%M')}")
    print(f"Puntos: {qs.count()}")
    print(f"Reporte CSV: {args.csv}")
    print()

    total_corrections = 0
    csv_path = args.csv

    with open(csv_path, "w", newline="") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["point_id", "point_title", "date_time_medition", "changes"])

        for point in qs.select_related("project", "project__client"):
            project_name = point.project.name if point.project else "Sin proyecto"
            print(f"📍 Punto {point.id}: {point.title} | {project_name}")

            try:
                corr = recalc_point(point, start_dt, end_dt, dry_run=not args.force, csv_writer=writer)
                total_corrections += corr
            except Exception as e:
                print(f"  ❌ ERROR procesando punto {point.id}: {e}")
                import traceback
                traceback.print_exc()

    print()
    print(f"=== RESUMEN ===")
    print(f"Total correcciones detectadas: {total_corrections}")
    if not args.force:
        print(f"Modo dry-run. Ningún cambio fue aplicado.")
        print(f"Para aplicar cambios reales: python scripts/recalcular_coherencia_masivo.py --days {args.days} --force")
    else:
        print(f"✅ Cambios aplicados.")
    print(f"Reporte CSV guardado en: {csv_path}")


if __name__ == "__main__":
    main()
