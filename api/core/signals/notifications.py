import logging
import threading
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings
from django.core.mail import send_mail
from api.core.models.catchment_points import NotificationsCatchment
from api.core.utils.google_chat import send_google_chat_message

logger = logging.getLogger(__name__)

SUPPORT_EMAILS = ['sporte@smarthydro.cl', 'felipebarraza@smarthydro.cl']

def send_async_notifications(instance_id):
    """
    Background worker to send chat and email notifications.
    """
    try:
        instance = NotificationsCatchment.objects.get(id=instance_id)
        
        # 1. Prepare Message for Google Chat
        client_name = "N/A"
        point_name = "N/A"
        if instance.point_catchment:
            point_name = instance.point_catchment.title
            if instance.point_catchment.project and instance.point_catchment.project.client:
                client_name = instance.point_catchment.project.client.name

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

        # 3. Send Email (TEMPORARILY DISABLED DUE TO SMTP BLOCK)
        # We comment this out because even with fail_silently=True, 
        # it can cause delays or overhead until the connection times out.
        """
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
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=SUPPORT_EMAILS,
            fail_silently=True
        )
        """

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
