import logging
from datetime import datetime
from django.utils import timezone
from api.core.models.catchment_points import NotificationsCatchment
from api.core.utils.google_chat import send_google_chat_message

logger = logging.getLogger(__name__)

def run():
    """
    Daily Active Tickets Report:
    Sends a summary of all unread NotificationsCatchment (is_read=False) to Google Chat.
    """
    logger.info("Starting Daily Unread Tickets Report...")

    try:
        active_tickets = NotificationsCatchment.objects.filter(
            is_read=False
        ).select_related('point_catchment__project__client').order_by('-created')

        total_active = active_tickets.count()

        if total_active == 0:
            msg = "✅ **REPORTE DIARIO DE SOPORTE**\n\nNo hay tickets pendientes (sin leer)."
            send_google_chat_message(msg)
            logger.info("No unread tickets found. Summary sent.")
            return

        msg_parts = [f"📋 **REPORTE DIARIO DE TICKETS PENDIENTES ({total_active})**"]
        msg_parts.append(f"📅 Fecha: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
        msg_parts.append("")

        for ticket in active_tickets[:25]:  # Limit to 25 to avoid message length issues
            client_name = "N/A"
            point_name = "N/A"
            if ticket.point_catchment:
                point_name = ticket.point_catchment.title
                if ticket.point_catchment.project and ticket.point_catchment.project.client:
                    client_name = ticket.point_catchment.project.client.name

            emoji = "⚠️"
            if ticket.type_notification in ['CRITICAL', 'ALERT']:
                emoji = "🚨"

            msg_parts.append(
                f"{emoji} **{ticket.title}**\n"
                f"   🏢 Cliente: {client_name} | 📍 Punto: {point_name}\n"
                f"   ⏳ Creado: {ticket.created.strftime('%d/%m/%Y')}\n"
            )

        if total_active > 25:
            msg_parts.append(f"\n... y {total_active - 25} tickets más.")

        msg_parts.append("\n🔗 [Ver todos los tickets pendientes](https://api.smarthydro.app/admin/core/notificationscatchment/?is_read__exact=0)")

        full_msg = "\n".join(msg_parts)

        # Handle long messages
        if len(full_msg) > 4000:
            parts = [full_msg[i:i+4000] for i in range(0, len(full_msg), 4000)]
            for p in parts:
                send_google_chat_message(p)
        else:
            send_google_chat_message(full_msg)

        logger.info(f"Daily ticket report sent ({total_active} tickets).")

    except Exception as e:
        logger.error(f"Error in Daily Active Tickets Report: {e}", exc_info=True)
