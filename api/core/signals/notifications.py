import logging
import threading
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver
from django.conf import settings
from django.core.mail import send_mail
from api.core.models.catchment_points import NotificationsCatchment
from api.core.utils.google_chat import send_google_chat_message

logger = logging.getLogger(__name__)


def send_async_notifications(instance_id):
    """
    Background worker to send chat and email notifications.
    """
    try:
        instance = NotificationsCatchment.objects.get(id=instance_id)

        # 1. Prepare Message for Google Chat
        client_name = "N/A"
        point_name = "N/A"
        owner_email = None
        if instance.point_catchment:
            point_name = instance.point_catchment.title
            if instance.point_catchment.project and instance.point_catchment.project.client:
                client_name = instance.point_catchment.project.client.name
            if instance.point_catchment.owner_user and instance.point_catchment.owner_user.email:
                owner_email = instance.point_catchment.owner_user.email

        chat_msg = (
            f"🎫 **NUEVO TICKET DE SOPORTE**\n\n"
            f"📌 **Título:** {instance.title}\n"
            f"🏢 **Cliente:** {client_name}\n"
            f"📍 **Punto:** {point_name}\n"
            f"🏷️ **Tipo:** {instance.get_type_notification_display()}\n"
            f"📝 **Mensaje:** {instance.message[:200]}{'...' if len(instance.message) > 200 else ''}\n"
            f"📅 **Fecha:** {instance.created.strftime('%d/%m/%Y %H:%M')}"
        )

        # 2. Send to Google Chat
        send_google_chat_message(chat_msg)

        # 3. Build recipient list for ticket email
        recipient_list = []

        # 3a. Emails configurados en la notificación (nuevo campo, prioridad)
        if instance.emails:
            import re
            EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
            for raw in instance.emails:
                raw = str(raw).strip() if raw else ''
                if raw and EMAIL_REGEX.match(raw):
                    recipient_list.append(raw)

        # 3b. Fallback: email del owner del punto (compatibilidad legacy)
        if not recipient_list and owner_email:
            recipient_list.append(owner_email)

        # 3c. Send email if we have recipients
        if recipient_list:
            subject = f"Nuevo Ticket de Soporte: {instance.title}"
            email_body = (
                f"Se ha creado un nuevo ticket en el sistema:\n\n"
                f"ID: {instance.id}\n"
                f"Título: {instance.title}\n"
                f"Cliente: {client_name}\n"
                f"Punto: {point_name}\n"
                f"Tipo: {instance.get_type_notification_display()}\n"
                f"Mensaje: {instance.message}\n\n"
                f"Fecha: {instance.created}\n"
                f"Link: https://api.smarthydro.app/admin/core/notificationscatchment/{instance.id}/change/"
            )

            send_mail(
                subject=subject,
                message=email_body,
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "soporte@smarthydro.cl"),
                recipient_list=recipient_list,
                fail_silently=True,
            )
            logger.info(f"Email de ticket enviado a {', '.join(recipient_list)}")

    except Exception as e:
        logger.error(f"Error in send_async_notifications: {e}")


@receiver(post_save, sender=NotificationsCatchment)
def notify_new_ticket(sender, instance, created, **kwargs):
    """
    Triggers background notification thread when a new ticket is created.
    """
    if not created:
        return

    # Use threading to avoid blocking the main request (prevent Timeouts in Admin)
    thread = threading.Thread(target=send_async_notifications, args=(instance.id,))
    thread.start()



@receiver(post_save, sender=NotificationsCatchment)
def sync_threshold_alert_to_new_system(sender, instance, created, **kwargs):
    """
    Sincroniza alertas umbral (ALERT + MAX/MIN/EQUALS) con AlertRule.
    Tickets de soporte (SUPPORT) y anuncios no se sincronizan.
    Se ejecuta automáticamente al crear o modificar desde Admin o API.
    """
    from api.core.views.alert_adapter import (
        is_threshold_alert,
        create_alert_rule_from_legacy,
        update_alert_rule_from_legacy,
    )

    if not is_threshold_alert(instance):
        return

    if created:
        create_alert_rule_from_legacy({}, instance)
    else:
        update_alert_rule_from_legacy(instance)


@receiver(pre_delete, sender=NotificationsCatchment)
def delete_threshold_alert_from_new_system(sender, instance, **kwargs):
    """
    Elimina la AlertRule vinculada cuando se borra una alerta umbral legacy.
    """
    from api.core.views.alert_adapter import is_threshold_alert, delete_alert_rule_by_legacy

    if is_threshold_alert(instance):
        delete_alert_rule_by_legacy(instance)
