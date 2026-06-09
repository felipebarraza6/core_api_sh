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
):
    """
    Guarda un SystemEvent en BD. Silencia cualquier excepción para no
    interrumpir el procesamiento de telemetría.

    Los eventos CRITICAL tienen un cooldown por defecto de 60 minutos
    para evitar saturación de tickets automáticos cuando un sensor
    falla de forma repetida.

    Args:
        event_type: str — choices de SystemEvent (MEASUREMENT_ERROR, API_ERROR, etc.)
        point_id: int — FK a CatchmentPoint
        title: str — máx 300 chars
        message: str — descripción libre
        severity: str — INFO | WARNING | CRITICAL
        extra_data: dict | None — metadatos adicionales
        cooldown_minutes: int — minutos de silencio para duplicados CRITICAL
    """
    try:
        from api.core.models.alerts import SystemEvent

        if severity == "CRITICAL" and cooldown_minutes:
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
            extra_data=extra_data or {},
        )
    except Exception:
        logger.exception(f"[AUDIT] Error guardando SystemEvent para punto {point_id}")
