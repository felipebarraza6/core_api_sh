"""
Señales de notificación push e in-app.

⚠️  DISEÑO DEFENSIVO — leer antes de tocar:

1. Cada receiver está envuelto en su propio `try/except Exception`. Un fallo
   aquí NUNCA puede romper la creación del ticket / comentario / alerta.
2. El envío de push corre en un hilo aparte (`threading.Thread`), igual que el
   patrón ya usado en `signals/notifications.py`, para no bloquear requests
   de la API ni el cron del motor de alertas.
3. Ninguna señal escribe en `AlertTrigger.notification_sent` ni en campos del
   dispatcher: el envío a Google Chat / webhook / correo sigue siendo
   responsabilidad exclusiva de `alert_dispatcher.py` y no cambia.
4. Todo es aditivo: no se modifica ningún comportamiento existente, sólo se
   agregan filas nuevas en `TicketNotification` y envíos push.
"""

import logging
import threading

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)

# Máximo de destinatarios por broadcast de aviso general. Tope de seguridad
# para que una creación masiva de usuarios no dispare miles de envíos.
MAX_BROADCAST_RECIPIENTS = 1000

# Emojis por severidad (consistente con el estilo de signals/notifications.py).
_SEVERITY_EMOJI = {
    "CRITICAL": "🔴",
    "WARNING": "⚠️",
    "ALERT": "🚨",
    "INFO": "ℹ️",
}


def _spawn(fn, *args, **kwargs):
    """
    Ejecuta `fn` en un hilo demonio. Nunca lanza hacia afuera.

    En tests (`settings.TESTING`) se ejecuta de forma síncrona para que los
    asserts sean deterministas; en producción siempre va en hilo para no
    bloquear requests de la API ni el cron del motor de alertas.
    """
    try:
        from django.conf import settings
        if getattr(settings, "TESTING", False):
            fn(*args, **kwargs)
            return
        thread = threading.Thread(target=fn, args=args, kwargs=kwargs, daemon=True)
        thread.start()
    except Exception as exc:  # pragma: no cover - defensa
        logger.warning("No se pudo lanzar hilo de notificación push: %s", exc)


# ============================================================================
# ALERTAS DE TELEMETRÍA  →  push al dueño y a los visores del punto
# ============================================================================

def _alert_recipients(point):
    """
    Destinatarios de una alerta (decisión operativa 2026-10):
    el `owner_user` del punto + sus `users_viewers`, **excluyendo** personal
    (staff/superuser): el equipo de operaciones ya recibe estas alertas por
    Google Chat.
    """
    users = []
    seen = set()

    def _add(user):
        if user is None or not user.is_active:
            return
        if user.is_staff or user.is_superuser:
            return
        if user.id in seen:
            return
        seen.add(user.id)
        users.append(user)

    _add(point.owner_user)
    for viewer in point.users_viewers.all():
        _add(viewer)
    return users


@receiver(post_save, sender="core.AlertTrigger")
def push_new_alert_trigger(sender, instance, created, **kwargs):
    """
    Push al INSTANTE de que el motor de alertas crea un `AlertTrigger`.

    Se purposely NO toca `alert_dispatcher.py`: el dispatcher sigue
    encargado de Chat/webhook/correo, y el push corre en paralelo.
    """
    if not created:
        return

    try:
        from api.core.models import AlertTrigger
        from api.core.utils.webpush import (
            CATEGORY_ALERTS,
            push_available,
            send_webpush_to_users,
        )

        trigger = (
            AlertTrigger.objects.select_related(
                "alert_rule", "alert_rule__point_catchment", "point_catchment"
            ).get(id=instance.id)
        )

        rule = trigger.alert_rule
        if rule is None:
            return

        point = trigger.point_catchment or rule.point_catchment
        if point is None:
            return

        severity = (rule.severity or "WARNING").upper()
        if severity == "INFO":
            return

        if not push_available():
            return

        users = _alert_recipients(point)
        if not users:
            return

        emoji = _SEVERITY_EMOJI.get(severity, "🚨")
        title = f"{emoji} {rule.name}"
        parts = [f"Punto: {point.title}"]
        if trigger.value_at_trigger is not None:
            parts.append(f"Valor: {trigger.value_at_trigger}")
        if trigger.threshold_breached is not None:
            parts.append(f"Umbral: {trigger.threshold_breached}")
        body = " · ".join(parts)
        url = f"/alerts/{trigger.id}"

        def _send():
            try:
                send_webpush_to_users(
                    users, title=title, body=body, url=url,
                    category=CATEGORY_ALERTS,
                )
            except Exception as exc:  # pragma: no cover - defensa
                logger.warning("Push de alerta falló (trigger=%s): %s", trigger.id, exc)

        _spawn(_send)

    except Exception as exc:  # pragma: no cover - defensa
        logger.error("push_new_alert_trigger falló: %s", exc, exc_info=True)


# ============================================================================
# TICKETS  →  notificación in-app + push
# ============================================================================

def _ticket_recipients_for_comment(ticket, comment, author):
    """
    Quién debe enterarse de una respuesta en el ticket.

    Se excluye al autor y a los usuarios mencionados (@usuario) en el
    contenido: esos ya reciben una notificación MENTION por separado, así que
    incluirlos aquí produciría un duplicado.
    Los comentarios internos (`is_internal=True`) no generan notificación:
    no son visibles para el cliente.
    """
    from .tickets import _ticket_involved_users, _resolve_mentioned_users

    if comment.is_internal:
        return []

    mentioned_ids = {
        u.id for u in _resolve_mentioned_users(comment.content, ticket)
    }

    author_id = getattr(author, "id", None)
    recipients = []
    for user in _ticket_involved_users(ticket):
        if author_id is not None and user.id == author_id:
            continue
        if user.id in mentioned_ids:
            continue
        recipients.append(user)
    return recipients


