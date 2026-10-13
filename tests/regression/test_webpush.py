"""
Tests de regresión para el subsistema de notificaciones push.

Cubren:
1. La utilidad de push es fail-open: sin claves / sin pywebpush / con
   preferencias apagadas no lanza excepciones y devuelve False.
2. Los endpoints de suscripción y preferencias.
3. Las señales: alertas (sólo dueño + visores, exigiendo staff), respuestas
   de tickets, cambios de estado y avisos broadcast.
4. Que las señales NO tocan los campos del dispatcher (notification_sent).
5. El feed unificado que consume la app.

Ningún test depende de `pywebpush` instalado: se simula su ausencia.
"""

from unittest import mock

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token

from api.core.models import (
    AlertRule,
    AlertTrigger,
    CatchmentPoint,
    Client,
    ProjectCatchments,
    SupportTicket,
    TicketCategory,
    TicketComment,
    TicketNotification,
    User,
    WebPushSubscription,
)
from api.core.utils import webpush as wp


def make_user(email, username=None, **kwargs):
    return User.objects.create_user(
        username=username or email.split("@")[0],
        email=email,
        password="testpass123",
        **kwargs,
    )


def make_point(owner, viewers=None, title="Punto Push"):
    client = Client.objects.create(name="Cliente Push")
    project = ProjectCatchments.objects.create(name="Proyecto Push", client=client)
    point = CatchmentPoint.objects.create(
        title=title,
        owner_user=owner,
        project=project,
        frecuency="60",
    )
    for viewer in viewers or []:
        point.users_viewers.add(viewer)
    return point


def make_subscription(user, endpoint="https://fcm.example.com/sub-1"):
    return WebPushSubscription.objects.create(
        user=user,
        endpoint=endpoint,
        p256dh="p256dh-key",
        auth="auth-key",
    )


# ============================================================================
# 1. UTILIDAD FAIL-OPEN
# ============================================================================

