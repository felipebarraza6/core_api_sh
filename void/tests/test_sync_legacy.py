"""Tests for legacy-to-void sync command."""
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from api.core.models import CatchmentPoint, ProjectCatchments, TelemetryProvider
from void.models import Device, Point, Provider


User = get_user_model()


class SyncLegacyTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="legacy_owner",
            email="legacy@smarthydro.cl",
            password="testpass123",
        )
        self.project = ProjectCatchments.objects.create(name="Proyecto Test")

    def test_sync_creates_point_and_device_from_catchment(self):
        legacy_provider = TelemetryProvider.objects.create(
            name="TheThings.io",
            handler_name="thethings",
            protocol="HTTP_REST",
            base_url="https://api.thethings.io/v2",
            auth_type="NONE",
        )
        void_provider = Provider.objects.create(
            name="TheThings.io",
            protocol="HTTP_REST",
            metadata={"legacy_provider_id": legacy_provider.id, "handler_name": "dynamic_http"},
        )

        cp = CatchmentPoint.objects.create(
            title="Punto Legacy",
            project=self.project,
            owner_user=self.user,
            telemetry_provider=legacy_provider,
            is_thethings=True,
            lat="-33.0",
            lon="-70.0",
        )

        call_command("void_sync_legacy", stdout=StringIO())

        point = Point.objects.get(legacy_point=cp)
        self.assertEqual(point.name, "Punto Legacy")
        self.assertEqual(point.lat, "-33.0")

        device = Device.objects.get(point=point)
        self.assertEqual(device.provider, void_provider)
        self.assertEqual(device.configuration.get("legacy_provider_id"), legacy_provider.id)

    def test_sync_maps_external_id_from_profile_data_config(self):
        legacy_provider = TelemetryProvider.objects.create(
            name="TwinDimension TDATA",
            handler_name="tdata",
            protocol="HTTP_REST",
            base_url="https://api.twindimension.com/tdata/v1",
            auth_type="BASIC",
            auth_username="user",
            auth_password="pass",
        )
        void_provider = Provider.objects.create(
            name="TwinDimension TDATA",
            protocol="HTTP_REST",
            metadata={"legacy_provider_id": legacy_provider.id, "handler_name": "tdata"},
        )

        cp = CatchmentPoint.objects.create(
            title="Punto TDATA",
            project=self.project,
            owner_user=self.user,
            telemetry_provider=legacy_provider,
            is_tdata=True,
        )
        cp.data_config_profiles.create(token_service="device-token-123")

        call_command("void_sync_legacy", stdout=StringIO())

        device = Device.objects.get(point__legacy_point=cp)
        self.assertEqual(device.provider, void_provider)
        self.assertEqual(device.external_id, "device-token-123")

    def test_sync_idempotent(self):
        cp = CatchmentPoint.objects.create(
            title="Punto Repetido",
            project=self.project,
            owner_user=self.user,
        )

        call_command("void_sync_legacy", stdout=StringIO())
        first_count = Point.objects.count()

        call_command("void_sync_legacy", stdout=StringIO())
        second_count = Point.objects.count()

        self.assertEqual(first_count, second_count)
