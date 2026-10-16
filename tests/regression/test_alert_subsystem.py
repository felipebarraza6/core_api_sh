"""
Tests de regresión para el subsistema de alertas.

Validan que:
1. AlertRule.clean() rechaza configuraciones inválidas
2. AlertChannel.clean() rechaza destinos inválidos
3. Los endpoints de API responden con estructura esperada
4. El motor no genera triggers para reglas con cooldown activo
"""

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core import mail
from django.test import TestCase, override_settings
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token

from api.core.models import (
    AlertRule, AlertChannel, AlertTrigger, SystemEvent,
    CatchmentPoint, User, InteractionDetail, ProjectCatchments, Client,
    ProfileDataConfigCatchment,
)

# El entorno de tests no tiene django-csp instalado; removemos el middleware para tests de API
TEST_MIDDLEWARE = [
    m for m in [
        "django.middleware.security.SecurityMiddleware",
        "whitenoise.middleware.WhiteNoiseMiddleware",
        # "csp.middleware.CSPMiddleware",
        "django.middleware.gzip.GZipMiddleware",
        "django.contrib.sessions.middleware.SessionMiddleware",
        "corsheaders.middleware.CorsMiddleware",
        "django.middleware.common.CommonMiddleware",
        "django.middleware.csrf.CsrfViewMiddleware",
        "django.contrib.auth.middleware.AuthenticationMiddleware",
        "django.contrib.messages.middleware.MessageMiddleware",
        "django.middleware.clickjacking.XFrameOptionsMiddleware",
    ]
]


class AlertRuleValidationTests(TestCase):
    """Validaciones de integridad en AlertRule.clean()."""

    def test_threshold_max_requires_variable(self):
        rule = AlertRule(
            name="Test", target_type="THRESHOLD_MAX",
            threshold_value=Decimal("10"),
        )
        with self.assertRaises(ValidationError) as ctx:
            rule.clean()
        self.assertIn("variable_type", ctx.exception.message_dict)

    def test_threshold_max_requires_threshold(self):
        rule = AlertRule(
            name="Test", target_type="THRESHOLD_MAX",
            variable_type="CAUDAL",
        )
        with self.assertRaises(ValidationError) as ctx:
            rule.clean()
        self.assertIn("threshold_value", ctx.exception.message_dict)

    def test_no_data_requires_minutes(self):
        rule = AlertRule(
            name="Test", target_type="NO_DATA",
            point_catchment_id=1,  # ID ficticio, no se guarda
        )
        with self.assertRaises(ValidationError) as ctx:
            rule.clean()
        self.assertIn("no_data_minutes", ctx.exception.message_dict)

    def test_scheduled_report_requires_schedule(self):
        rule = AlertRule(name="Test", target_type="SCHEDULED_REPORT")
        with self.assertRaises(ValidationError) as ctx:
            rule.clean()
        self.assertIn("report_schedule", ctx.exception.message_dict)
        self.assertIn("report_hour", ctx.exception.message_dict)

    def test_report_hour_must_be_0_to_23(self):
        rule = AlertRule(
            name="Test", target_type="SCHEDULED_REPORT",
            report_schedule="DAILY", report_hour=25,
        )
        with self.assertRaises(ValidationError) as ctx:
            rule.clean()
        self.assertIn("report_hour", ctx.exception.message_dict)

    def test_frequency_must_be_positive(self):
        rule = AlertRule(
            name="Test", target_type="THRESHOLD_MAX",
            variable_type="CAUDAL", threshold_value=Decimal("10"),
            check_frequency_minutes=0,
        )
        with self.assertRaises(ValidationError) as ctx:
            rule.clean()
        self.assertIn("check_frequency_minutes", ctx.exception.message_dict)

    def test_end_date_after_start_date(self):
        from datetime import date
        rule = AlertRule(
            name="Test", target_type="THRESHOLD_MAX",
            variable_type="CAUDAL", threshold_value=Decimal("10"),
            start_date=date(2026, 1, 10),
            end_date=date(2026, 1, 5),
        )
        with self.assertRaises(ValidationError) as ctx:
            rule.clean()
        self.assertIn("end_date", ctx.exception.message_dict)

    def test_valid_threshold_rule_passes(self):
        rule = AlertRule(
            name="Test OK", target_type="THRESHOLD_MAX",
            variable_type="CAUDAL", threshold_value=Decimal("10"),
            check_frequency_minutes=10, cooldown_minutes=60,
        )
        # No debe lanzar excepción
        rule.clean()


