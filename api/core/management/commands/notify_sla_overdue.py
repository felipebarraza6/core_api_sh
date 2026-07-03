"""
Comando para notificar tickets con SLA vencido.

Envía un email a los operadores de la categoría y al usuario asignado cuando:
- Se venció el deadline de primera respuesta y aún no respondió.
- Se venció el deadline de resolución, el ticket sigue abierto y no está resuelto.

Se ejecuta vía cron cada hora.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.db import transaction
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
    "EN_ORDEN_TRABAJO",
}


class Command(BaseCommand):
    help = "Notifica tickets con SLA de respuesta o resolución vencido"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Solo muestra cuántas notificaciones se enviarían sin enviar emails ni actualizar timestamps",
        )

    def handle(self, *args, **options):
        now = timezone.now()
        dry_run = options["dry_run"]
        # Notificar máximo una vez al día por ticket
        min_last_notification = now - timedelta(hours=23)

        qs = SupportTicket.objects.filter(
            status__in=OPEN_STATUSES,
            is_active=True,
        ).filter(
            Q(sla_deadline_response__lt=now, sla_responded_at__isnull=True)
            | Q(sla_deadline_resolution__lt=now, sla_resolved_at__isnull=True)
        ).filter(
            Q(sla_last_overdue_notification__isnull=True)
            | Q(sla_last_overdue_notification__lt=min_last_notification)
        ).select_related("category", "assigned_to", "sla_config").prefetch_related(
            "category__operators", "points"
        ).order_by("id")

        notified_count = 0
        # select_for_update requiere transacción atómica; evita race conditions
        # si el cron se solapa.
        with transaction.atomic():
            for ticket in qs:
                # Re-evaluar condiciones tras bloquear la fila.
                # select_for_update no es compatible con prefetch_related sobre
                # relaciones nullable, por lo que se carga sin prefetch y la
                # notificación accede a las relaciones por separado.
                # Bloqueamos solo la fila de SupportTicket. Las relaciones se
                # cargan bajo demanda en _notify para evitar LEFT OUTER JOINs
                # incompatibles con FOR UPDATE en PostgreSQL.
                ticket = (
                    SupportTicket.objects.select_for_update(of=("self",))
                    .get(pk=ticket.pk)
                )

                if not self._should_notify(ticket, now, min_last_notification):
                    continue

                if dry_run:
                    notified_count += 1
                    continue

                if self._notify(ticket, now):
                    notified_count += 1

        action = "[DRY-RUN] Notificaciones que se enviarían" if dry_run else "Notificaciones enviadas"
        self.stdout.write(self.style.SUCCESS(f"{action}: {notified_count}"))

    def _should_notify(self, ticket, now, min_last_notification):
        """Re-evalúa si el ticket sigue cumpliendo las condiciones de notificación."""
        if ticket.status not in OPEN_STATUSES or not ticket.is_active:
            return False
        if ticket.sla_last_overdue_notification and ticket.sla_last_overdue_notification >= min_last_notification:
            return False

        response_overdue = (
            ticket.sla_deadline_response
            and ticket.sla_deadline_response < now
            and ticket.sla_responded_at is None
        )
        resolution_overdue = (
            ticket.sla_deadline_resolution
            and ticket.sla_deadline_resolution < now
            and ticket.sla_resolved_at is None
        )
        return response_overdue or resolution_overdue

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

        # Escalamiento: usuario configurado en la SLA aplica
        escalation_user = (
            ticket.sla_config.escalation_user
            if ticket.sla_config and ticket.sla_config.escalation_user
            else None
        )
        if escalation_user and escalation_user.email:
            operators.add(escalation_user.email)

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
        if ticket.sla_deadline_resolution and ticket.sla_deadline_resolution < now and not ticket.sla_resolved_at:
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
            "now_str": now_str,
        }

        html_message = render_to_string("tickets/ticket_sla_overdue.html", context)
        plain_message = strip_tags(html_message)
        subject = f"[SLA VENCIDO] Ticket #{ticket.id}: {ticket.title}"

        try:
            sent = send_mail(
                subject=subject,
                message=plain_message,
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "soporte@smarthydro.cl"),
                recipient_list=sorted(operators),
                html_message=html_message,
                fail_silently=True,
            )
            if sent == 0:
                logger.warning(f"No se pudo enviar notificación SLA para ticket #{ticket.id}")
                return False

            ticket.sla_last_overdue_notification = now
            ticket.save(update_fields=["sla_last_overdue_notification"])
            logger.info(f"Notificación SLA vencido enviada para ticket #{ticket.id}")
            return True
        except Exception as e:
            logger.error(f"Error notificando SLA vencido ticket #{ticket.id}: {e}")
            return False
