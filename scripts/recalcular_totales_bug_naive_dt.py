#!/usr/bin/env python
"""
Recalcula totales afectados por el bug de naive datetime (May 18 2026 ~18:45 UTC).
El bug causó que total_m3 retornara 0 para todos los puntos con last_interaction
 porque current_dt (naive) - last_interaction.date_time_medition (aware) lanzaba TypeError.

Este script:
1. Identifica registros afectados: total=0, pulses>0, desde cutoff
2. Por cada punto, recalcula en orden cronológico
3. Actualiza total, total_diff, total_today_diff
"""
import os
import sys
import django

sys.path.insert(0, '/app')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from datetime import datetime
from django.db import transaction
from api.core.models import InteractionDetail, CatchmentPoint, ProfileDataConfigCatchment, Variable
from api.cronjobs.telemetry.controllers.total import total_m3, total_hour, total_day

CUTOFF = datetime(2026, 5, 18, 18, 45, 0)


def build_point_catchment_dict(point_id):
    """Construye el dict point_catchment como lo espera total_m3."""
    try:
        point = CatchmentPoint.objects.get(id=point_id)
    except CatchmentPoint.DoesNotExist:
        return None
    profile = ProfileDataConfigCatchment.objects.filter(point_catchment_id=point_id).first()
    profile_data = {}
    if profile:
        profile_data = {
            "addition": float(profile.addition) if profile.addition is not None else 0,
            "max_diff_m3_per_hour": float(profile.max_diff_m3_per_hour) if profile.max_diff_m3_per_hour is not None else 500,
            "max_flow_ls": float(profile.max_flow_ls) if profile.max_flow_ls is not None else 100,
            "max_time_gap_hours": float(profile.max_time_gap_hours) if profile.max_time_gap_hours is not None else 2,
            "reconnection_threshold_hours": float(profile.reconnection_threshold_hours) if profile.reconnection_threshold_hours is not None else 2,
        }
    return {
        "id": point_id,
        "title": point.title,
        "frecuency": point.frecuency,
        "profile_data_config": profile_data,
    }


def get_pulses_factor(point_id):
    var = Variable.objects.filter(catchment_point_id=point_id, type_variable='TOTALIZADO').first()
    return var.pulses_factor if var and var.pulses_factor else 1000


def main():
    affected = (
        InteractionDetail.objects
        .filter(date_time_medition__gte=CUTOFF, total=0, pulses__gt=0)
        .order_by('catchment_point_id', 'date_time_medition')
    )
    total_count = affected.count()
    print(f"Registros afectados encontrados: {total_count}")
    if total_count == 0:
        print("Nada que recalcular.")
        return

    # Agrupar por punto
    by_point = {}
    for r in affected:
        by_point.setdefault(r.catchment_point_id, []).append(r)

    updated = 0
    skipped = 0
    errors = 0

    for point_id, regs in sorted(by_point.items()):
        point_catchment = build_point_catchment_dict(point_id)
        if not point_catchment:
            print(f"  Punto {point_id}: NO EXISTE. Skipping {len(regs)} registros.")
            skipped += len(regs)
            continue

        pulses_factor = get_pulses_factor(point_id)
        print(f"  Punto {point_id}: {len(regs)} registros, factor={pulses_factor}")

        for reg in regs:
            try:
                current_dt = reg.date_time_medition
                value = int(float(reg.pulses))

                # Calcular total
                new_total = total_m3(
                    pulses_factor, value, point_catchment,
                    current_dt=current_dt, frecuency_minutes=point_catchment.get("frecuency")
                )

                # Calcular diff hora y día
                new_diff = total_hour(new_total, point_catchment, current_dt)
                new_today_diff = total_day(point_catchment, current_dt, new_total)

                # Actualizar solo si cambió
                if new_total != reg.total or new_diff != reg.total_diff or new_today_diff != reg.total_today_diff:
                    with transaction.atomic():
                        reg.total = new_total
                        reg.total_diff = new_diff
                        reg.total_today_diff = new_today_diff
                        reg.save(update_fields=["total", "total_diff", "total_today_diff"])
                    updated += 1
                    print(f"    {reg.date_time_medition}: total {reg.total} -> {new_total}, diff {reg.total_diff} -> {new_diff}, today_diff {reg.total_today_diff} -> {new_today_diff}")
                else:
                    skipped += 1
            except Exception as e:
                errors += 1
                print(f"    ERROR {reg.date_time_medition}: {e}")

    print(f"\nResumen: actualizados={updated}, sin cambio={skipped}, errores={errors}")


if __name__ == "__main__":
    main()