class WebPushUtilityTests(TestCase):
    """La utilidad nunca debe explotar, sin importar la configuración."""

    def setUp(self):
        self.user = make_user("push-util@example.com")
        make_subscription(self.user)

    @override_settings(PUSH_ENABLED=False, VAPID_PRIVATE_KEY="", VAPID_PUBLIC_KEY="")
    def test_push_disabled_by_default(self):
        """Sin PUSH_ENABLED ni claves, push_available() es False."""
        self.assertFalse(wp.push_available())

    @override_settings(PUSH_ENABLED=False, VAPID_PRIVATE_KEY="", VAPID_PUBLIC_KEY="")
    def test_send_webpush_returns_false_when_disabled(self):
        with mock.patch.object(wp, "send_webpush", wraps=wp.send_webpush):
            self.assertFalse(
                wp.send_webpush(self.user, title="hola", body="mundo")
            )

    def test_send_webpush_survives_missing_pywebpush(self):
        """Si pywebpush no está instalado, se omite el envío sin explotar."""
        with override_settings(
            PUSH_ENABLED=True,
            VAPID_PRIVATE_KEY="priv",
            VAPID_PUBLIC_KEY="pub",
        ):
            with mock.patch.object(wp, "_load_pywebpush", return_value=(None, None)):
                self.assertFalse(
                    wp.send_webpush(self.user, title="hola", body="mundo")
                )

    def test_send_webpush_survives_any_exception(self):
        """Una excepción inesperada interna no se propaga al llamador."""
        with override_settings(
            PUSH_ENABLED=True,
            VAPID_PRIVATE_KEY="priv",
            VAPID_PUBLIC_KEY="pub",
        ):
            fake_webpush = mock.Mock(side_effect=RuntimeError("boom"))
            with mock.patch.object(
                wp, "_load_pywebpush", return_value=(fake_webpush, Exception)
            ):
                self.assertFalse(
                    wp.send_webpush(self.user, title="hola", body="mundo")
                )

    def test_user_can_receive_push_respects_flags(self):
        self.assertTrue(wp.user_can_receive_push(self.user, wp.CATEGORY_ALERTS))

        self.user.notify_push = False
        self.user.save(update_fields=["notify_push"])
        self.assertFalse(wp.user_can_receive_push(self.user, wp.CATEGORY_ALERTS))

        self.user.notify_push = True
        self.user.push_alerts = False
        self.user.save(update_fields=["notify_push", "push_alerts"])
        self.assertFalse(wp.user_can_receive_push(self.user, wp.CATEGORY_ALERTS))
        self.assertTrue(wp.user_can_receive_push(self.user, wp.CATEGORY_TICKETS))

    def test_user_can_receive_push_rejects_inactive_user(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        self.assertFalse(wp.user_can_receive_push(self.user, wp.CATEGORY_ALERTS))

    def test_send_webpush_to_users_counts_only_eligible(self):
        other = make_user("push-util-other@example.com")
        stats = wp.send_webpush_to_users(
            [self.user, other], title="t", body="b", category=wp.CATEGORY_ALERTS
        )
        # Ninguno tiene PUSH_ENABLED: attempted cuenta sólo a los que quieren.
        self.assertEqual(stats["delivered"], 0)


# ============================================================================
# 2. ENDPOINTS
# ============================================================================

class PushAPITests(TestCase):

    def setUp(self):
        self.user = make_user("push-api@example.com")
        self.token = Token.objects.create(user=self.user)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

    def test_config_requires_auth(self):
        resp = APIClient().get("/api/ik/me/push/config/")
        self.assertEqual(resp.status_code, 401)

    @override_settings(PUSH_ENABLED=False, VAPID_PRIVATE_KEY="", VAPID_PUBLIC_KEY="")
    def test_config_reports_disabled_and_user_flags(self):
        resp = self.client.get("/api/ik/me/push/config/")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.data["enabled"])
        self.assertEqual(resp.data["user"]["notify_push"], True)
        self.assertEqual(resp.data["subscription_count"], 0)

    def test_subscribe_creates_subscription(self):
        payload = {
            "endpoint": "https://fcm.example.com/abc",
            "keys": {"p256dh": "k1", "auth": "k2"},
            "user_agent": "Chrome 129",
        }
        resp = self.client.post("/api/ik/me/push/subscribe/", payload, format="json")
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(resp.data["ok"])
        self.assertTrue(
            WebPushSubscription.objects.filter(
                user=self.user, endpoint="https://fcm.example.com/abc"
            ).exists()
        )

    def test_subscribe_is_idempotent_per_endpoint(self):
        payload = {"endpoint": "https://fcm.example.com/abc",
                   "keys": {"p256dh": "k1", "auth": "k2"}}
        self.client.post("/api/ik/me/push/subscribe/", payload, format="json")
        payload["keys"] = {"p256dh": "otra", "auth": "otra"}
        resp = self.client.post("/api/ik/me/push/subscribe/", payload, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            WebPushSubscription.objects.filter(user=self.user).count(), 1
        )

    def test_subscribe_rejects_insecure_endpoint(self):
        resp = self.client.post(
            "/api/ik/me/push/subscribe/",
            {"endpoint": "http://inseguro.example.com/x"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_subscribe_requires_keys_for_web_channel(self):
        resp = self.client.post(
            "/api/ik/me/push/subscribe/",
            {"endpoint": "https://fcm.example.com/x"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_unsubscribe_deletes_only_own(self):
        other = make_user("push-api-other@example.com")
        make_subscription(other, "https://fcm.example.com/other")
        make_subscription(self.user, "https://fcm.example.com/mine")

        resp = self.client.delete(
            "/api/ik/me/push/subscribe/",
            {"endpoint": "https://fcm.example.com/mine"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["deleted"], 1)
        self.assertFalse(
            WebPushSubscription.objects.filter(
                endpoint="https://fcm.example.com/mine"
            ).exists()
        )
        self.assertTrue(
            WebPushSubscription.objects.filter(
                endpoint="https://fcm.example.com/other"
            ).exists()
        )

    def test_preferences_get_and_post(self):
        resp = self.client.get("/api/ik/me/push/preferences/")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data["push_alerts"])

        resp = self.client.post(
            "/api/ik/me/push/preferences/",
            {"push_alerts": False, "notify_push": True},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.data["push_alerts"])

        self.user.refresh_from_db()
        self.assertFalse(self.user.push_alerts)

    def test_preferences_reject_non_boolean(self):
        resp = self.client.post(
            "/api/ik/me/push/preferences/", {"push_alerts": "si"}, format="json"
        )
        self.assertEqual(resp.status_code, 400)

    @override_settings(PUSH_ENABLED=False, VAPID_PRIVATE_KEY="", VAPID_PUBLIC_KEY="")
    def test_test_endpoint_reports_disabled_backend(self):
        """Con el backend apagado, el endpoint de prueba explica el motivo."""
        resp = self.client.post("/api/ik/me/push/test/", {}, format="json")
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.data["reason"], "push_deshabilitado_en_backend")


# ============================================================================
# 3. SEÑALES
# ============================================================================

class PushSignalAlertTests(TestCase):
    """El push de alertas va sólo a dueño + visores, excluyendo al staff."""

    def setUp(self):
        self.owner = make_user("alert-owner@example.com")
        self.viewer = make_user("alert-viewer@example.com")
        self.staff = make_user("alert-staff@example.com", is_staff=True)
        self.point = make_point(self.owner, viewers=[self.viewer, self.staff])
        self.rule = AlertRule.objects.create(
            name="Caudal alto",
            target_type="THRESHOLD_MAX",
            variable_type="CAUDAL",
            threshold_value=100,
            check_frequency_minutes=1,
            cooldown_minutes=0,
            point_catchment=self.point,
            severity="WARNING",
        )

    def _make_trigger(self, severity="WARNING"):
        self.rule.severity = severity
        self.rule.save(update_fields=["severity"])
        return AlertTrigger.objects.create(
            alert_rule=self.rule,
            triggered_at=timezone.now(),
            point_catchment=self.point,
        )

    @override_settings(PUSH_ENABLED=True, VAPID_PRIVATE_KEY="k", VAPID_PUBLIC_KEY="p")
    def test_alert_push_targets_owner_and_viewer_not_staff(self):
        with mock.patch.object(wp, "send_webpush_to_users") as mocked:
            self._make_trigger()
            self.assertEqual(mocked.call_count, 1)
            users = mocked.call_args[0][0]
            emails = {u.email for u in users}
            self.assertEqual(emails, {"alert-owner@example.com", "alert-viewer@example.com"})

    def test_alert_push_does_not_touch_dispatcher_fields(self):
        """La señal NO debe marcar notification_sent: eso es del dispatcher."""
        with mock.patch.object(wp, "send_webpush_to_users"):
            trigger = self._make_trigger()
            trigger.refresh_from_db()
            self.assertFalse(trigger.notification_sent)
            self.assertIsNone(trigger.notification_sent_at)
            self.assertFalse(trigger.is_acknowledged)

    def test_alert_push_skipped_for_info_severity(self):
        with mock.patch.object(wp, "send_webpush_to_users") as mocked:
            self._make_trigger(severity="INFO")
            mocked.assert_not_called()

    @override_settings(PUSH_ENABLED=False, VAPID_PRIVATE_KEY="", VAPID_PUBLIC_KEY="")
    def test_alert_push_disabled_when_backend_off(self):
        """Con PUSH_ENABLED=False la señal ni siquiera arma los destinatarios."""
        with mock.patch.object(wp, "send_webpush_to_users") as mocked:
            self._make_trigger()
            mocked.assert_not_called()


class PushSignalTicketTests(TestCase):
    """Respuestas y cambios de estado generan notificación in-app + push."""

    def setUp(self):
        self.client_user = make_user("ticket-client@example.com", username="clientepush")
        self.operator = make_user("ticket-operator@example.com", username="operadorpush")
        self.category = TicketCategory.objects.create(
            name="Categoría Push", notify_operators_on_create=True
        )
        self.category.operators.add(self.operator)
        self.point = make_point(self.client_user)
        self.ticket = SupportTicket.objects.create(
            title="Ticket de prueba push",
            category=self.category,
            status="NUEVO",
        )
        self.ticket.created_by = self.client_user
        self.ticket.assigned_to = self.operator
        self.ticket.save()
        self.ticket.points.add(self.point)

    def test_reply_creates_in_app_notification_for_others(self):
        comment = TicketComment.objects.create(
            ticket=self.ticket, author=self.operator, content="Respuesta del operador"
        )
        notes = TicketNotification.objects.filter(
            ticket=self.ticket, notification_type=TicketNotification.REPLY
        )
        self.assertEqual(notes.count(), 1)
        self.assertEqual(notes.first().user, self.client_user)
        self.assertEqual(notes.first().comment, comment)

    def test_reply_excludes_author(self):
        TicketComment.objects.create(
            ticket=self.ticket, author=self.client_user, content="Consulta"
        )
        self.assertFalse(
            TicketNotification.objects.filter(
                ticket=self.ticket, notification_type=TicketNotification.REPLY,
                user=self.client_user,
            ).exists()
        )

    def test_reply_skips_internal_notes(self):
        TicketComment.objects.create(
            ticket=self.ticket, author=self.operator,
            content="nota interna", is_internal=True,
        )
        self.assertFalse(
            TicketNotification.objects.filter(
                ticket=self.ticket, notification_type=TicketNotification.REPLY
            ).exists()
        )

    def test_reply_does_not_duplicate_mentions(self):
        """Si el usuario es mencionado (@usuario) no debe recibir además un REPLY."""
        comment = TicketComment.objects.create(
            ticket=self.ticket,
            author=self.operator,
            content="@clientepush revisa este dato por favor",
        )
        # El flujo real del endpoint también crea la MENTION:
        from api.core.signals.tickets import _notify_comment_mentions
        _notify_comment_mentions(comment, self.ticket, self.operator)

        mentions = TicketNotification.objects.filter(
            ticket=self.ticket, comment=comment,
            notification_type=TicketNotification.MENTION,
        )
        replies = TicketNotification.objects.filter(
            ticket=self.ticket, comment=comment,
            notification_type=TicketNotification.REPLY,
        )
        self.assertEqual(mentions.count(), 1)
        self.assertEqual(mentions.first().user, self.client_user)
        self.assertEqual(replies.count(), 0)

    def test_status_change_notifies_creator(self):
        self.ticket.status = "EN_ANALISIS"
        self.ticket.save()
        note = TicketNotification.objects.filter(
            ticket=self.ticket,
            notification_type=TicketNotification.STATUS_CHANGE,
        ).first()
        self.assertIsNotNone(note)
        self.assertEqual(note.user, self.client_user)
        # Usa el valor legible del estado, no la clave cruda.
        self.assertIn("En análisis", note.message)

    def test_status_unchanged_creates_nothing(self):
        self.ticket.save()  # sin cambio real de estado
        self.assertFalse(
            TicketNotification.objects.filter(
                ticket=self.ticket,
                notification_type=TicketNotification.STATUS_CHANGE,
            ).exists()
        )


# ============================================================================
# 4. FEED UNIFICADO
# ============================================================================

class MyNotificationsFeedTests(TestCase):

    def setUp(self):
        self.user = make_user("feed-user@example.com")
        self.token = Token.objects.create(user=self.user)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

        self.point = make_point(self.user)
        self.category = TicketCategory.objects.create(name="Cat Feed")
        self.ticket = SupportTicket.objects.create(
            title="Ticket feed", category=self.category, status="NUEVO"
        )
        self.ticket.created_by = self.user
        self.ticket.save()
        self.ticket.points.add(self.point)
        TicketNotification.objects.create(
            user=self.user,
            ticket=self.ticket,
            notification_type=TicketNotification.MENTION,
            message="te mencionaron",
        )

    def test_feed_requires_auth(self):
        resp = APIClient().get("/api/ik/me/notifications/")
        self.assertEqual(resp.status_code, 401)

    def test_feed_returns_items_and_unread_count(self):
        resp = self.client.get("/api/ik/me/notifications/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("results", resp.data)
        self.assertIn("unread_count", resp.data)
        self.assertGreaterEqual(len(resp.data["results"]), 1)
        self.assertEqual(resp.data["unread_count"]["tickets"], 1)
        self.assertEqual(resp.data["unread_count"]["total"], 1)

    def test_feed_source_filter_tickets(self):
        resp = self.client.get("/api/ik/me/notifications/?source=tickets")
        self.assertEqual(resp.status_code, 200)
        for item in resp.data["results"]:
            self.assertEqual(item["source"], "ticket")

    def test_feed_unread_only(self):
        resp = self.client.get("/api/ik/me/notifications/?unread_only=true")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data["results"]), 1)

    def test_feed_alerts_respect_point_access(self):
        """Sólo se ven alertas de puntos propios o visibles."""
        AlertTrigger.objects.create(
            alert_rule=AlertRule.objects.create(
                name="Regla ajena", target_type="THRESHOLD_MAX",
                variable_type="CAUDAL", threshold_value=1,
                check_frequency_minutes=1, cooldown_minutes=0,
            ),
            triggered_at=timezone.now(),
            point_catchment=make_point(make_user("otro-dueno@example.com")),
        )
        resp = self.client.get("/api/ik/me/notifications/?source=alerts")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data["results"]), 0)
