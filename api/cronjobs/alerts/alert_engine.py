"""
Motor de alertas unificado — Fase 3.

Evalúa AlertRule según su frecuencia configurada (check_frequency_minutes).
Crea AlertTrigger cuando se cumple la condición.
El dispatcher (alert_dispatcher.py) se encarga de enviar las notificaciones.

Este motor reemplaza al legacy alert_evaluator.py (eliminado).
"""

from datetime import datetime, timedelta
from typing import List, Optional

import pytz
from django.utils import timezone

from api.core.models.alerts import AlertRule, AlertTrigger
from api.core.models.catchment_points import CatchmentPoint
from api.core.models.interaction_detail import InteractionDetail
from api.cronjobs.utils.logging_config import telemetry_logger
from api.cronjobs.utils.locks import cron_job_lock


@cron_job_lock("alert_engine", timeout=90)
def run(dry_run: bool = False) -> dict:
    """Wrapper para django-crontab."""
    return run_engine(dry_run=dry_run)

chile_tz = pytz.timezone("America/Santiago")


def run_engine(dry_run: bool = False) -> dict:
    """
    Punto de entrada del motor de alertas.

    Args:
        dry_run: Si True, solo loguea sin crear AlertTrigger.

    Returns:
        Dict con estadísticas de la ejecución.
    """
    now = datetime.now(chile_tz)
    current_minute = now.minute

    stats = {
        "evaluated": 0,
        "triggered": 0,
        "errors": 0,
        "dry_run": dry_run,
    }

    # Buscar reglas activas cuya frecuencia corresponda a este minuto
    rules = AlertRule.objects.filter(is_active=True)
    eligible_rules = [r for r in rules if current_minute % r.check_frequency_minutes == 0]

    telemetry_logger.info(f"[ALERT_ENGINE] Minuto={current_minute} | Reglas evaluables={len(eligible_rules)} | dry_run={dry_run}")

    for rule in eligible_rules:
        try:
            results = _evaluate_rule(rule, now)
            stats["evaluated"] += 1

            for should_trigger, value, threshold, interaction, point_id in results:
                if should_trigger:
                    stats["triggered"] += 1
                    if not dry_run:
                        trigger = AlertTrigger.objects.create(
                            alert_rule=rule,
                            triggered_at=now,
                            value_at_trigger=value,
                            threshold_breached=threshold,
                            interaction_detail_id=interaction.id if interaction else None,
                            point_catchment_id=point_id,
                            notification_sent=False,
                        )
                        telemetry_logger.info(
                            f"[ALERT_ENGINE] Trigger creado: regla={rule.id} punto={point_id} "
                            f"tipo={rule.target_type} valor={value} umbral={threshold}"
                        )
                    else:
                        telemetry_logger.info(
                            f"[ALERT_ENGINE] DRY-RUN trigger: regla={rule.id} punto={point_id} "
                            f"tipo={rule.target_type} valor={value} umbral={threshold}"
                        )
        except Exception as e:
            stats["errors"] += 1
            telemetry_logger.error(f"[ALERT_ENGINE] Error evaluando regla {rule.id}: {e}", exc_info=True)

    telemetry_logger.info(
        f"[ALERT_ENGINE] Fin | Evaluadas={stats['evaluated']} | Disparadas={stats['triggered']} | Errores={stats['errors']}"
    )
    return stats


