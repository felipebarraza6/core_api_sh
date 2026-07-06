"""Check subscriptions and send notifications manually."""
from django.core.management.base import BaseCommand

from void.services import SubscriptionService


class Command(BaseCommand):
    help = "Revisa contratos próximos a vencer y facturas vencidas, y envía notificaciones"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Crear notificaciones pero no enviar emails.",
        )
        parser.add_argument(
            "--date",
            type=str,
            help="Fecha de referencia YYYY-MM-DD (default: hoy).",
        )

    def handle(self, *args, **options):
        from datetime import datetime

        dry_run = options["dry_run"]
        date_str = options["date"]

        if date_str:
            today = datetime.strptime(date_str, "%Y-%m-%d").date()
        else:
            from django.utils import timezone
            today = timezone.now().date()

        service = SubscriptionService(today=today)
        contract_notifications = service.check_contracts()
        invoice_notifications = service.check_invoices()

        self.stdout.write(
            self.style.NOTICE(
                f"Fecha de referencia: {today}\n"
                f"Recordatorios de contrato: {len(contract_notifications)}\n"
                f"Facturas vencidas: {len(invoice_notifications)}"
            )
        )

        for n in contract_notifications + invoice_notifications:
            self.stdout.write(
                f"  [{n.category}] {n.recipient_email} — {n.subject}"
            )

        if not dry_run:
            from void.tasks import _send_notification_email
            sent = 0
            failed = 0
            for notification in contract_notifications + invoice_notifications:
                try:
                    _send_notification_email(notification)
                    notification.status = "sent"
                    notification.sent_at = __import__("django.utils.timezone", fromlist=["timezone"]).timezone.now()
                    if notification.contract and notification.category == "subscription_reminder":
                        service.mark_contract_reminder_sent(notification.contract, sent_at=notification.sent_at)
                    sent += 1
                except Exception as exc:
                    notification.status = "failed"
                    notification.error_message = str(exc)
                    failed += 1
                notification.save(update_fields=["status", "sent_at", "error_message"])

            self.stdout.write(
                self.style.SUCCESS(f"Enviadas: {sent}, Fallidas: {failed}")
            )
        else:
            self.stdout.write(self.style.WARNING("Dry-run: notificaciones creadas pero no enviadas."))
