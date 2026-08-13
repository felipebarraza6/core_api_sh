"""
Signals para crear tickets automáticamente desde alertas y eventos del sistema.
"""

import logging
import re

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

    # Los tickets de origen interno son borradores/eventos automáticos;
    # no se notifica a operadores porque aún no requieren atención humana.
    if ticket.origin == "INTERNO":
        return

    category = ticket.category
    if not category or not category.notify_operators_on_create:
        return

    operators = set(category.operators.filter(is_active=True, notify_email=True).values_list("email", flat=True))

    # Modo prueba: limitar destinatarios a lista configurada
    test_only = getattr(settings, "SLA_OVERDUE_TEST_ONLY", None)
    if test_only:
        allowed = set(test_only)
        operators = operators & allowed
        if not operators:
            return

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

    recipient_list = sorted(operators)

    try:
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "soporte@smarthydro.cl"),
            recipient_list=recipient_list,
            html_message=html_message,
            fail_silently=True,
        )
        logger.info(f"Notificación de ticket #{ticket.id} enviada a {', '.join(recipient_list)}")
    except Exception as e:
        logger.error(f"Error enviando notificación de ticket #{ticket.id}: {e}")


def _notify_scheduled_date_confirmed(ticket, confirmer):
    """
    Envía notificación por correo cuando se confirma la fecha planificada de
    una OT (orden de trabajo).

    Destinatarios:
      - La persona que confirmó la fecha.
      - Los involucrados en el ticket de soporte: creador, asignado,
        operadores de la categoría y dueños/visores de los puntos vinculados.

    Correo configurable con lo ya existente: `DEFAULT_FROM_EMAIL` y el modo
    prueba `SLA_OVERDUE_TEST_ONLY` (lista blanca de destinatarios).
    """
    if not ticket.scheduled_date or not ticket.scheduled_date_confirmed:
        return

    confirmer_email = confirmer.email if confirmer else None
    recipients = set()
    if confirmer_email:
        recipients.add(confirmer_email)

    # Involucrados en el ticket
    involved = []
    if ticket.created_by and ticket.created_by.id != getattr(confirmer, "id", None):
        involved.append(ticket.created_by)
    if ticket.assigned_to and ticket.assigned_to.id != getattr(confirmer, "id", None):
        involved.append(ticket.assigned_to)
    if ticket.category:
        involved.extend(ticket.category.operators.all())

    for point in ticket.points.prefetch_related("users_viewers").all():
        involved.append(point.owner_user)
        involved.extend(point.users_viewers.all())

    for user in involved:
        if not user or not user.is_active or not user.email:
            continue
        if not user.notify_email:
            continue
        if user.id == getattr(confirmer, "id", None):
            continue
        recipients.add(user.email)

    recipients.discard("")
    if not recipients:
        return

    # Modo prueba: limitar destinatarios a lista configurada
    test_only = getattr(settings, "SLA_OVERDUE_TEST_ONLY", None)
    if test_only:
        allowed = set(test_only)
        recipients = recipients & allowed
        if not recipients:
            return

    point = ticket.points.first()
    client_name = (
        point.project.client.name
        if point and point.project and point.project.client
        else "N/A"
    )
    point_name = point.title if point else "N/A"
    confirmed_by_name = (
        confirmer.get_full_name() or confirmer.email
        if confirmer
        else "Usuario"
    )

    context = {
        "ticket_id": ticket.id,
        "title": ticket.title,
        "scheduled_date": ticket.scheduled_date.strftime("%d/%m/%Y"),
        "confirmed_by_name": confirmed_by_name,
        "confirmed_at": (
            ticket.scheduled_date_confirmed_at.strftime("%d/%m/%Y %H:%M")
            if ticket.scheduled_date_confirmed_at
            else "N/A"
        ),
        "client_name": client_name,
        "point_name": point_name,
        "category": str(ticket.category) if ticket.category else "N/A",
        "priority": ticket.priority,
        "priority_display": ticket.get_priority_display(),
        "status": ticket.status,
        "status_display": ticket.get_status_display(),
        "assigned_to_name": (
            ticket.assigned_to.get_full_name() if ticket.assigned_to else "Sin asignar"
        ),
    }

    html_message = render_to_string("tickets/ticket_date_confirmed.html", context)
    plain_message = strip_tags(html_message)
    subject = f"Fecha confirmada Ticket #{ticket.id}: {ticket.title}"

    recipient_list = sorted(recipients)

    try:
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "soporte@smarthydro.cl"),
            recipient_list=recipient_list,
            html_message=html_message,
            fail_silently=True,
        )
        logger.info(
            f"Notificación de fecha confirmada Ticket #{ticket.id} enviada a "
            f"{', '.join(recipient_list)}"
        )
    except Exception as e:
        logger.error(f"Error enviando notificación de fecha confirmada Ticket #{ticket.id}: {e}")


