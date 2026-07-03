"""
Signals para crear tickets automáticamente desde alertas y eventos del sistema.
"""

import logging

from django.conf import settings
from django.core.mail import send_mail
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.template.loader import render_to_string
from django.utils.html import strip_tags

from api.core.models.alerts import AlertTrigger, SystemEvent
from api.core.models.tickets import SupportTicket, TicketCategory

logger = logging.getLogger(__name__)


def _notify_category_operators(ticket_id):
    """
    Envía notificación por correo a los operadores de la categoría del ticket.
    Se ejecuta sincrónicamente para evitar problemas de concurrencia en tests
    y mantener la trazabilidad; `fail_silently=True` evita que falle la request.
    """
    try:
        ticket = SupportTicket.objects.select_related("category").get(id=ticket_id)
    except SupportTicket.DoesNotExist:
        logger.warning(f"Ticket {ticket_id} no existe; no se envía notificación.")
        return

    category = ticket.category
    if not category or not category.notify_operators_on_create:
        return

    operators = list(category.operators.filter(is_active=True).values_list("email", flat=True))
    if not operators:
        return

    point = ticket.points.first()
    client_name = point.project.client.name if point and point.project and point.project.client else "N/A"
    point_name = point.title if point else "N/A"

    context = {
        "ticket_id": ticket.id,
        "title": ticket.title,
        "description": ticket.description,
        "client_name": client_name,
        "point_name": point_name,
        "category": str(category) if category else "N/A",
        "priority": ticket.priority,
        "priority_display": ticket.get_priority_display(),
        "source": ticket.source,
        "source_display": ticket.get_source_display(),
        "origin": ticket.origin,
        "origin_display": ticket.get_origin_display(),
        "created_by_name": ticket.created_by.get_full_name() if ticket.created_by else "N/A",
    }

    html_message = render_to_string("tickets/ticket_created.html", context)
    plain_message = strip_tags(html_message)
    subject = f"Nuevo ticket #{ticket.id}: {ticket.title}"

    try:
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "soporte@smarthydro.cl"),
            recipient_list=operators,
            html_message=html_message,
            fail_silently=True,
        )
        logger.info(f"Notificación de ticket #{ticket.id} enviada a {', '.join(operators)}")
    except Exception as e:
        logger.error(f"Error enviando notificación de ticket #{ticket.id}: {e}")


def _get_category(category_type, name):
    """Obtiene una categoría base activa por tipo y nombre."""
    try:
        return TicketCategory.objects.get(
            category_type=category_type,
            name=name,
            parent=None,
            is_active=True,
        )
    except TicketCategory.DoesNotExist:
        logger.warning(f"No se encontró TicketCategory {category_type}/{name}")
        return None


@receiver(post_save, sender=AlertTrigger)
def create_ticket_from_alert_trigger(sender, instance, created, **kwargs):
    """
    Cuando un AlertTrigger se marca como notificación enviada (notification_sent=True),
    crea un ticket de soporte automático si no existe ya uno vinculado.
    """
    # Solo crear ticket cuando la notificación fue efectivamente enviada.
    if not instance.notification_sent:
        return

    # Evitar duplicados si la signal se dispara más de una vez.
    if SupportTicket.objects.filter(alert_trigger=instance).exists():
        return

    rule = instance.alert_rule
    point = instance.point_catchment or rule.point_catchment
    if not point:
        logger.warning(f"AlertTrigger {instance.id} sin punto; no se crea ticket.")
        return

    # Mapear tipo de alerta a (tipo de categoría, nombre de categoría)
    category_map = {
        "THRESHOLD_MAX": ("HARDWARE", "Telemetría"),
        "THRESHOLD_MIN": ("HARDWARE", "Telemetría"),
        "NO_DATA": ("HARDWARE", "Conectividad"),
        "DISCONNECTION": ("HARDWARE", "Conectividad"),
        "RECONNECTION": ("HARDWARE", "Conectividad"),
        "PROCESSING_ERROR": ("HARDWARE", "Telemetría"),
        "RATE_OF_CHANGE": ("HARDWARE", "Telemetría"),
        "DEVIATION": ("HARDWARE", "Telemetría"),
        "SCHEDULED_REPORT": ("SOFTWARE", "Software"),
    }
    cat_type, cat_name = category_map.get(rule.target_type, ("HARDWARE", "Telemetría"))
    category = _get_category(cat_type, cat_name)

    # Prioridad según severidad
    priority_map = {
        "INFO": "BAJA",
        "WARNING": "MEDIA",
        "ALERT": "ALTA",
        "CRITICAL": "CRITICA",
    }
    priority = priority_map.get(rule.severity, "MEDIA")

    ticket = SupportTicket.objects.create(
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
    ticket.points.add(point)
    logger.info(f"Ticket #{ticket.id} creado automáticamente desde AlertTrigger {instance.id}.")
    _notify_category_operators(ticket.id)


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

    # Mapear evento a (tipo de categoría, nombre de categoría)
    category_map = {
        "COUNTER_RESET": ("HARDWARE", "Telemetría"),
        "DISCONNECTION": ("HARDWARE", "Conectividad"),
        "RECONNECTION": ("HARDWARE", "Conectividad"),
        "MEASUREMENT_ERROR": ("HARDWARE", "Telemetría"),
        "MASSIVE_JUMP_BLOCKED": ("HARDWARE", "Telemetría"),
        "TOKEN_REFRESH": ("SOFTWARE", "Software"),
        "API_ERROR": ("SOFTWARE", "Software"),
    }
    cat_type, cat_name = category_map.get(instance.event_type, ("HARDWARE", "Telemetría"))
    category = _get_category(cat_type, cat_name)

    ticket = SupportTicket.objects.create(
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
    ticket.points.add(point)
    logger.info(f"Ticket #{ticket.id} creado automáticamente desde SystemEvent {instance.id}.")
    _notify_category_operators(ticket.id)
