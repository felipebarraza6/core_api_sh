"""Subscription billing and notification service for void."""
import logging
from datetime import date, timedelta
from typing import List, Optional

from django.db import transaction
from django.utils import timezone

from void.models import (
    Client,
    Contract,
    Invoice,
    Notification,
    Subscription,
)

logger = logging.getLogger(__name__)


class SubscriptionService:
    """Servicio de gestión de suscripciones, recordatorios y facturas."""

    REMINDER_DAYS = [30, 15, 7, 3, 1]

    FREQUENCY_DELTAS = {
        "daily": timedelta(days=1),
        "every_3_days": timedelta(days=3),
        "weekly": timedelta(days=7),
    }

    def __init__(self, today: date = None, now: timezone.datetime = None):
        self.today = today or timezone.now().date()
        self.now = now or timezone.now()

    @transaction.atomic
    def check_contracts(self) -> List[Notification]:
        """Revisa contratos próximos a vencer y genera notificaciones.

        La frecuencia de repetición se controla por Contract.reminder_frequency.
        """
        notifications = []

        for days_before in self.REMINDER_DAYS:
            target_date = self.today + timedelta(days=days_before)
            contracts = Contract.objects.filter(
                status__in=("active", "pending"),
                end_date=target_date,
            ).select_related("client")

            for contract in contracts:
                if not self._should_send_contract_reminder(contract):
                    continue

                notification = self._create_contract_reminder(contract, days_before)
                notifications.append(notification)

        return notifications

    def _should_send_contract_reminder(self, contract: Contract) -> bool:
        """Determina si se debe enviar un recordatorio según frecuencia configurada."""
        if contract.reminder_frequency == "once":
            return contract.last_reminder_sent_at is None

        if contract.last_reminder_sent_at is None:
            return True

        delta = self.FREQUENCY_DELTAS.get(contract.reminder_frequency)
        if delta is None:
            return False

        return self.now - contract.last_reminder_sent_at >= delta

    @transaction.atomic
    def check_invoices(self) -> List[Notification]:
        """Revisa facturas vencidas y genera notificaciones.

        Por defecto se repite diariamente mientras la factura esté vencida.
        """
        notifications = []
        overdue_invoices = Invoice.objects.filter(
            status__in=("sent", "overdue"),
            due_date__lt=self.today,
        ).select_related("contract", "contract__client")

        for invoice in overdue_invoices:
            if invoice.status == "sent":
                invoice.status = "overdue"
                invoice.save(update_fields=["status"])

            reference_id = f"invoice:{invoice.id}:overdue:{self.today}"
            already_exists = Notification.objects.filter(
                reference_id=reference_id,
            ).exists()
            if already_exists:
                continue

            notification = self._create_invoice_overdue_notification(invoice, reference_id)
            notifications.append(notification)

        return notifications

    def _create_contract_reminder(self, contract: Contract, days_before: int) -> Notification:
        recipient = contract.client.billing_email or contract.client.contact_email
        if not recipient:
            recipient = ""

        return Notification.objects.create(
            recipient_email=recipient,
            recipient_name=contract.client.contact_name or contract.client.name,
            category="subscription_reminder",
            channel="email",
            subject=f"Recordatorio: contrato '{contract.name}' vence en {days_before} día(s)",
            body=(
                f"Estimado cliente,\n\n"
                f"El contrato '{contract.name}' de {contract.client.name} "
                f"vence el {contract.end_date}.\n"
                f"Monto: {contract.amount} {contract.currency}\n"
                f"Ciclo: {contract.get_billing_cycle_display()}\n"
                f"Frecuencia de aviso: {contract.get_reminder_frequency_display()}\n\n"
                f"Por favor contacte a su ejecutivo para renovación."
            ),
            contract=contract,
            client=contract.client,
        )

    def _create_invoice_overdue_notification(self, invoice: Invoice, reference_id: str = "") -> Notification:
        recipient = invoice.contract.client.billing_email or invoice.contract.client.contact_email
        if not recipient:
            recipient = ""

        return Notification.objects.create(
            recipient_email=recipient,
            recipient_name=invoice.contract.client.contact_name or invoice.contract.client.name,
            category="invoice_overdue",
            channel="email",
            subject=f"Factura vencida: {invoice.contract.name}",
            body=(
                f"Estimado cliente,\n\n"
                f"La factura del período {invoice.period_start} - {invoice.period_end} "
                f"se encuentra vencida desde el {invoice.due_date}.\n"
                f"Monto total: {invoice.total_amount} {invoice.contract.currency}\n\n"
                f"Favor regularizar el pago."
            ),
            contract=invoice.contract,
            client=invoice.contract.client,
            reference_id=reference_id,
        )

    @transaction.atomic
    def mark_contract_reminder_sent(
        self,
        contract: Contract,
        sent_at: Optional[timezone.datetime] = None,
    ) -> None:
        """Marca el contrato con la fecha del último recordatorio enviado."""
        contract.last_reminder_sent_at = sent_at or self.now
        contract.save(update_fields=["last_reminder_sent_at"])

    @transaction.atomic
    def create_invoice_for_contract(self, contract: Contract, period_start: date, period_end: date) -> Invoice:
        """Crea borrador de factura para un período de contrato."""
        due_date = period_end + timedelta(days=7)
        return Invoice.objects.create(
            contract=contract,
            period_start=period_start,
            period_end=period_end,
            due_date=due_date,
            amount=contract.amount,
            tax_amount=0,
            total_amount=contract.amount,
            status="draft",
        )

    @transaction.atomic
    def renew_contract(self, contract: Contract, new_end_date: date) -> Contract:
        """Renueva un contrato extendiendo su fecha de término."""
        contract.start_date = contract.end_date
        contract.end_date = new_end_date
        contract.status = "active"
        contract.last_reminder_sent_at = None
        contract.save(update_fields=["start_date", "end_date", "status", "last_reminder_sent_at"])
        return contract