def _notify_scheduled_date_cancelled(ticket, canceller):
    """
    Envía notificación por correo cuando se cancela la fecha planificada de una OT.

    Los destinatarios son los mismos que en la confirmación: la persona que
    cancela y los involucrados (creador, asignado, operadores de la categoría y
    dueños/visores de los puntos). Reutiliza `DEFAULT_FROM_EMAIL` y el modo
    prueba `SLA_OVERDUE_TEST_ONLY`.
    """
    if not ticket.scheduled_date or not ticket.scheduled_date_cancelled:
        return

    canceller_email = canceller.email if canceller else None
    recipients = set()
    if canceller_email:
        recipients.add(canceller_email)

    involved = []
    if ticket.created_by and ticket.created_by.id != getattr(canceller, "id", None):
        involved.append(ticket.created_by)
    if ticket.assigned_to and ticket.assigned_to.id != getattr(canceller, "id", None):
        involved.append(ticket.assigned_to)
    if ticket.category:
        involved.extend(ticket.category.operators.all())

    for point in ticket.points.prefetch_related("users_viewers").all():
        involved.append(point.owner_user)
        involved.extend(point.users_viewers.all())

    for user in involved:
        if not user or not user.is_active or not user.email:
            continue
        if not user.notify_email:
            continue
        if user.id == getattr(canceller, "id", None):
            continue
        recipients.add(user.email)

    recipients.discard("")
    if not recipients:
        return

    test_only = getattr(settings, "SLA_OVERDUE_TEST_ONLY", None)
    if test_only:
        allowed = set(test_only)
        recipients = recipients & allowed
        if not recipients:
            return

    point = ticket.points.first()
    client_name = (
        point.project.client.name
        if point and point.project and point.project.client
        else "N/A"
    )
    point_name = point.title if point else "N/A"
    cancelled_by_name = (
        canceller.get_full_name() or canceller.email
        if canceller
        else "Usuario"
    )

    context = {
        "ticket_id": ticket.id,
        "title": ticket.title,
        "scheduled_date": ticket.scheduled_date.strftime("%d/%m/%Y"),
        "cancelled_by_name": cancelled_by_name,
        "cancelled_at": (
            ticket.scheduled_date_cancelled_at.strftime("%d/%m/%Y %H:%M")
            if ticket.scheduled_date_cancelled_at
            else "N/A"
        ),
        "reason": ticket.scheduled_date_cancelled_reason or "No indicado",
        "client_name": client_name,
        "point_name": point_name,
        "category": str(ticket.category) if ticket.category else "N/A",
        "priority": ticket.priority,
        "priority_display": ticket.get_priority_display(),
        "status": ticket.status,
        "status_display": ticket.get_status_display(),
        "assigned_to_name": (
            ticket.assigned_to.get_full_name() if ticket.assigned_to else "Sin asignar"
        ),
    }

    html_message = render_to_string("tickets/ticket_date_cancelled.html", context)
    plain_message = strip_tags(html_message)
    subject = f"Fecha cancelada Ticket #{ticket.id}: {ticket.title}"

    recipient_list = sorted(recipients)

    try:
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "soporte@smarthydro.cl"),
            recipient_list=recipient_list,
            html_message=html_message,
            fail_silently=True,
        )
        logger.info(
            f"Notificación de fecha cancelada Ticket #{ticket.id} enviada a "
            f"{', '.join(recipient_list)}"
        )
    except Exception as e:
        logger.error(f"Error enviando notificación de fecha cancelada Ticket #{ticket.id}: {e}")


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


