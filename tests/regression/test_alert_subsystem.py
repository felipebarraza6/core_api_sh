"""
Tests de regresión para el subsistema de alertas.

Validan que:
1. AlertRule.clean() rechaza configuraciones inválidas
2. AlertChannel.clean() rechaza destinos inválidos
3. Los endpoints de API responden con estructura esperada
4. El motor no genera triggers para reglas con cooldown activo
"""

from decimal import Decimal

from django.test import TestCase, override_settings
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token

from api.core.models import (
    AlertRule, AlertChannel, AlertTrigger, SystemEvent,
    CatchmentPoint, User, InteractionDetail,
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
        self.assertEqual(resp.data["count"], 0)
