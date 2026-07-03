"""
Comando para notificar tickets con SLA vencido.

Envía un email a los operadores de la categoría y al usuario asignado cuando:
- Se venció el deadline de primera respuesta y aún no respondió.
- Se venció el deadline de resolución y el ticket sigue abierto.

Se ejecuta vía cron cada hora.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.html import strip_tags

from api.core.models.tickets import SupportTicket

logger = logging.getLogger(__name__)


OPEN_STATUSES = {
    "ABIERTO",
    "EN_ANALISIS",
    "ESPERA_CLIENTE",
    "ESPERA_PROVEEDOR",
}


class Command(BaseCommand):
    help = "Notifica tickets con SLA de respuesta o resolución vencido"

    def handle(self, *args, **options):
        now = timezone.now()
        # Notificar máximo una vez al día por ticket
        min_last_notification = now - timedelta(hours=23)

        qs = SupportTicket.objects.filter(
            status__in=OPEN_STATUSES,
            is_active=True,
        ).filter(
            Q(sla_deadline_response__lt=now, sla_responded_at__isnull=True)
            | Q(sla_deadline_resolution__lt=now)
        ).filter(
            Q(sla_last_overdue_notification__isnull=True)
            | Q(sla_last_overdue_notification__lt=min_last_notification)
        ).select_related("category", "assigned_to").prefetch_related("category__operators", "points")

        notified_count = 0
        for ticket in qs.iterator():
            if self._notify(ticket, now):
                notified_count += 1

        self.stdout.write(self.style.SUCCESS(f"Notificaciones enviadas: {notified_count}"))

    def _notify(self, ticket, now):
        category = ticket.category
        operators = set()
        if category:
            operators.update(
                category.operators.filter(is_active=True, email__isnull=False)
                .exclude(email="")
                .values_list("email", flat=True)
            )
        if ticket.assigned_to and ticket.assigned_to.email:
            operators.add(ticket.assigned_to.email)

        # Modo prueba: limitar destinatarios a lista configurada
        test_only = getattr(settings, "SLA_OVERDUE_TEST_ONLY", None)
        if test_only:
            allowed = set(test_only)
            operators = operators & allowed
            if not operators:
                return False

        if not operators:
            return False

        point = ticket.points.first()
        client_name = (
            point.project.client.name
            if point and point.project and point.project.client
            else "N/A"
        )
        point_name = point.title if point else "N/A"

        now_str = now.strftime("%d/%m/%Y %H:%M")

        vencidos = []
        if ticket.sla_deadline_response and ticket.sla_deadline_response < now and not ticket.sla_responded_at:
            vencido = ticket.sla_deadline_response.strftime("%d/%m/%Y %H:%M")
            vencidos.append(f"- Primera respuesta: venció el {vencido}")
        if ticket.sla_deadline_resolution and ticket.sla_deadline_resolution < now:
            vencido = ticket.sla_deadline_resolution.strftime("%d/%m/%Y %H:%M")
            vencidos.append(f"- Resolución: venció el {vencido}")

        if not vencidos:
            return False

        context = {
            "ticket_id": ticket.id,
            "title": ticket.title,
            "client_name": client_name,
            "point_name": point_name,
            "category": str(category) if category else "N/A",
            "priority": ticket.priority,
            "priority_display": ticket.get_priority_display(),
            "status": ticket.status,
            "status_display": ticket.get_status_display(),
            "assigned_to_name": ticket.assigned_to.get_full_name() if ticket.assigned_to else "Sin asignar",
            "overdue_items": vencidos,
        }

        html_message = render_to_string("tickets/ticket_sla_overdue.html", context)
        plain_message = strip_tags(html_message)
        subject = f"[SLA VENCIDO] Ticket #{ticket.id}: {ticket.title}"

        try:
            send_mail(
                subject=subject,
                message=plain_message,
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "soporte@smarthydro.cl"),
                recipient_list=sorted(operators),
                html_message=html_message,
                fail_silently=True,
            )
            ticket.sla_last_overdue_notification = now
            ticket.save(update_fields=["sla_last_overdue_notification"])
            logger.info(f"Notificación SLA vencido enviada para ticket #{ticket.id}")
            return True
        except Exception as e:
            logger.error(f"Error notificando SLA vencido ticket #{ticket.id}: {e}")
            return False