def _ticket_involved_users(ticket):
    """Usuarios involucrados en un ticket: creador, asignado, operadores de la
    categoría y dueños/visores de los puntos vinculados. Solo usuarios activos."""
    involved = set()
    if ticket.created_by:
        involved.add(ticket.created_by)
    if ticket.assigned_to:
        involved.add(ticket.assigned_to)
    if ticket.category:
        involved.update(ticket.category.operators.filter(is_active=True))
    for point in ticket.points.prefetch_related("users_viewers").all():
        if point.owner_user:
            involved.add(point.owner_user)
        involved.update(point.users_viewers.filter(is_active=True))
    return [u for u in involved if u.is_active]


def _extract_mention_tokens(content):
    """Extrae los tokens @usuario de un texto (p. ej. '@juan' de '@juan, me avisas')."""
    if not content:
        return set()
    return {token.lower() for token in re.findall(r"@([\w.]+)", content)}


def _resolve_mentioned_users(content, ticket):
    """Resuelve las menciones @usuario del contenido contra los usuarios
    involucrados en el ticket. Retorna lista de User sin duplicados."""
    tokens = _extract_mention_tokens(content)
    if not tokens:
        return []
    involved = _ticket_involved_users(ticket)
    if not involved:
        return []

    index = {}
    for user in involved:
        keys = {user.username.lower()}
        if user.email:
            keys.add(user.email.lower())
            keys.add(user.email.split("@")[0].lower())
        if user.first_name:
            keys.add(user.first_name.lower())
        if user.last_name:
            keys.add(user.last_name.lower())
        if user.first_name and user.last_name:
            keys.add(f"{user.first_name} {user.last_name}".lower())
        for key in keys:
            index.setdefault(key, user)

    resolved = {}
    for token in tokens:
        user = index.get(token) or index.get(token.rstrip("."))
        if user:
            resolved[user.id] = user
    return list(resolved.values())


def _notify_comment_mentions(comment, ticket, author):
    """Notifica por email + in-app a los usuarios mencionados (@usuario) en un
    comentario. Respeta la preferencia notify_email y excluye al autor."""
    from api.core.models.tickets import TicketNotification

    mentioned = [
        u
        for u in _resolve_mentioned_users(comment.content, ticket)
        if u.id != getattr(author, "id", None)
    ]
    if not mentioned:
        return []

    author_name = author.get_full_name() or author.email if author else "Usuario"
    point = ticket.points.first()
    client_name = (
        point.project.client.name
        if point and point.project and point.project.client
        else "N/A"
    )
    point_name = point.title if point else "N/A"

    context = {
        "ticket_id": ticket.id,
        "title": ticket.title,
        "comment": comment.content,
        "comment_id": comment.id,
        "author_name": author_name,
        "client_name": client_name,
        "point_name": point_name,
        "status_display": ticket.get_status_display(),
    }
    html_message = render_to_string("tickets/ticket_mention.html", context)
    plain_message = strip_tags(html_message)
    subject = f"Te mencionaron en Ticket #{ticket.id}: {ticket.title}"

    test_only = getattr(settings, "SLA_OVERDUE_TEST_ONLY", None)
    allowed = set(test_only) if test_only else None

    recipients = []
    seen = set()
    for user in mentioned:
        TicketNotification.objects.create(
            user=user,
            ticket=ticket,
            comment=comment,
            notification_type=TicketNotification.MENTION,
            message=f"{author_name} te mencionó en el ticket #{ticket.id}",
        )
        if not user.notify_email or not user.email or user.email in seen:
            continue
        if allowed is not None and user.email not in allowed:
            continue
        seen.add(user.email)
        recipients.append(user.email)

    if recipients:
        try:
            send_mail(
                subject=subject,
                message=plain_message,
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "soporte@smarthydro.cl"),
                recipient_list=sorted(recipients),
                html_message=html_message,
                fail_silently=True,
            )
            logger.info(
                f"Mención en Ticket #{ticket.id}: correo a {', '.join(sorted(recipients))}"
            )
        except Exception as e:
            logger.error(f"Error enviando mención Ticket #{ticket.id}: {e}")

    return mentioned


