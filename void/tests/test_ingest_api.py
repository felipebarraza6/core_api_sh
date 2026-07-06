"""Tests for void ingest API."""
import json

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from void.models import Device, Point
from void.services.handlers.stateful_rulesets import apply_totalizer_schema


class IngestApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.point = Point.objects.create(name="P-Ingest")
        self.device = Device.objects.create(
            point=self.point,
            serial_number="SN-INGEST-001",
            configuration={"ingest_token": "secret-token-123", "variables": ["pulses"]},
        )
        apply_totalizer_schema(
            self.device,
            source_variable="pulses",
            pulses_factor=1000,
        )

    def test_ingest_without_token_returns_401(self):
        response = self.client.post(
            reverse("void:ingest"),
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)

    def test_ingest_invalid_token_returns_403(self):
        response = self.client.post(
            reverse("void:ingest"),
            data=json.dumps({"serial_number": "SN-INGEST-001", "source_variable": "pulses", "value": "10"}),
            content_type="application/json",
            HTTP_X_DEVICE_TOKEN="bad-token",
        )
        self.assertEqual(response.status_code, 403)

    def test_ingest_creates_raw_and_processed(self):
        response = self.client.post(
            reverse("void:ingest"),
            data=json.dumps({
                "serial_number": "SN-INGEST-001",
                "source_variable": "pulses",
                "value": "25",
                "timestamp": "2026-07-05T14:00:00Z",
            }),
            content_type="application/json",
            HTTP_X_DEVICE_TOKEN="secret-token-123",
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["total"], "25.000")
        self.assertEqual(data["variable"], "pulses")
        self.assertFalse(data["is_error"])

        self.assertTrue(self.device.raw_readings.filter(raw_value="25").exists())
        self.assertTrue(self.device.processed_readings.filter(total=25).exists())

    def test_ingest_auto_configure(self):
        """auto_configure aplica la plantilla stateful si la variable no existe."""
        response = self.client.post(
            reverse("void:ingest"),
            data=json.dumps({
                "serial_number": "SN-INGEST-001",
                "source_variable": "flow",
                "value": "12",
                "auto_configure": True,
            }),
            content_type="application/json",
            HTTP_X_DEVICE_TOKEN="secret-token-123",
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(
            self.device.variable_configs.filter(source_variable="flow").exists()
        )
