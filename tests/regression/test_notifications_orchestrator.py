"""Tests del orquestador único de notificaciones (solo correo)."""

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings

from api.core.models import Client, ProjectCatchments, CatchmentPoint, SupportTicket, TicketCategory
from api.core.notifications import batch_notifications, is_client, notify

User = get_user_model()


class IsClientTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            email="isstaff@smarthydro.cl", password="pass", username="isstaff", is_staff=True
        )
        self.client_user = User.objects.create_user(
            email="isclient@smarthydro.cl", password="pass", username="isclient"
        )
        self.viewer = User.objects.create_user(
            email="isviewer@smarthydro.cl", password="pass", username="isviewer"
        )
        self.operator = User.objects.create_user(
            email="isoper@smarthydro.cl", password="pass", username="isoper"
        )
        self.stranger = User.objects.create_user(
            email="isstranger@smarthydro.cl", password="pass", username="isstranger"
        )
        client = Client.objects.create(name="Cliente IsClient")
        project = ProjectCatchments.objects.create(name="Proyecto IsClient", client=client)
        self.point = CatchmentPoint.objects.create(
            title="Punto IsClient", project=project, owner_user=self.client_user
        )
        self.point.users_viewers.add(self.viewer)
        self.cat = TicketCategory.objects.get(category_type="HARDWARE", name="Telemetría")
        self.cat.operators.add(self.operator)
        self.ticket = SupportTicket.objects.create(
            title="Ticket is_client",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
            category=self.cat,
        )
        self.ticket.points.add(self.point)

    def test_staff_is_not_client(self):
        self.assertFalse(is_client(self.staff, self.ticket))

    def test_category_operator_is_not_client(self):
        self.assertFalse(is_client(self.operator, self.ticket))

    def test_point_owner_is_client(self):
        self.assertTrue(is_client(self.client_user, self.ticket))

    def test_point_viewer_is_client(self):
        self.assertTrue(is_client(self.viewer, self.ticket))

    def test_stranger_is_not_client(self):
        self.assertFalse(is_client(self.stranger, self.ticket))


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    NOTIFY_CLIENTS=False,
    NOTIFY_CLIENTS_WHITELIST=[],
    NOTIFICATIONS_DRY_RUN=False,
    SLA_OVERDUE_TEST_ONLY=[],
)
class NotifyPolicyTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            email="nstaff@smarthydro.cl", password="pass", username="nstaff", is_staff=True
        )
        self.owner = User.objects.create_user(
            email="nowner@smarthydro.cl", password="pass", username="nowner"
        )
        self.muted = User.objects.create_user(
            email="nmuted@smarthydro.cl", password="pass", username="nmuted"
        )
        self.muted.notify_email = False
        self.muted.save(update_fields=["notify_email"])
        client = Client.objects.create(name="Cliente Notify")
        project = ProjectCatchments.objects.create(name="Proyecto Notify", client=client)
        point = CatchmentPoint.objects.create(
            title="Punto Notify", project=project, owner_user=self.owner
        )
        self.ticket = SupportTicket.objects.create(
            title="Ticket notify",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
        )
        self.ticket.points.add(point)

    def test_filters_client_when_flag_false(self):
        mail.outbox = []
        notify(
            subject="Hola",
            message="m",
            recipients=[self.owner, self.staff],
            ticket=self.ticket,
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.staff.email, mail.outbox[0].to)
        self.assertNotIn(self.owner.email, mail.outbox[0].to)

    def test_sends_to_client_when_flag_true(self):
        with override_settings(NOTIFY_CLIENTS=True):
            mail.outbox = []
            notify(
                subject="Hola clientes",
                message="m",
                recipients=[self.owner, self.staff],
                ticket=self.ticket,
            )
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.owner.email, mail.outbox[0].to)
        self.assertIn(self.staff.email, mail.outbox[0].to)

    def test_whitelist_allows_specific_client(self):
        with override_settings(NOTIFY_CLIENTS_WHITELIST=[self.owner.email]):
            mail.outbox = []
            notify(
                subject="Hola wl",
                message="m",
                recipients=[self.owner, self.staff],
                ticket=self.ticket,
            )
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.owner.email, mail.outbox[0].to)

    def test_respects_notify_email_false(self):
        mail.outbox = []
        notify(
            subject="Sin mute",
            message="m",
            recipients=[self.muted, self.staff],
            ticket=self.ticket,
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertNotIn(self.muted.email, mail.outbox[0].to)
        self.assertIn(self.staff.email, mail.outbox[0].to)

    def test_dry_run_sends_nothing(self):
        with override_settings(NOTIFICATIONS_DRY_RUN=True):
            mail.outbox = []
            notify(
                subject="Dry",
                message="m",
                recipients=[self.staff],
                ticket=self.ticket,
            )
        self.assertEqual(len(mail.outbox), 0)

    def test_sla_test_only_whitelist(self):
        with override_settings(SLA_OVERDUE_TEST_ONLY=["only@smarthydro.cl"]):
            mail.outbox = []
            notify(
                subject="SLA",
                message="m",
                recipients=[self.staff],
                ticket=self.ticket,
            )
        self.assertEqual(len(mail.outbox), 0)

    def test_dedup_key_blocks_second_send(self):
        mail.outbox = []
        notify(
            subject="Dedup",
            message="m",
            recipients=[self.staff],
            ticket=self.ticket,
            dedup_key="unique-key-1",
        )
        notify(
            subject="Dedup",
            message="m",
            recipients=[self.staff],
            ticket=self.ticket,
            dedup_key="unique-key-1",
        )
        self.assertEqual(len(mail.outbox), 1)

    def test_empty_recipients_no_email(self):
        mail.outbox = []
        notify(subject="Vacío", message="m", recipients=[], ticket=self.ticket)
        self.assertEqual(len(mail.outbox), 0)


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    NOTIFY_CLIENTS=False,
    NOTIFY_CLIENTS_WHITELIST=[],
    NOTIFICATIONS_DRY_RUN=False,
    SLA_OVERDUE_TEST_ONLY=[],
)
class BatchNotificationsTests(TestCase):
    def setUp(self):
        self.user_a = User.objects.create_user(
            email="batcha@smarthydro.cl", password="pass", username="batcha"
        )
        self.user_b = User.objects.create_user(
            email="batchb@smarthydro.cl", password="pass", username="batchb"
        )

    def test_batches_by_subject_and_merges_recipients(self):
        mail.outbox = []
        with batch_notifications():
            notify(subject="Mismo asunto", message="m", recipients=[self.user_a])
            notify(subject="Mismo asunto", message="m", recipients=[self.user_b])
            notify(subject="Otro asunto", message="m2", recipients=[self.user_a])
        self.assertEqual(len(mail.outbox), 2)
        subjects = sorted(m.subject for m in mail.outbox)
        self.assertEqual(subjects, ["Mismo asunto", "Otro asunto"])
        mismo = next(m for m in mail.outbox if m.subject == "Mismo asunto")
        self.assertEqual(set(mismo.to), {self.user_a.email, self.user_b.email})

    def test_flushes_even_on_exception(self):
        mail.outbox = []
        with self.assertRaises(RuntimeError):
            with batch_notifications():
                notify(subject="En batch", message="m", recipients=[self.user_a])
                raise RuntimeError("boom")
        self.assertEqual(len(mail.outbox), 1)

    def test_without_batch_sends_immediately(self):
        mail.outbox = []
        notify(subject="Inmediato", message="m", recipients=[self.user_a])
        self.assertEqual(len(mail.outbox), 1)
