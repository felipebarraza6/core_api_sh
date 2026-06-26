"""
Procesamiento unificado para backfill histórico (re-sync por rango).
========================================================================

Este módulo aplica la lógica de negocio real (caudal convertido, nivel con offset,
totales en cascada) a registros ya ingresados en InteractionDetail.

A diferencia del cronjob en tiempo real, procesa registros en orden cronológico
usando SIEMPRE el registro inmediatamente anterior como base, evitando que
registros futuros contaminen el cálculo de totales durante backfill.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from django.db.models import QuerySet

from api.core.models import (
    CatchmentPoint,
    InteractionDetail,
    ProfileDataConfigCatchment,
    SchemesCatchment,
    Variable,
)
from api.cronjobs.telemetry.controllers.flow import (
    average_flow,
    instantaneous_flow,
)
from api.cronjobs.telemetry.controllers.nivel import nivel_mt, water_table
from api.cronjobs.telemetry.utils.audit import emit_system_event
from decimal import Decimal, ROUND_HALF_UP

logger = logging.getLogger(__name__)


def round_total(val):
    return int(Decimal(str(val)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _get_point_variables(point: CatchmentPoint) -> Dict[str, Variable]:
    """Obtener variables del punto indexadas por tipo."""
    scheme = SchemesCatchment.objects.filter(points_catchment=point).first()
    if not scheme:
        return {}
    return {v.type_variable.upper(): v for v in Variable.objects.filter(scheme_catchment=scheme)}


def _get_point_profile(point: CatchmentPoint) -> Optional[ProfileDataConfigCatchment]:
    """Obtener el profile de telemetría del punto."""
    return point.data_config_profiles.filter(is_telemetry=True).first()


def _get_range_records(
    point_id: int, start_dt: datetime, end_dt: datetime
) -> List[InteractionDetail]:
    """Traer registros del rango ordenados cronológicamente (más antiguo primero)."""
    return list(
        InteractionDetail.objects.filter(
            catchment_point_id=point_id,
            date_time_medition__gte=start_dt,
            date_time_medition__lt=end_dt,
        ).order_by("date_time_medition")
    )


def _get_pre_range_base(
    point_id: int, start_dt: datetime
) -> Tuple[Optional[float], Optional[float]]:
    """
    Obtener la base (last_pulses, last_total) del registro INMEDIATAMENTE ANTERIOR al rango.
    Retorna (None, None) si no hay registro previo válido.
    """
    prior = (
        InteractionDetail.objects.filter(
            catchment_point_id=point_id,
            date_time_medition__lt=start_dt,
        )
        .exclude(total__isnull=True)
        .exclude(total="")
        .exclude(total="0")
        .exclude(total="None")
        .exclude(pulses__isnull=True)
        .order_by("-date_time_medition")
        .first()
    )
    if not prior:
        return None, None
    try:
        last_total = float(prior.total)
        last_pulses = float(prior.pulses)
        return last_pulses, last_total
    except (ValueError, TypeError):
        return None, None


def recalc_totals_cascade(
    point: CatchmentPoint,
    start_dt: datetime,
    end_dt: datetime,
    pulses_factor: Optional[int] = None,
) -> int:
    """
    Recalcula totales en cascada para registros del rango.
    Usa el registro inmediatamente anterior al rango como base.
    NO genera CounterResetLog ni notificaciones (para no spammear en backfill).

    Retorna cantidad de registros actualizados.
    """
    point_id = point.id
    if pulses_factor is None:
        v = Variable.objects.filter(
            type_variable="TOTALIZADO",
            scheme_catchment__points_catchment=point,
        ).first()
        pulses_factor = v.pulses_factor if v and v.pulses_factor else 1000

    records = _get_range_records(point_id, start_dt, end_dt)
    if not records:
        return 0

    last_pulses, last_total = _get_pre_range_base(point_id, start_dt)
    updated = 0

    for reg in records:
        current_pulses = reg.pulses
        if current_pulses is None:
            continue

        # Si pulses=0 pero tenemos base, propagar último total (monotonicidad)
        if current_pulses == 0 and last_total is not None:
            if reg.total != str(int(last_total)):
                reg.total = str(int(last_total))
                reg.total_diff = 0
                reg.save(update_fields=["total", "total_diff"])
                updated += 1
            continue

        cp = float(current_pulses)

        if last_pulses is None or last_total is None:
            # Sin base previa: usar addition del profile como offset
            profile = _get_point_profile(point)
            addition = float(profile.addition) if profile and profile.addition else 0.0
            new_total = (cp * pulses_factor) / 1000.0 + addition
            last_pulses = cp
        else:
            if cp >= last_pulses:
                diff = cp - last_pulses
            else:
                # Reset detectado: asumimos que el contador se reinició
                diff = cp
            new_total = last_total + (diff * pulses_factor) / 1000.0
            last_pulses = cp

        last_total = new_total
        new_total_rounded = int(round(new_total))

        # Solo actualizar si cambió significativamente
        try:
            old_total = float(reg.total) if reg.total not in (None, "", "None") else 0.0
        except (ValueError, TypeError):
            old_total = 0.0

        if abs(int(round(old_total)) - new_total_rounded) > 0 or reg.total in (None, "", "None"):
            reg.total = str(new_total_rounded)
            reg.save(update_fields=["total"])
            updated += 1

    return updated


def process_flow_for_range(
    point: CatchmentPoint,
    start_dt: datetime,
    end_dt: datetime,
    var_config: Optional[Variable] = None,
) -> int:
    """
    Aplica instantaneous_flow() a los registros del rango que tengan CAUDAL.
    Retorna cantidad de registros actualizados.
    """
    if var_config is None:
        vars_map = _get_point_variables(point)
        var_config = vars_map.get("CAUDAL")
    if not var_config:
        return 0

    records = _get_range_records(point.id, start_dt, end_dt)
    updated = 0
    convert_to_lt = var_config.convert_to_lt
    scale_divisor = var_config.calculate_nivel

    for reg in records:
        raw_flow = reg.flow
        if raw_flow is None:
            continue
        processed = instantaneous_flow(raw_flow, convert_to_lt, scale_divisor)
        # Solo actualizar si cambió (comparación con tolerancia float)
        if abs(float(reg.flow or 0) - processed) > 0.005:
            reg.flow = processed
            reg.save(update_fields=["flow"])
            updated += 1

    return updated


def process_nivel_for_range(
    point: CatchmentPoint,
    start_dt: datetime,
    end_dt: datetime,
    var_config: Optional[Variable] = None,
    profile: Optional[ProfileDataConfigCatchment] = None,
) -> int:
    """
    Aplica nivel_mt() + water_table() a registros del rango.
    Usa nivel_offset del profile y d3 del profile.
    Retorna cantidad de registros actualizados.
    """
    if var_config is None:
        vars_map = _get_point_variables(point)
        var_config = vars_map.get("NIVEL")
    if not var_config:
        return 0

    if profile is None:
        profile = _get_point_profile(point)

    # Offset configurable del profile (reemplaza hardcodeo)
    nivel_offset = float(profile.nivel_offset) if profile and profile.nivel_offset else 0.0
    d3 = profile.d3 if profile else 0

    records = _get_range_records(point.id, start_dt, end_dt)
    updated = 0
    calculate_nivel = var_config.calculate_nivel

    for reg in records:
        raw_nivel = reg.nivel
        if raw_nivel is None:
            continue

        nivel_con_offset = float(raw_nivel) + nivel_offset
        nivel_procesado = nivel_mt(
            nivel_con_offset,
            calculate_nivel,
            point.id,
            d3,
        )
        try:
            nivel_float = float(nivel_procesado)
        except (ValueError, TypeError):
            nivel_float = 0.0

        wt_procesado = water_table(nivel_float, d3)
        try:
            wt_float = float(wt_procesado)
        except (ValueError, TypeError):
            wt_float = 0.0

        # Solo actualizar si cambió
        old_nivel = float(reg.nivel or 0)
        old_wt = float(reg.water_table or 0)
        if abs(old_nivel - nivel_float) > 0.005 or abs(old_wt - wt_float) > 0.005:
            reg.nivel = nivel_float
            reg.water_table = wt_float
            reg.save(update_fields=["nivel", "water_table"])
            updated += 1

    return updated


def process_average_flow_for_range(
    point: CatchmentPoint,
    start_dt: datetime,
    end_dt: datetime,
    var_config: Optional[Variable] = None,
) -> int:
    """
    Aplica average_flow() a registros del rango que tengan CAUDAL_PROMEDIO configurado
    y store_average_flow=True.
    Retorna cantidad de registros actualizados.
    """
    if var_config is None:
        vars_map = _get_point_variables(point)
        var_config = vars_map.get("CAUDAL_PROMEDIO")
    if not var_config or not var_config.store_average_flow:
        return 0

    records = _get_range_records(point.id, start_dt, end_dt)
    updated = 0

    # Construir point_catchment dict mínimo para average_flow
    point_dict = {"id": point.id}

    for reg in records:
        total_val = reg.total
        if total_val is None:
            continue
        try:
            total_float = float(total_val)
        except (ValueError, TypeError):
            continue

        dt_lg = reg.date_time_last_logger
        if not dt_lg:
            dt_lg = reg.date_time_medition

        processed = average_flow(point_dict, total_float, dt_lg)
        old_flow = float(reg.flow or 0)
        if abs(old_flow - processed) > 0.005:
            reg.flow = processed
            reg.save(update_fields=["flow"])
            updated += 1

    return updated


def recalc_diffs_for_range(
    point: CatchmentPoint,
    start_dt: datetime,
    end_dt: datetime,
) -> Tuple[int, int]:
    """
    Recalcula total_diff y total_today_diff para registros del rango.
    """
    point_id = point.id
    records = list(
        InteractionDetail.objects.filter(
            catchment_point_id=point_id,
            date_time_medition__gte=start_dt,
            date_time_medition__lt=end_dt,
        ).order_by("date_time_medition").values(
            "id", "date_time_medition", "total", "total_diff", "total_today_diff"
        )
    )
    if not records:
        return 0, 0

    # Base pre-rango
    prior = InteractionDetail.objects.filter(
        catchment_point_id=point_id,
        date_time_medition__lt=start_dt,
    ).exclude(total__isnull=True).exclude(total="").exclude(total="0").exclude(total="None").order_by(
        "-date_time_medition"
    ).values("total").first()

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

        # total_diff
        new_diff = max(0, round_total(curr_total) - round_total(prev_total))
        old_diff = r["total_diff"] or 0
        if new_diff != old_diff:
            InteractionDetail.objects.filter(id=rid).update(total_diff=new_diff)
            diff_updates += 1

        # total_today_diff
        first_total = first_total_of_day.get(day, 0.0)
        new_today_diff = max(0, round_total(curr_total) - round_total(first_total))
        old_today_diff = r["total_today_diff"] or 0
        if new_today_diff != old_today_diff:
            InteractionDetail.objects.filter(id=rid).update(total_today_diff=new_today_diff)
            today_diff_updates += 1

        prev_total = curr_total

    return diff_updates, today_diff_updates


def process_backfill_range(
    point: CatchmentPoint,
    start_dt: datetime,
    end_dt: datetime,
) -> Dict[str, Any]:
    """
    Orquesta el procesamiento completo de un rango de backfill.

    Fases:
    1. Recalcular totales en cascada (con base del registro anterior)
    2. Procesar caudal instantáneo (conversión L/s)
    3. Procesar nivel + water_table (con offset y d3)
    4. Procesar caudal promedio (si aplica)
    5. Recalcular diffs (total_diff, total_today_diff)

    Retorna dict con contadores de actualizaciones.
    """

    vars_map = _get_point_variables(point)
    profile = _get_point_profile(point)

    # Fase 1: Totales en cascada
    totals_updated = recalc_totals_cascade(point, start_dt, end_dt)

    # Fase 2: Caudal instantáneo
    flow_updated = process_flow_for_range(
        point, start_dt, end_dt, vars_map.get("CAUDAL")
    )

    # Fase 3: Nivel + water_table
    nivel_updated = process_nivel_for_range(
        point, start_dt, end_dt, vars_map.get("NIVEL"), profile
    )

    # Fase 4: Caudal promedio
    avg_flow_updated = process_average_flow_for_range(
        point, start_dt, end_dt, vars_map.get("CAUDAL_PROMEDIO")
    )

    # Fase 5: Recalcular diffs
    diff_upd, today_upd = recalc_diffs_for_range(point, start_dt, end_dt)

    return {
        "totals_updated": totals_updated,
        "flow_updated": flow_updated,
        "nivel_updated": nivel_updated,
        "avg_flow_updated": avg_flow_updated,
        "diff_updated": diff_upd,
        "today_diff_updated": today_upd,
    }


def detect_gaps(
    point: CatchmentPoint,
    start_dt: Optional[datetime] = None,
    end_dt: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """
    Detecta gaps (huecos) de datos para un punto en un rango.

    Si no se pasan start/end, busca desde el primer registro existente hasta el último.
    Retorna lista de dicts: [{"start_gap": "...", "end_gap": "...", "missing_count": N}, ...]
    """
    point_id = point.id
    freq_str = point.frecuency or "60"
    try:
        freq_min = int(freq_str)
    except (ValueError, TypeError):
        freq_min = 60

    # Determinar rango de búsqueda
    qs = InteractionDetail.objects.filter(catchment_point_id=point_id)
    if start_dt and end_dt:
        qs = qs.filter(date_time_medition__gte=start_dt, date_time_medition__lt=end_dt)

    first = qs.order_by("date_time_medition").values_list("date_time_medition", flat=True).first()
    last = qs.order_by("-date_time_medition").values_list("date_time_medition", flat=True).first()

    if not first or not last:
        return []

    # Generar todos los buckets esperados
    from datetime import timedelta

    existing = set(
        InteractionDetail.objects.filter(
            catchment_point_id=point_id,
            date_time_medition__gte=first,
            date_time_medition__lte=last,
        ).values_list("date_time_medition", flat=True)
    )

    gaps = []
    current = first.replace(second=0, microsecond=0)
    if freq_min == 60:
        current = current.replace(minute=0)
    elif freq_min == 5:
        current = current.replace(minute=(current.minute // 5) * 5)
    elif freq_min == 10:
        current = current.replace(minute=(current.minute // 10) * 10)

    gap_start = None
    while current <= last:
        if current not in existing:
            if gap_start is None:
                gap_start = current
        else:
            if gap_start is not None:
                gaps.append({
                    "start_gap": gap_start.strftime("%Y-%m-%dT%H:%M:%S"),
                    "end_gap": (current - timedelta(minutes=freq_min)).strftime("%Y-%m-%dT%H:%M:%S"),
                    "missing_count": int((current - gap_start).total_seconds() / 60 / freq_min),
                })
                gap_start = None
        current += timedelta(minutes=freq_min)

    # Cerrar gap abierto al final
    if gap_start is not None:
        gaps.append({
            "start_gap": gap_start.strftime("%Y-%m-%dT%H:%M:%S"),
            "end_gap": last.strftime("%Y-%m-%dT%H:%M:%S"),
            "missing_count": int((last - gap_start).total_seconds() / 60 / freq_min) + 1,
        })

    return gaps