def _evaluate_rule(rule: AlertRule, now: datetime) -> list:
    """
    Evalúa una sola AlertRule.

    Returns:
        Lista de tuplas: [(should_trigger, value_at_trigger, threshold_breached, interaction_detail, point_id), ...]
        point_id permite identificar qué punto disparó una regla global.
    """
    target = rule.target_type
    point = rule.point_catchment

    # Cooldown: verificar si ya hubo un trigger reciente
    if not _cooldown_passed(rule, now):
        return []

    if target in ("THRESHOLD_MAX", "THRESHOLD_MIN"):
        return _evaluate_threshold(rule, now)
    elif target == "NO_DATA":
        return _evaluate_no_data(rule, now)
    elif target == "DISCONNECTION":
        return _evaluate_disconnection(rule, now)
    elif target == "RECONNECTION":
        return _evaluate_reconnection(rule, now)
    elif target == "PROCESSING_ERROR":
        return _evaluate_processing_error(rule, now)
    elif target == "RATE_OF_CHANGE":
        return _evaluate_rate_of_change(rule, now)
    elif target == "SCHEDULED_REPORT":
        return _evaluate_scheduled_report(rule, now)

    return []


def _cooldown_passed(rule: AlertRule, now: datetime) -> bool:
    """Verifica si el cooldown de la regla ha pasado desde el último trigger."""
    last_trigger = AlertTrigger.objects.filter(alert_rule=rule).order_by("-triggered_at").first()
    if not last_trigger:
        return True
    cooldown = timedelta(minutes=rule.cooldown_minutes)
    return now - last_trigger.triggered_at >= cooldown


def _get_points_for_rule(rule: AlertRule):
    """Devuelve los puntos a evaluar para una regla."""
    if rule.points.exists():
        return rule.points.all()
    if rule.point_catchment:
        return [rule.point_catchment]
    # Global: todos los puntos activos con telemetría
    return (
        CatchmentPoint.objects.filter(data_config_profiles__is_telemetry=True)
        .exclude(ikolu_profiles__entry_by_form=True)
        .distinct()
    )


def _evaluate_threshold(rule: AlertRule, now: datetime) -> list:
    """Evalúa alertas de umbral MAX/MIN."""
    variable_type = rule.variable_type
    threshold = rule.threshold_value

    if not variable_type or threshold is None:
        return []

    points = _get_points_for_rule(rule)
    results = []

    for point in points:
        last_record = (
            InteractionDetail.objects.filter(catchment_point=point)
            .order_by("-date_time_medition")
            .first()
        )
        if not last_record:
            continue

        value = _extract_value(last_record, variable_type)
        if value is None:
            continue

        if rule.target_type == "THRESHOLD_MAX":
            triggered = value > threshold
        else:  # THRESHOLD_MIN
            triggered = value < threshold

        results.append((triggered, value, threshold, last_record, point.id))

    return results


def _evaluate_no_data(rule: AlertRule, now: datetime) -> list:
    """
    Evalúa alertas de ausencia de datos.
    Si la regla tiene una lista de puntos (M2M), evalúa esos.
    Si tiene punto_catchment individual, evalúa ese.
    Si es global (sin nada), evalúa TODOS los puntos activos.
    """
    minutes = rule.no_data_minutes or 60
    cutoff = now - timedelta(minutes=minutes)
    results = []

    for pt in _get_points_for_rule(rule):
        last_record = (
            InteractionDetail.objects.filter(catchment_point=pt)
            .order_by("-date_time_medition")
            .first()
        )
        if not last_record or not last_record.date_time_medition:
            # Nunca hubo datos = trigger inmediato para este punto
            results.append((True, None, minutes, None, pt.id))
            continue

        last_dt = last_record.date_time_medition
        if last_dt.tzinfo is None:
            last_dt = chile_tz.localize(last_dt)
        else:
            last_dt = last_dt.astimezone(chile_tz)

        triggered = last_dt < cutoff
        results.append((triggered, None, minutes, last_record, pt.id))

    return results


