"""
Comando para limpiar tickets internos inactivos.

Cancela tickets con origen interno que nunca fueron atendidos
(sin asignado, sin comentarios, sin adjuntos) y tienen más de 90 días.

Se ejecuta vía cron una vez al día.
"""

import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from api.core.models.tickets import SupportTicket

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Cancela tickets internos inactivos con más de 90 días"

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=90,
            help="Antigüedad mínima en días para considerar un ticket como stale (default: 90)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Solo muestra cuántos tickets se cancelarían sin aplicar cambios",
        )

    def handle(self, *args, **options):
        days = options["days"]
        dry_run = options["dry_run"]

        if days <= 0:
            self.stdout.write(
                self.style.ERROR("--days debe ser un número positivo.")
            )
            return

        cutoff = timezone.now() - timedelta(days=days)

        qs = SupportTicket.objects.filter(
            origin="INTERNO",
            status="ABIERTO",
            is_active=True,
            assigned_to__isnull=True,
            created__lt=cutoff,
        ).filter(
            # Sin comentarios ni adjuntos
            Q(comments__isnull=True),
            Q(attachments__isnull=True),
        ).distinct()

        count = qs.count()

        if dry_run:
            self.stdout.write(
                self.style.WARNING(f"[DRY-RUN] Se cancelarían {count} tickets internos inactivos.")
            )
            return

        # No seteamos closed_at porque CANCELADO no es CERRADO y el modelo
        # lo valida en clean().
        cancelled = qs.update(
            status="CANCELADO",
            is_active=False,
        )

        self.stdout.write(
            self.style.SUCCESS(f"Tickets internos inactivos cancelados: {cancelled}")
        )
        logger.info(f"cleanup_stale_internal_tickets: cancelados {cancelled} tickets")
