"""
Signals para crear tickets automáticamente desde alertas y eventos del sistema.
"""

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from api.core.models.alerts import AlertTrigger, SystemEvent
from api.core.models.tickets import SupportTicket

logger = logging.getLogger(__name__)


@receiver(post_save, sender=AlertTrigger)
def create_ticket_from_alert_trigger(sender, instance, created, **kwargs):
    """
    Cuando un AlertTrigger se marca como notificación enviada (notification_sent=True),
    crea un ticket de soporte automático si no existe ya uno vinculado.
    """
    if not created or not instance.notification_sent:
        return

    # Evitar duplicados
    if SupportTicket.objects.filter(alert_trigger=instance).exists():
        return

    rule = instance.alert_rule
    point = instance.point_catchment or rule.point_catchment
    if not point:
        logger.warning(f"AlertTrigger {instance.id} sin punto; no se crea ticket.")
        return

    # Mapear tipo de alerta a categoría
    category_map = {
        "THRESHOLD_MAX": "TELEMETRIA",
        "THRESHOLD_MIN": "TELEMETRIA",
        "NO_DATA": "CONECTIVIDAD",
        "DISCONNECTION": "CONECTIVIDAD",
        "RECONNECTION": "CONECTIVIDAD",
        "PROCESSING_ERROR": "TELEMETRIA",
        "RATE_OF_CHANGE": "TELEMETRIA",
        "DEVIATION": "TELEMETRIA",
        "SCHEDULED_REPORT": "SOFTWARE",
    }
    category = category_map.get(rule.target_type, "TELEMETRIA")

    # Prioridad según severidad
    priority_map = {
        "INFO": "BAJA",
        "WARNING": "MEDIA",
        "ALERT": "ALTA",
        "CRITICAL": "CRITICA",
    }
    priority = priority_map.get(rule.severity, "MEDIA")

    ticket = SupportTicket.objects.create(
        point_catchment=point,
        title=f"Alerta automática: {rule.name}",
        description=(
            f"Se disparó la regla '{rule.name}'.\n"
            f"Variable: {rule.variable_type or 'N/A'}\n"
            f"Valor medido: {instance.value_at_trigger}\n"
            f"Umbral: {instance.threshold_breached}\n"
            f"Fecha del disparo: {instance.triggered_at}"
        ),
        status="ABIERTO",
        priority=priority,
        category=category,
        source="ALERTA_AUTO",
        origin="INTERNO",
        alert_trigger=instance,
    )
    logger.info(f"Ticket #{ticket.id} creado automáticamente desde AlertTrigger {instance.id}.")


@receiver(post_save, sender=SystemEvent)
def create_ticket_from_system_event(sender, instance, created, **kwargs):
    """
    Cuando ocurre un SystemEvent de severidad CRITICAL, crea un ticket automático.
    """
    if not created or instance.severity != "CRITICAL":
        return

    # Evitar duplicados
    if SupportTicket.objects.filter(system_event=instance).exists():
        return

    point = instance.point_catchment
    if not point:
        logger.warning(f"SystemEvent {instance.id} sin punto; no se crea ticket.")
        return

    # Mapear evento a categoría
    category_map = {
        "COUNTER_RESET": "TELEMETRIA",
        "DISCONNECTION": "CONECTIVIDAD",
        "RECONNECTION": "CONECTIVIDAD",
        "MEASUREMENT_ERROR": "TELEMETRIA",
        "MASSIVE_JUMP_BLOCKED": "TELEMETRIA",
        "TOKEN_REFRESH": "SOFTWARE",
        "API_ERROR": "SOFTWARE",
    }
    category = category_map.get(instance.event_type, "TELEMETRIA")

    ticket = SupportTicket.objects.create(
        point_catchment=point,
        title=f"Evento crítico: {instance.title}",
        description=(
            f"Evento del sistema: {instance.event_type}\n"
            f"Mensaje: {instance.message}\n"
            f"Severidad: {instance.severity}\n"
            f"Fecha: {instance.created}"
        ),
        status="ABIERTO",
        priority="CRITICA",
        category=category,
        source="SISTEMA",
        origin="INTERNO",
        system_event=instance,
    )
    logger.info(f"Ticket #{ticket.id} creado automáticamente desde SystemEvent {instance.id}.")