def _evaluate_disconnection(rule: AlertRule, now: datetime) -> list:
    """
    Evalúa alertas de desconexión usando days_not_conection del último InteractionDetail.
    Equivale a la lógica hardcodeada de google_chat.py::check_and_notify_disconnection.
    Ignora puntos desconectados hace más de max_disconnection_days (default 3) para evitar spam.
    """
    max_days = rule.max_disconnection_days if rule.max_disconnection_days is not None else 3
    results = []
    for pt in _get_points_for_rule(rule):
        last_record = (
            InteractionDetail.objects.filter(catchment_point=pt)
            .order_by("-date_time_medition")
            .first()
        )
        if not last_record:
            # Nunca hubo datos = considerado desconectado (si no excede max_days)
            results.append((True, None, None, None, pt.id))
            continue

        days = last_record.days_not_conection or 0
        if days > max_days:
            # Spam prevention: igual que google_chat.py (ignora > 3 días)
            continue

        triggered = days > 0
        results.append((triggered, days, None, last_record, pt.id))

    return results


def _evaluate_reconnection(rule: AlertRule, now: datetime) -> list:
    """
    Evalúa alertas de reconexión.
    Detecta transición de desconectado (> 0 días) a conectado (0 días)
    comparando el último InteractionDetail con el anterior.
    Equivale a google_chat.py::check_and_notify_reconnection.
    """
    results = []
    for pt in _get_points_for_rule(rule):
        # Obtener los últimos 2 registros ordenados por fecha
        records = list(
            InteractionDetail.objects.filter(catchment_point=pt)
            .order_by("-date_time_medition")[:2]
        )
        if len(records) < 2:
            continue

        current, previous = records[0], records[1]
        current_days = current.days_not_conection or 0
        previous_days = previous.days_not_conection or 0

        triggered = current_days == 0 and previous_days > 0
        results.append((triggered, current_days, previous_days, current, pt.id))

    return results


def _evaluate_processing_error(rule: AlertRule, now: datetime) -> list:
    """
    Evalúa alertas de error de procesamiento.
    Busca InteractionDetail con is_error=True en los últimos minutos
    según la frecuencia de la regla (o 10 min por defecto).
    Equivale a google_chat.py::check_and_notify_error.
    """
    window_minutes = rule.check_frequency_minutes or 10
    cutoff = now - timedelta(minutes=window_minutes)
    results = []

    for pt in _get_points_for_rule(rule):
        # Buscar errores recientes para este punto
        recent_errors = (
            InteractionDetail.objects.filter(
                catchment_point=pt,
                is_error=True,
                date_time_medition__gte=cutoff,
            )
            .order_by("-date_time_medition")
            .first()
        )
        if recent_errors:
            results.append((True, None, None, recent_errors, pt.id))

    return results


def _evaluate_rate_of_change(rule: AlertRule, now: datetime) -> list:
    """Evalúa alertas de tasa de cambio (pendiente de implementación completa)."""
    # TODO: Implementar comparación entre registro actual y registro hace N minutos
    return []


def _evaluate_scheduled_report(rule: AlertRule, now: datetime) -> list:
    """Evalúa reportes programados."""
    schedule = rule.report_schedule
    report_hour = rule.report_hour

    if schedule == "DAILY":
        triggered = report_hour is not None and now.hour == report_hour and now.minute == 0
    elif schedule == "WEEKLY":
        triggered = now.weekday() == 0 and report_hour is not None and now.hour == report_hour and now.minute == 0
    elif schedule == "MONTHLY":
        triggered = now.day == 1 and report_hour is not None and now.hour == report_hour and now.minute == 0
    else:
        triggered = False

    point_id = rule.point_catchment_id if rule.point_catchment_id else None
    return [(triggered, None, None, None, point_id)]


def _extract_value(record: InteractionDetail, variable_type: str) -> Optional[float]:
    """Extrae el valor numérico de un InteractionDetail según el tipo de variable."""
    if variable_type == "NIVEL":
        return float(record.nivel) if record.nivel is not None else None
    elif variable_type == "CAUDAL":
        return float(record.flow) if record.flow is not None else None
    elif variable_type == "CAUDAL PROMEDIO":
        return float(record.flow) if record.flow is not None else None
    elif variable_type == "TOTALIZADO":
        try:
            return float(record.total) if record.total is not None else None
        except (ValueError, TypeError):
            return None
    return None