def _extract_ticket_references(content):
    """Extrae referencias #<id> de ticket de un texto (p. ej. '#245' o '#245,')."""
    if not content:
        return set()
    return {int(ref) for ref in re.findall(r"#(\d+)", content)}


def _notify_ticket_references(comment, ticket, author):
    """Notifica (email + in-app) a los involucrados de los tickets referenciados
    (#<id>) dentro de un comentario, excluyendo el ticket donde se escribió."""
    from api.core.models.tickets import TicketNotification

    ref_ids = _extract_ticket_references(comment.content) - {ticket.id}
    if not ref_ids:
        return []

    ref_tickets = list(SupportTicket.objects.filter(id__in=ref_ids))
    if not ref_tickets:
        return []

    author_name = author.get_full_name() or author.email if author else "Usuario"
    test_only = getattr(settings, "SLA_OVERDUE_TEST_ONLY", None)
    allowed = set(test_only) if test_only else None

    recipients = []
    seen = set()
    notified = []
    for ref in ref_tickets:
        for user in _ticket_involved_users(ref):
            if user.id == getattr(author, "id", None):
                continue
            TicketNotification.objects.create(
                user=user,
                ticket=ref,
                comment=comment,
                notification_type=TicketNotification.REFERENCE,
                message=(
                    f"{author_name} referenció tu ticket #{ref.id} "
                    f"desde el ticket #{ticket.id}"
                ),
            )
            notified.append(user)
            if not user.notify_email or not user.email or user.email in seen:
                continue
            if allowed is not None and user.email not in allowed:
                continue
            seen.add(user.email)
            recipients.append(user.email)

    if recipients:
        context = {
            "ticket_id": ticket.id,
            "title": ticket.title,
            "comment": comment.content,
            "comment_id": comment.id,
            "author_name": author_name,
            "referenced_tickets": [r.id for r in ref_tickets],
        }
        html_message = render_to_string("tickets/ticket_reference.html", context)
        plain_message = strip_tags(html_message)
        subject = f"Referenciaron tu ticket en #{ticket.id}: {ticket.title}"
        try:
            send_mail(
                subject=subject,
                message=plain_message,
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "soporte@smarthydro.cl"),
                recipient_list=sorted(recipients),
                html_message=html_message,
                fail_silently=True,
            )
            logger.info(
                f"Referencia en Ticket #{ticket.id}: correo a {', '.join(sorted(recipients))}"
            )
        except Exception as e:
            logger.error(f"Error enviando referencia Ticket #{ticket.id}: {e}")

    return notified


