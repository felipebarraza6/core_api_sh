"""
Tests del digest diario de notificaciones de tickets.

Cubre las 4 garantías del módulo `api.core.notifications.digest`:
1. No se pierde una notificación (fallback al envío en caliente).
2. Misma política de destinatarios que el orquestador.
3. Estado en cache, sin migraciones.
4. `NOTIFICATIONS_DRY_RUN` corta encolado y envío.
"""

from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings

from api.core.models import Client, ProjectCatchments, CatchmentPoint, SupportTicket
from api.core.notifications import digest

User = get_user_model()

LOC_MEM_CACHE = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
}


@override_settings(CACHES=LOC_MEM_CACHE)
class DigestQueueTests(TestCase):
    """Encolado: qué se guarda y qué devuelve."""

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.owner = User.objects.create_user(
            email="digestowner@smarthydro.cl", password="pass", username="digestowner"
        )

    def test_queue_returns_true_and_stores_index(self):
        from django.core.cache import cache
        ok = digest.queue(
            emails=[self.owner.email],
            subject="Ticket #1 cambió a Resuelto",
            summary="Ana marcó el ticket como Resuelto",
            link="/tickets/1",
        )
        self.assertTrue(ok)
        date_key = digest.timezone.localdate().isoformat()
        self.assertIn(
            self.owner.email.lower(),
            cache.get(digest._index_key(date_key)) or [],
        )

    def test_queue_returns_false_without_emails(self):
        self.assertFalse(digest.queue(emails=[], subject="x", summary="y"))
        self.assertFalse(digest.queue(emails=None, subject="x", summary="y"))

    def test_queue_returns_false_on_dry_run(self):
        """Dry-run → False, para que el llamador siga por notify()."""
        with override_settings(NOTIFICATIONS_DRY_RUN=True):
            self.assertFalse(
                digest.queue(
                    emails=[self.owner.email], subject="x", summary="y"
                )
            )

    def test_queue_returns_false_when_index_unreadable(self):
        """
        Garantía 1: si no puede confirmar el índice, devuelve False y el
        llamador envía en caliente (no se pierde nada).
        """
        with mock.patch.object(digest, "cache") as fake:
            fake.get.return_value = None  # índice ilegible tras el set
            fake.set.return_value = None
            self.assertFalse(
                digest.queue(
                    emails=[self.owner.email], subject="x", summary="y"
                )
            )

    def test_queue_returns_false_when_cache_raises(self):
        with mock.patch.object(digest, "cache") as fake:
            fake.get.side_effect = RuntimeError("redis caído")
            self.assertFalse(
                digest.queue(
                    emails=[self.owner.email], subject="x", summary="y"
                )
            )


