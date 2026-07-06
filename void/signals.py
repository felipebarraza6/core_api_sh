"""Señales de void."""
import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from void.models import DeviceEvent
from void.services.alerts import AlertEngine
from void.tasks import void_dispatch_alerts

logger = logging.getLogger(__name__)


@receiver(post_save, sender=DeviceEvent)
def evaluate_device_event_alert(sender, instance, created, **kwargs):
    """Evalúa reglas de alerta cuando se crea un DeviceEvent."""
    if not created:
        return

    try:
        triggers = AlertEngine().evaluate_event(instance)
        if triggers:
            # Encolar dispatch asíncrono de alertas generadas.
            void_dispatch_alerts.delay(
                trigger_ids=[t.id for t in triggers if t is not None]
            )
    except Exception as exc:
        logger.exception("Error evaluando alertas para evento %s: %s", instance.id, exc)