def _notify_ticket_assigned(ticket, actor, new_assignee):
    """Notifica por correo cuando un ticket es asignado/reasignado.

    Destinatarios: el nuevo asignado, los operadores de la categoría y el
    creador del ticket. Excluye a quien realiza la acción. Respeta la
    preferencia notify_email y el modo prueba SLA_OVERDUE_TEST_ONLY.
    """
    if not new_assignee:
        return []

    users = set()
    if new_assignee.is_active:
        users.add(new_assignee)
    if ticket.category:
        users.update(ticket.category.operators.filter(is_active=True))
    if ticket.created_by and ticket.created_by.is_active:
        users.add(ticket.created_by)

    actor_id = getattr(actor, "id", None)
    actor_name = actor.get_full_name() or actor.email if actor else "Usuario"
    assignee_name = new_assignee.get_full_name() or new_assignee.email

    point = ticket.points.first()
    client_name = (
        point.project.client.name
        if point and point.project and point.project.client
        else "N/A"
    )
    point_name = point.title if point else "N/A"

    context = {
        "ticket_id": ticket.id,
        "title": ticket.title,
        "assignee_name": assignee_name,
        "assigner_name": actor_name,
        "client_name": client_name,
        "point_name": point_name,
        "status_display": ticket.get_status_display(),
        "priority_display": ticket.get_priority_display(),
    }
    html_message = render_to_string("tickets/ticket_assigned.html", context)
    plain_message = strip_tags(html_message)
    subject = f"Te asignaron el ticket #{ticket.id}: {ticket.title}"

    test_only = getattr(settings, "SLA_OVERDUE_TEST_ONLY", None)
    allowed = set(test_only) if test_only else None

    recipients = []
    seen = set()
    for user in sorted(users, key=lambda u: u.email or ""):
        if not user.is_active or user.id == actor_id:
            continue
        if not user.notify_email or not user.email or user.email in seen:
            continue
        if allowed is not None and user.email not in allowed:
            continue
        seen.add(user.email)
        recipients.append(user.email)

    if recipients:
        try:
            send_mail(
                subject=subject,
                message=plain_message,
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "soporte@smarthydro.cl"),
                recipient_list=sorted(recipients),
                html_message=html_message,
                fail_silently=True,
            )
            logger.info(
                f"Asignación Ticket #{ticket.id}: correo a {', '.join(sorted(recipients))}"
            )
        except Exception as e:
            logger.error(f"Error enviando asignación Ticket #{ticket.id}: {e}")

    return recipients


def _notify_ticket_status_changed(ticket, actor, old_status, new_status):
    """Notifica por correo a los involucrados del ticket cuando cambia su estado.

    Destinatarios: involucrados del ticket (creador, asignado, operadores de la
    categoría y dueños/visores de los puntos). Excluye a quien realiza la acción.
    Respeta la preferencia notify_email y el modo prueba SLA_OVERDUE_TEST_ONLY.
    """
    if not new_status or new_status == old_status:
        return []

    status_display = dict(SupportTicket.STATUS_CHOICES)
    users = [
        u
        for u in _ticket_involved_users(ticket)
        if u.id != getattr(actor, "id", None)
    ]
    if not users:
        return []

    actor_name = actor.get_full_name() or actor.email if actor else "Usuario"
    point = ticket.points.first()
    client_name = (
        point.project.client.name
        if point and point.project and point.project.client
        else "N/A"
    )
    point_name = point.title if point else "N/A"

    context = {
        "ticket_id": ticket.id,
        "title": ticket.title,
        "old_status_display": status_display.get(old_status, old_status) if old_status else "—",
        "new_status_display": status_display.get(new_status, new_status),
        "actor_name": actor_name,
        "client_name": client_name,
        "point_name": point_name,
        "priority_display": ticket.get_priority_display(),
    }
    html_message = render_to_string("tickets/ticket_status_changed.html", context)
    plain_message = strip_tags(html_message)
    subject = (
        f"Ticket #{ticket.id} cambió a {status_display.get(new_status, new_status)}: "
        f"{ticket.title}"
    )

    test_only = getattr(settings, "SLA_OVERDUE_TEST_ONLY", None)
    allowed = set(test_only) if test_only else None

    recipients = []
    seen = set()
    for user in sorted(users, key=lambda u: u.email or ""):
        if not user.is_active or not user.notify_email or not user.email or user.email in seen:
            continue
        if allowed is not None and user.email not in allowed:
            continue
        seen.add(user.email)
        recipients.append(user.email)

    if recipients:
        try:
            send_mail(
                subject=subject,
                message=plain_message,
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "soporte@smarthydro.cl"),
                recipient_list=sorted(recipients),
                html_message=html_message,
                fail_silently=True,
            )
            logger.info(
                f"Estado Ticket #{ticket.id}: {old_status} → {new_status}, "
                f"correo a {', '.join(sorted(recipients))}"
            )
        except Exception as e:
            logger.error(f"Error enviando cambio de estado Ticket #{ticket.id}: {e}")

    return recipients


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