@override_settings(CACHES=LOC_MEM_CACHE)
class DigestFlushTests(TestCase):
    """Envío: agrupación, opt-out y limpieza."""

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        mail.outbox = []
        self.a = User.objects.create_user(
            email="flusha@smarthydro.cl", password="pass", username="flusha"
        )
        self.b = User.objects.create_user(
            email="flushb@smarthydro.cl", password="pass", username="flushb"
        )

    def _queue(self, emails, subject):
        return digest.queue(
            emails=emails, subject=subject, summary=f"Detalle de {subject}",
            link="/tickets/1",
        )

    def test_flush_with_nothing_queued_sends_nothing(self):
        mail.outbox = []
        self.assertEqual(digest.flush(), 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_flush_groups_identical_recipients_into_one_email(self):
        """Dos encolados del día con los mismos destinatarios → 1 correo."""
        self._queue([self.a.email, self.b.email], "Ticket #1 cambió a Resuelto")
        self._queue([self.a.email, self.b.email], "Ticket #2 cambió a Abierto")
        mail.outbox = []

        self.assertEqual(digest.flush(), 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            set(mail.outbox[0].to), {self.a.email, self.b.email}
        )
        self.assertIn("Resumen de tickets", mail.outbox[0].subject)
        self.assertIn("2 novedades", mail.outbox[0].subject)
        # Ambas novedades viajan en el mismo cuerpo.
        self.assertIn("Ticket #1 cambió a Resuelto", mail.outbox[0].body)
        self.assertIn("Ticket #2 cambió a Abierto", mail.outbox[0].body)

    def test_flush_separates_groups_with_different_recipients(self):
        self._queue([self.a.email], "Ticket #1 cambió a Resuelto")
        self._queue([self.b.email], "Ticket #2 cambió a Abierto")
        mail.outbox = []

        self.assertEqual(digest.flush(), 2)
        self.assertEqual(len(mail.outbox), 2)

    def test_flush_respects_opt_out_after_queue(self):
        self._queue([self.a.email, self.b.email], "Ticket #1 cambió a Resuelto")
        self.a.notify_email = False
        self.a.save()
        mail.outbox = []

        self.assertEqual(digest.flush(), 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertNotIn(self.a.email, mail.outbox[0].to)
        self.assertIn(self.b.email, mail.outbox[0].to)

    def test_flush_clears_pending_state(self):
        self._queue([self.a.email], "Ticket #1 cambió a Resuelto")
        mail.outbox = []
        self.assertEqual(digest.flush(), 1)
        # Un segundo flush no reenvía el mismo resumen.
        self.assertEqual(digest.flush(), 0)
        self.assertEqual(len(mail.outbox), 1)

    def test_flush_dry_run_sends_nothing(self):
        self._queue([self.a.email], "Ticket #1 cambió a Resuelto")
        mail.outbox = []
        with override_settings(NOTIFICATIONS_DRY_RUN=True):
            self.assertEqual(digest.flush(), 0)
        self.assertEqual(len(mail.outbox), 0)


@override_settings(CACHES=LOC_MEM_CACHE)
class SendOrQueueTests(TestCase):
    """El punto de entrada que usan los signals de tickets."""

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        mail.outbox = []
        self.client_obj = Client.objects.create(name="Cliente Digest")
        self.project = ProjectCatchments.objects.create(
            name="Proyecto Digest", client=self.client_obj
        )
        self.owner = User.objects.create_user(
            email="digestpoint@smarthydro.cl", password="pass",
            username="digestpoint",
        )
        self.point = CatchmentPoint.objects.create(
            title="Punto Digest", project=self.project, owner_user=self.owner
        )
        self.staff = User.objects.create_user(
            email="sendorqueue@smarthydro.cl", password="pass",
            username="sendorqueue", is_staff=True,
        )
        self.ticket = SupportTicket.objects.create(
            title="Ticket digest", description="...",
            origin="CLIENTE", source="APP_CLIENTE",
            created_by=self.staff,
        )

    def _call(self, **kwargs):
        defaults = dict(
            users=[self.staff],
            ticket=self.ticket,
            subject="Ticket #1 cambió a Resuelto",
            message="cuerpo plano",
            html_message="<p>cuerpo</p>",
            summary="Ana marcó el ticket como Resuelto",
            link="/tickets/1",
        )
        defaults.update(kwargs)
        return digest.send_or_queue(**defaults)

    def test_queues_instead_of_sending(self):
        self.assertTrue(self._call())
        # Nada salió en caliente: quedó para el resumen diario.
        self.assertEqual(len(mail.outbox), 0)

        mail.outbox = []
        self.assertEqual(digest.flush(), 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.staff.email, mail.outbox[0].to)

    def test_falls_back_to_hot_send_when_cache_unavailable(self):
        """Garantía 1: si el digest no puede encolar, se envía igual."""
        with mock.patch.object(digest, "queue", return_value=False):
            self.assertTrue(self._call())
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.staff.email, mail.outbox[0].to)
        # El correo mantiene el formato previo (asunto en caliente).
        self.assertEqual(mail.outbox[0].subject, "Ticket #1 cambió a Resuelto")

    def test_skips_filtered_recipients(self):
        """Política del orquestador: notify_email=False no se encola."""
        self.staff.notify_email = False
        self.staff.save()
        self.assertFalse(self._call())
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(digest.flush(), 0)

    def test_dedup_key_blocks_second_call(self):
        self.assertTrue(self._call(dedup_key="ticket:1:status:RESUELTO"))
        self.assertTrue(self._call(dedup_key="ticket:1:status:RESUELTO"))
        mail.outbox = []
        self.assertEqual(digest.flush(), 1)
        self.assertEqual(len(mail.outbox), 1)
        # Solo el primer evento quedó encolado.
        self.assertEqual(mail.outbox[0].body.count("Ticket #1 cambió"), 1)