class AlertChannelValidationTests(TestCase):
    """Validaciones de integridad en AlertChannel.clean()."""

    def test_webhook_requires_valid_url(self):
        channel = AlertChannel(
            channel_type="WEBHOOK", destination="not-a-url",
        )
        with self.assertRaises(ValidationError) as ctx:
            channel.clean()
        self.assertIn("destination", ctx.exception.message_dict)

    def test_email_requires_valid_email(self):
        channel = AlertChannel(
            channel_type="EMAIL", destination="invalid-email",
        )
        with self.assertRaises(ValidationError) as ctx:
            channel.clean()
        self.assertIn("destination", ctx.exception.message_dict)

    def test_multiple_emails_accepted(self):
        channel = AlertChannel(
            channel_type="EMAIL",
            destination="a@example.com, b@example.com",
        )
        channel.clean()  # No debe fallar

    def test_valid_webhook_passes(self):
        channel = AlertChannel(
            channel_type="WEBHOOK",
            destination="https://hooks.example.com/alerts",
        )
        channel.clean()


@override_settings(MIDDLEWARE=TEST_MIDDLEWARE)
class AlertSubsystemAPITests(TestCase):
    """Smoke tests para endpoints del subsistema de alertas."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="alert_tester",
            email="alert_tester@example.com",
            password="testpass123",
        )
        self.token = Token.objects.create(user=self.user)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

    def test_alert_rules_list_requires_auth(self):
        anon = APIClient()
        resp = anon.get("/api/alert_rules/")
        self.assertEqual(resp.status_code, 401)

    def test_alert_rules_list_empty(self):
        resp = self.client.get("/api/alert_rules/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["count"], 0)

    def test_alert_triggers_list_empty(self):
        resp = self.client.get("/api/alert_triggers/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["count"], 0)

    def test_system_events_list_empty(self):
        resp = self.client.get("/api/system_events/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["count"], 0)

    def test_alert_rules_create_with_invalid_data_fails(self):
        payload = {
            "name": "Bad Rule",
            "target_type": "THRESHOLD_MAX",
            # Falta variable_type y threshold_value
        }
        resp = self.client.post("/api/alert_rules/", data=payload, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("variable_type", resp.data)
        self.assertIn("threshold_value", resp.data)

    def test_alert_channels_create_invalid_webhook_fails(self):
        rule = AlertRule.objects.create(
            name="Base Rule",
            target_type="THRESHOLD_MAX",
            variable_type="CAUDAL",
            threshold_value=10,
            check_frequency_minutes=10,
            cooldown_minutes=60,
        )
        payload = {
            "alert_rule": rule.id,
            "channel_type": "WEBHOOK",
            "destination": "not-a-url",
        }
        resp = self.client.post("/api/alert_channels/", data=payload, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("destination", resp.data)

    def test_alert_channels_list_empty(self):
        resp = self.client.get("/api/alert_channels/")
        self.assertEqual(resp.status_code, 200)

    def test_alert_triggers_filter_severity_and_triggered_at_gte(self):
        """
        N1 envía severity=CRITICAL y triggered_at__gte; ambos deben filtrar.
        Orden por defecto: más recientes primero.
        """
        client_obj = Client.objects.create(name="N1 Client")
        project = ProjectCatchments.objects.create(name="N1 Project", client=client_obj)
        point = CatchmentPoint.objects.create(
            title="N1 Point", project=project, owner_user=self.user, frecuency="60",
        )
        rule_crit = AlertRule.objects.create(
            name="Crítica caudal",
            target_type="THRESHOLD_MAX",
            variable_type="CAUDAL",
            threshold_value=Decimal("10"),
            severity="CRITICAL",
            check_frequency_minutes=1,
            cooldown_minutes=0,
            point_catchment=point,
        )
        rule_warn = AlertRule.objects.create(
            name="Warning nivel",
            target_type="THRESHOLD_MAX",
            variable_type="NIVEL",
            threshold_value=Decimal("100"),
            severity="WARNING",
            check_frequency_minutes=1,
            cooldown_minutes=0,
            point_catchment=point,
        )
        now = timezone.now()
        old = now - timedelta(hours=5)
        t_old_crit = AlertTrigger.objects.create(
            alert_rule=rule_crit, triggered_at=old, value_at_trigger=20,
            point_catchment=point,
        )
        t_new_crit = AlertTrigger.objects.create(
            alert_rule=rule_crit, triggered_at=now, value_at_trigger=25,
            point_catchment=point,
        )
        AlertTrigger.objects.create(
            alert_rule=rule_warn, triggered_at=now, value_at_trigger=200,
            point_catchment=point,
        )

        cutoff = (now - timedelta(hours=1)).isoformat().replace("+00:00", "Z")
        resp = self.client.get(
            "/api/alert_triggers/",
            {"severity": "CRITICAL", "triggered_at__gte": cutoff},
        )
        self.assertEqual(resp.status_code, 200)
        ids = [row["id"] for row in resp.data["results"]]
        self.assertIn(t_new_crit.id, ids)
        self.assertNotIn(t_old_crit.id, ids)
        self.assertTrue(all(row["severity"] == "CRITICAL" for row in resp.data["results"]))
        # Más reciente primero
        self.assertEqual(ids[0], t_new_crit.id)


class AlertEngineTriggerTests(TestCase):
    """Tests para el flujo completo: engine crea trigger con interaction_detail."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="engine_tester", email="engine@test.com", password="testpass"
        )
        self.client_obj = Client.objects.create(name="Engine Client")
        self.project = ProjectCatchments.objects.create(
            name="Engine Project", client=self.client_obj
        )
        self.point = CatchmentPoint.objects.create(
            title="Engine Point",
            owner_user=self.user,
            project=self.project,
            frecuency="60",
        )
        ProfileDataConfigCatchment.objects.create(
            point_catchment=self.point,
            is_telemetry=True,
        )
        self.interaction = InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition="2026-05-23T12:00:00+00:00",
            flow="150.0",
            total=1000.0,
        )

    def test_engine_creates_trigger_with_interaction_detail_id(self):
        """El motor debe crear un AlertTrigger con interaction_detail_id correcto."""
        from api.cronjobs.alerts.alert_engine import run_engine

        rule = AlertRule.objects.create(
            name="Test Caudal Alto",
            target_type="THRESHOLD_MAX",
            variable_type="CAUDAL",
            threshold_value=100,
            check_frequency_minutes=1,
            cooldown_minutes=0,
            point_catchment=self.point,
        )

        stats = run_engine(dry_run=False)

        self.assertEqual(stats["triggered"], 1)
        trigger = AlertTrigger.objects.filter(alert_rule=rule).first()
        self.assertIsNotNone(trigger)
        # interaction_detail debe estar presente (sea FK o IntegerField)
        self.assertEqual(trigger.interaction_detail_id, self.interaction.id)

    def test_dispatcher_processes_trigger_without_error(self):
        """El dispatcher debe procesar un trigger sin explotar."""
        from api.cronjobs.alerts.alert_dispatcher import run_dispatcher
        from api.cronjobs.alerts.alert_engine import run_engine

        rule = AlertRule.objects.create(
            name="Test Dispatcher",
            target_type="THRESHOLD_MAX",
            variable_type="CAUDAL",
            threshold_value=100,
            check_frequency_minutes=1,
            cooldown_minutes=0,
            point_catchment=self.point,
        )

        run_engine(dry_run=False)
        trigger = AlertTrigger.objects.filter(alert_rule=rule).first()
        self.assertIsNotNone(trigger)

        # El dispatcher no debe fallar al procesar el trigger
        stats = run_dispatcher(dry_run=True)
        self.assertEqual(stats["processed"], 1)
        self.assertEqual(stats["errors"], 0)

    def test_trigger_cooldown_prevents_duplicate(self):
        """El cooldown debe evitar triggers duplicados consecutivos."""
        from api.cronjobs.alerts.alert_engine import run_engine

        rule = AlertRule.objects.create(
            name="Test Cooldown",
            target_type="THRESHOLD_MAX",
            variable_type="CAUDAL",
            threshold_value=100,
            check_frequency_minutes=1,
            cooldown_minutes=60,
            point_catchment=self.point,
        )

        # Primera ejecución: debe crear trigger
        stats1 = run_engine(dry_run=False)
        self.assertEqual(stats1["triggered"], 1)

        # Segunda ejecución inmediata: no debe crear otro por cooldown
        stats2 = run_engine(dry_run=False)
        self.assertEqual(stats2["triggered"], 0)

    def test_totalizado_threshold_uses_period_consumption_not_absolute_total(self):
        """
        Regla TOTALIZADO debe evaluar consumo del período (total_diff / delta),
        no el total acumulado que siempre crece (caso P09 Central Yungay / AlertRule #5).
        """
        from api.cronjobs.alerts.alert_engine import run_engine

        # Total absoluto 113404 >> umbral 105845, pero consumo período = 50
        InteractionDetail.objects.filter(pk=self.interaction.pk).update(
            total="113404.0",
            total_diff=50,
            flow=0,
        )
        rule = AlertRule.objects.create(
            name="volumen acumulado Yungay",
            target_type="THRESHOLD_MAX",
            variable_type="TOTALIZADO",
            threshold_value=Decimal("105845"),
            severity="WARNING",
            check_frequency_minutes=1,
            cooldown_minutes=0,
            point_catchment=self.point,
        )

        stats = run_engine(dry_run=False)
        self.assertEqual(stats["triggered"], 0)
        self.assertFalse(AlertTrigger.objects.filter(alert_rule=rule).exists())

        # Si el consumo del período supera el umbral, sí dispara
        InteractionDetail.objects.filter(pk=self.interaction.pk).update(total_diff=200000)
        stats2 = run_engine(dry_run=False)
        self.assertEqual(stats2["triggered"], 1)
        trigger = AlertTrigger.objects.filter(alert_rule=rule).first()
        self.assertIsNotNone(trigger)
        self.assertEqual(float(trigger.value_at_trigger), 200000.0)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class AlertDispatcherEmailTests(TestCase):
    """El canal EMAIL debe enviarse correctamente (no 'Canal desconocido')."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="email_alert_tester",
            email="email_alert@test.com",
            password="testpass",
        )
        self.client_obj = Client.objects.create(name="CCU")
        self.project = ProjectCatchments.objects.create(
            name="Pozo Project", client=self.client_obj
        )
        self.point = CatchmentPoint.objects.create(
            title="Pozo 1",
            owner_user=self.user,
            project=self.project,
            frecuency="60",
        )
        self.rule = AlertRule.objects.create(
            name="Pozo 1 flow > 35 L/s",
            target_type="THRESHOLD_MAX",
            variable_type="CAUDAL",
            threshold_value=Decimal("35"),
            check_frequency_minutes=1,
            cooldown_minutes=0,
            point_catchment=self.point,
        )
        self.channel = AlertChannel.objects.create(
            alert_rule=self.rule,
            channel_type="EMAIL",
            destination="ops@ccu.example.com",
            is_active=True,
        )
        self.trigger = AlertTrigger.objects.create(
            alert_rule=self.rule,
            triggered_at=timezone.now(),
            value_at_trigger=Decimal("42.5"),
            threshold_breached=Decimal("35"),
            point_catchment=self.point,
            notification_sent=False,
        )

    def test_send_via_channel_email_succeeds(self):
        """_send_via_channel debe reconocer EMAIL y no devolver 'Canal desconocido'."""
        from api.cronjobs.alerts.alert_dispatcher import _send_via_channel

        mail.outbox = []
        ok, err = _send_via_channel(self.trigger, self.channel, dry_run=False)

        self.assertTrue(ok, msg=f"EMAIL falló: {err}")
        self.assertIsNone(err)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["ops@ccu.example.com"])
        self.assertIn("Pozo 1 flow > 35 L/s", mail.outbox[0].subject)
        self.assertIn("Pozo 1", mail.outbox[0].body)
        self.assertIn("42.5", mail.outbox[0].body)

    def test_send_via_channel_email_multiple_recipients(self):
        """EMAIL con varios destinatarios separados por coma."""
        from api.cronjobs.alerts.alert_dispatcher import _send_via_channel

        self.channel.destination = "a@ccu.example.com, b@ccu.example.com"
        self.channel.save(update_fields=["destination"])

        mail.outbox = []
        ok, err = _send_via_channel(self.trigger, self.channel, dry_run=False)

        self.assertTrue(ok, msg=f"EMAIL falló: {err}")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            set(mail.outbox[0].to),
            {"a@ccu.example.com", "b@ccu.example.com"},
        )

    def test_dispatcher_sends_email_and_marks_trigger(self):
        """run_dispatcher debe enviar EMAIL y marcar notification_sent sin error."""
        from api.cronjobs.alerts.alert_dispatcher import run_dispatcher

        mail.outbox = []
        stats = run_dispatcher(dry_run=False)

        self.assertNotIn("skipped", stats)
        self.assertEqual(stats["processed"], 1)
        self.assertEqual(stats["sent"], 1)
        self.assertEqual(stats["errors"], 0)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("ops@ccu.example.com", mail.outbox[0].to)

        self.trigger.refresh_from_db()
        self.assertTrue(self.trigger.notification_sent)
        self.assertIsNotNone(self.trigger.notification_sent_at)
        self.assertFalse(
            bool(self.trigger.notification_error)
            and "Canal desconocido" in (self.trigger.notification_error or "")
        )

    def test_dispatcher_google_chat_still_works(self):
        """GOOGLE_CHAT no debe romperse al rehabilitar EMAIL."""
        from api.cronjobs.alerts.alert_dispatcher import _send_via_channel

        chat_channel = AlertChannel.objects.create(
            alert_rule=self.rule,
            channel_type="GOOGLE_CHAT",
            destination="https://chat.googleapis.com/v1/spaces/AAA/messages?key=x",
            is_active=True,
        )

        with patch(
            "api.cronjobs.alerts.alert_dispatcher.send_google_chat_message"
        ) as mock_chat:
            ok, err = _send_via_channel(self.trigger, chat_channel, dry_run=False)

        self.assertTrue(ok, msg=f"GOOGLE_CHAT falló: {err}")
        self.assertIsNone(err)
        mock_chat.assert_called_once()

    def test_unknown_channel_still_reports_error(self):
        """Canales no soportados siguen reportando 'Canal desconocido'."""
        from api.cronjobs.alerts.alert_dispatcher import _send_via_channel

        bad = AlertChannel(
            alert_rule=self.rule,
            channel_type="PIGEON",
            destination="nowhere",
            is_active=True,
        )
        ok, err = _send_via_channel(self.trigger, bad, dry_run=False)
        self.assertFalse(ok)
        self.assertIn("Canal desconocido", err)
        self.assertIn("PIGEON", err)
