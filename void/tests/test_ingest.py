"""Tests for void ingest service."""
from datetime import datetime

from django.test import TestCase
from django.utils import timezone

from void.models import Device, Point, RawReading
from void.services import IngestService


class IngestServiceTests(TestCase):
    def setUp(self):
        self.point = Point.objects.create(name="P1")
        self.device = Device.objects.create(
            point=self.point,
            configuration={"variables": ["pulses"]},
        )
        self.service = IngestService()

    def test_ingest_single_reading(self):
        now = timezone.now()
        raw = self.service.ingest_reading(
            device=self.device,
            variable="pulses",
            timestamp=now,
            value=42,
            unit="pulses",
        )
        self.assertEqual(raw.raw_value, "42")
        self.assertEqual(raw.unit, "pulses")
        self.assertEqual(RawReading.objects.count(), 1)

    def test_ingest_without_provider_returns_empty(self):
        created = self.service.ingest_device_variable(
            device=self.device,
            variable="pulses",
        )
        self.assertEqual(created, [])

    def test_ingest_device_variable_deduplicates_by_timestamp(self):
        """ingest_device_variable omite lecturas con mismo device/variable/timestamp."""
        from datetime import datetime

        from void.models import Provider
        from void.services.providers.registry import registry

        class FakeProvider:
            name = "fake_test_provider"

            def __init__(self, provider):
                self.provider = provider

            def authenticate(self):
                return None

            def fetch(self, device, variable, since=None, until=None):
                return [{"value": 99, "timestamp": since or timezone.now()}]

        registry.register(FakeProvider)

        now = timezone.now()
        RawReading.objects.create(
            device=self.device,
            variable="pulses",
            timestamp=now,
            raw_value="10",
        )

        provider = Provider.objects.create(
            name="Fake Test",
            protocol="HTTP_REST",
            metadata={"handler_name": "fake_test_provider"},
        )
        self.device.provider = provider
        self.device.save(update_fields=["provider"])

        created = self.service.ingest_device_variable(
            device=self.device,
            variable="pulses",
            since=now,
            until=now,
        )
        self.assertEqual(created, [])
        self.assertEqual(RawReading.objects.count(), 1)