@receiver(post_save, sender="core.TicketComment")
def notify_ticket_reply(sender, instance, created, **kwargs):
    """
    Cuando aparece una respuesta en un ticket → `TicketNotification(REPLY)`
    para los involucrados + push (si quieren tickets).
    """
    if not created:
        return

    try:
        from api.core.models import TicketNotification
        from api.core.utils.webpush import CATEGORY_TICKETS, send_webpush

        comment = instance
        ticket = comment.ticket
        author = comment.author

        if comment.is_internal:
            return

        recipients = _ticket_recipients_for_comment(ticket, comment, author)
        if not recipients:
            return

        author_name = (author.get_full_name() or author.email) if author else "Sistema"
        message = f"{author_name} respondió en el ticket #{ticket.id}: {ticket.title}"

        # Notificación in-app (síncrona: debe quedar visible al instante).
        for user in recipients:
            TicketNotification.objects.create(
                user=user,
                ticket=ticket,
                comment=comment,
                notification_type=TicketNotification.REPLY,
                message=message[:500],
            )

        # Push en hilo aparte.
        def _send():
            try:
                for user in recipients:
                    send_webpush(
                        user,
                        title=f"💬 Ticket #{ticket.id}",
                        body=message[:200],
                        url=f"/tickets/{ticket.id}",
                        category=CATEGORY_TICKETS,
                    )
            except Exception as exc:  # pragma: no cover - defensa
                logger.warning("Push de respuesta de ticket falló: %s", exc)

        _spawn(_send)

    except Exception as exc:  # pragma: no cover - defensa
        logger.error("notify_ticket_reply falló: %s", exc, exc_info=True)


# Estado anterior del ticket, capturado en pre_save para detectar cambios
# en post_save sin tener que tocar las vistas.
_PREVIOUS_STATUS = {}


@receiver(pre_save, sender="core.SupportTicket")
def _capture_previous_ticket_status(sender, instance, **kwargs):
    if instance.pk is None:
        return
    try:
        from api.core.models import SupportTicket
        old = (
            SupportTicket.objects.filter(pk=instance.pk)
            .values_list("status", flat=True)
            .first()
        )
        if old is not None:
            instance._prev_status_for_push = old
    except Exception:  # pragma: no cover - defensa
        pass


@receiver(post_save, sender="core.SupportTicket")
def notify_ticket_status_change(sender, instance, created, **kwargs):
    """
    Cuando cambia el estado de un ticket → `TicketNotification(STATUS_CHANGE)`
    para el creador (el cliente que espera la respuesta) + push.
    """
    if created:
        return

    try:
        from api.core.models import SupportTicket, TicketNotification
        from api.core.utils.webpush import CATEGORY_TICKETS, send_webpush

        old_status = getattr(instance, "_prev_status_for_push", None)
        new_status = instance.status
        if old_status is None or old_status == new_status:
            return

        recipient = instance.created_by
        if recipient is None or not recipient.is_active:
            return

        status_display = dict(SupportTicket.STATUS_CHOICES)
        message = (
            f"El ticket #{instance.id} cambió a "
            f"{status_display.get(new_status, new_status)}: {instance.title}"
        )

        TicketNotification.objects.create(
            user=recipient,
            ticket=instance,
            notification_type=TicketNotification.STATUS_CHANGE,
            message=message[:500],
        )

        def _send():
            try:
                send_webpush(
                    recipient,
                    title=f"🔄 Ticket #{instance.id}",
                    body=message[:200],
                    url=f"/tickets/{instance.id}",
                    category=CATEGORY_TICKETS,
                )
            except Exception as exc:  # pragma: no cover - defensa
                logger.warning("Push de cambio de estado falló: %s", exc)

        _spawn(_send)

    except Exception as exc:  # pragma: no cover - defensa
        logger.error("notify_ticket_status_change falló: %s", exc, exc_info=True)


# ============================================================================
# AVISOS GENERALES  →  push broadcast
# ============================================================================

@receiver(post_save, sender="core.NotificationsCatchment")
def push_broadcast_announcement(sender, instance, created, **kwargs):
    """
    Avisos globales (`NotificationsCatchment` SIN punto de captación) →
    push a todos los usuarios que tengan `push_announcements` activo.

    Las notificaciones que SÍ tienen punto (alertas legacy / soporte) no
    entran aquí: esas ya tienen su propio flujo.
    """
    if not created:
        return

    try:
        from api.core.models import User
        from api.core.utils.webpush import (
            CATEGORY_ANNOUNCEMENTS,
            push_available,
            send_webpush_to_users,
        )

        if instance.point_catchment_id is not None:
            return
        if not instance.is_active:
            return
        if not push_available():
            return

        users = list(
            User.objects.filter(
                is_active=True,
                is_staff=False,
                is_superuser=False,
                notify_push=True,
                push_announcements=True,
            )[:MAX_BROADCAST_RECIPIENTS]
        )
        if not users:
            return

        title = instance.title or "Aviso SmartHydro"
        body = instance.message or ""

        def _send():
            try:
                send_webpush_to_users(
                    users, title=title, body=body, url="/avisos",
                    category=CATEGORY_ANNOUNCEMENTS,
                )
            except Exception as exc:  # pragma: no cover - defensa
                logger.warning("Push de aviso falló: %s", exc)

        _spawn(_send)

    except Exception as exc:  # pragma: no cover - defensa
        logger.error("push_broadcast_announcement falló: %s", exc, exc_info=True)
