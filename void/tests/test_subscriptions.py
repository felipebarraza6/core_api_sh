"""Tests for subscription, client and billing models."""
from datetime import date, timedelta

from django.test import TestCase
from django.utils import timezone

from void.models import (
    Client,
    Contract,
    Invoice,
    Notification,
    Point,
    Subscription,
    VoidUserProfile,
)
from void.services import SubscriptionService


class ClientModelTests(TestCase):
    def test_create_client(self):
        client = Client.objects.create(
            name="Cliente A",
            tax_id="76.123.456-7",
            contact_email="cliente@example.com",
            billing_email="facturacion@example.com",
        )
        self.assertEqual(str(client), "Cliente A")
        self.assertEqual(client.status, "active")


class ContractModelTests(TestCase):
    def setUp(self):
        self.client = Client.objects.create(name="Cliente A")

    def test_create_contract(self):
        contract = Contract.objects.create(
            client=self.client,
            name="Contrato Mensual",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            billing_cycle="monthly",
            amount=100000,
            currency="CLP",
            status="active",
        )
        self.assertEqual(contract.get_billing_cycle_display(), "Mensual")
        self.assertIn("Cliente A", str(contract))


class SubscriptionServiceTests(TestCase):
    def setUp(self):
        self.client = Client.objects.create(
            name="Cliente A",
            billing_email="facturacion@example.com",
        )
        self.contract = Contract.objects.create(
            client=self.client,
            name="Contrato",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 7, 15),
            billing_cycle="monthly",
            amount=100000,
            status="active",
        )
        self.point = Point.objects.create(name="Punto A")
        self.subscription = Subscription.objects.create(
            contract=self.contract,
            point=self.point,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 7, 15),
            status="active",
        )

    def test_check_contracts_creates_reminder(self):
        today = date(2026, 7, 8)  # 7 días antes del vencimiento
        service = SubscriptionService(today=today)
        notifications = service.check_contracts()

        self.assertEqual(len(notifications), 1)
        self.assertEqual(notifications[0].category, "subscription_reminder")
        self.assertEqual(notifications[0].recipient_email, "facturacion@example.com")
        self.assertIn("7 día(s)", notifications[0].subject)

    def test_check_contracts_respects_once_frequency(self):
        self.contract.reminder_frequency = "once"
        self.contract.save(update_fields=["reminder_frequency"])

        today = date(2026, 7, 8)
        service = SubscriptionService(today=today)
        service.check_contracts()
        service.mark_contract_reminder_sent(self.contract)
        notifications = service.check_contracts()

        self.assertEqual(len(notifications), 0)

    def test_check_contracts_repeats_daily(self):
        self.contract.reminder_frequency = "daily"
        self.contract.last_reminder_sent_at = timezone.now() - timedelta(days=2)
        self.contract.save(update_fields=["reminder_frequency", "last_reminder_sent_at"])

        today = date(2026, 7, 8)
        service = SubscriptionService(today=today)
        notifications = service.check_contracts()

        self.assertEqual(len(notifications), 1)

    def test_check_contracts_daily_skips_if_recent(self):
        self.contract.reminder_frequency = "daily"
        self.contract.last_reminder_sent_at = timezone.now() - timedelta(hours=6)
        self.contract.save(update_fields=["reminder_frequency", "last_reminder_sent_at"])

        today = date(2026, 7, 8)
        service = SubscriptionService(today=today)
        notifications = service.check_contracts()

        self.assertEqual(len(notifications), 0)

    def test_check_invoices_creates_overdue_notification(self):
        invoice = Invoice.objects.create(
            contract=self.contract,
            period_start=date(2026, 6, 1),
            period_end=date(2026, 6, 30),
            due_date=date(2026, 7, 1),
            amount=100000,
            total_amount=100000,
            status="sent",
        )
        today = date(2026, 7, 10)
        service = SubscriptionService(today=today)
        notifications = service.check_invoices()

        self.assertEqual(len(notifications), 1)
        self.assertEqual(notifications[0].category, "invoice_overdue")
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, "overdue")

    def test_create_invoice_for_contract(self):
        service = SubscriptionService()
        invoice = service.create_invoice_for_contract(
            self.contract,
            period_start=date(2026, 7, 1),
            period_end=date(2026, 7, 31),
        )
        self.assertEqual(invoice.status, "draft")
        self.assertEqual(invoice.amount, self.contract.amount)
        self.assertEqual(invoice.due_date, date(2026, 8, 7))
