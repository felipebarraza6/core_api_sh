"""
Auditoría de telemetría — SystemEvent helper
=============================================

Cada anomalía detectada en el procesamiento de telemetría se registra
como un SystemEvent para trazabilidad histórica sin depender de logs
de texto.

Principio: nunca debe fallar el procesamiento principal por un error
de auditoría.
"""

import logging
from datetime import timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)


def emit_system_event(
    event_type,
    point_id,
    title,
    message,
    severity,
    extra_data=None,
    cooldown_minutes=60,
    condition_key=None,
    dedupe_until_resolved=False,
):
    """
    Guarda un SystemEvent en BD. Silencia cualquier excepción para no
    interrumpir el procesamiento de telemetría.

    Los eventos CRITICAL tienen un cooldown por defecto de 60 minutos
    para evitar saturación de tickets automáticos cuando un sensor
    falla de forma repetida.

    Si `dedupe_until_resolved=True` y se pasa `condition_key`, solo se
    crea un evento abierto por punto/condición hasta que se resuelva
    vía `resolve_system_events`.

    Args:
        event_type: str — choices de SystemEvent (MEASUREMENT_ERROR, API_ERROR, etc.)
        point_id: int — FK a CatchmentPoint
        title: str — máx 300 chars
        message: str — descripción libre
        severity: str — INFO | WARNING | CRITICAL
        extra_data: dict | None — metadatos adicionales
        cooldown_minutes: int — minutos de silencio para duplicados CRITICAL
        condition_key: str | None — clave estable de condición (ej. pulses_zero:25)
        dedupe_until_resolved: bool — una alerta abierta por condición
    """
    try:
        from api.core.models.alerts import SystemEvent

        payload = dict(extra_data or {})
        if condition_key:
            payload["condition_key"] = condition_key
            payload.setdefault("resolved", False)

        if dedupe_until_resolved and condition_key:
            open_qs = SystemEvent.objects.filter(
                event_type=event_type,
                point_catchment_id=point_id,
                extra_data__condition_key=condition_key,
            ).exclude(extra_data__resolved=True)
            if open_qs.exists():
                return

        if severity == "CRITICAL" and cooldown_minutes and not dedupe_until_resolved:
            recent_exists = SystemEvent.objects.filter(
                event_type=event_type,
                point_catchment_id=point_id,
                severity=severity,
                created__gte=timezone.now() - timedelta(minutes=cooldown_minutes),
            ).exists()
            if recent_exists:
                return

        SystemEvent.objects.create(
            event_type=event_type,
            point_catchment_id=point_id,
            title=title[:300],
            message=message,
            severity=severity,
            extra_data=payload,
        )
    except Exception:
        logger.exception(f"[AUDIT] Error guardando SystemEvent para punto {point_id}")


def resolve_system_events(point_id, condition_key):
    """
    Marca como resueltos los SystemEvent abiertos de una condición.

    Usado cuando la condición deja de cumplirse (ej. pulsos vuelven a >0).
    """
    if not condition_key:
        return
    try:
        from api.core.models.alerts import SystemEvent

        open_events = SystemEvent.objects.filter(
            point_catchment_id=point_id,
            extra_data__condition_key=condition_key,
        ).exclude(extra_data__resolved=True)

        now_iso = timezone.now().isoformat()
        for event in open_events:
            data = dict(event.extra_data or {})
            data["resolved"] = True
            data["resolved_at"] = now_iso
            event.extra_data = data
            event.save(update_fields=["extra_data"])
    except Exception:
        logger.exception(
            f"[AUDIT] Error resolviendo SystemEvent condición={condition_key} punto={point_id}"
        )
