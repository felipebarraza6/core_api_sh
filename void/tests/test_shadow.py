"""Tests for shadow mode comparison service."""
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from api.core.models import CatchmentPoint, InteractionDetail, ProjectCatchments
from void.models import (
    Device,
    Point,
    Provider,
    RawReading,
    ShadowComparison,
    ShadowRun,
)
from void.services import ShadowService


class ShadowServiceTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        self.user = User.objects.create_user(
            username="shadow_owner",
            email="shadow@smarthydro.cl",
            password="testpass123",
        )
        self.project = ProjectCatchments.objects.create(name="Shadow Project")
        self.legacy_point = CatchmentPoint.objects.create(
            title="Shadow Point",
            project=self.project,
            owner_user=self.user,
        )
        self.point = Point.objects.create(
            name="Shadow Point",
            legacy_point=self.legacy_point,
        )
        self.provider = Provider.objects.create(
            name="Shadow Provider",
            protocol="HTTP_REST",
        )
        self.device = Device.objects.create(
            point=self.point,
            provider=self.provider,
            external_id="dev-123",
            configuration={"variables": ["pulses"]},
        )

    def test_run_skips_when_no_provider(self):
        self.device.provider = None
        self.device.save(update_fields=["provider"])

        service = ShadowService()
        run = service.run(self.device, "pulses", ingest=False)

        self.assertEqual(run.status, "skipped")

    def test_run_skips_when_no_legacy_point(self):
        self.point.legacy_point = None
        self.point.save(update_fields=["legacy_point"])

        service = ShadowService()
        run = service.run(self.device, "pulses", ingest=False)

        self.assertEqual(run.status, "skipped")

    def test_run_matches_records_by_timestamp(self):
        now = timezone.now().replace(second=0, microsecond=0)
        InteractionDetail.objects.create(
            catchment_point=self.legacy_point,
            date_time_medition=now,
            variable_values={"1": "123.45"},
            pulses=123,
        )
        RawReading.objects.create(
            device=self.device,
            variable="pulses",
            timestamp=now,
            raw_value="123.45",
        )

        service = ShadowService()
        run = service.run(self.device, "pulses", ingest=False)

        self.assertEqual(run.status, "completed")
        self.assertEqual(run.legacy_count, 1)
        self.assertEqual(run.void_count, 1)
        self.assertEqual(run.matched_count, 1)
        self.assertEqual(run.mismatched_count, 0)

    def test_run_detects_mismatch(self):
        now = timezone.now().replace(second=0, microsecond=0)
        InteractionDetail.objects.create(
            catchment_point=self.legacy_point,
            date_time_medition=now,
            variable_values={"1": "100.00"},
            pulses=100,
        )
        RawReading.objects.create(
            device=self.device,
            variable="pulses",
            timestamp=now,
            raw_value="200.00",
        )

        service = ShadowService()
        run = service.run(self.device, "pulses", ingest=False)

        self.assertEqual(run.status, "completed")
        self.assertEqual(run.matched_count, 0)
        self.assertEqual(run.mismatched_count, 1)

    def test_run_detects_legacy_only(self):
        now = timezone.now().replace(second=0, microsecond=0)
        InteractionDetail.objects.create(
            catchment_point=self.legacy_point,
            date_time_medition=now,
            variable_values={"1": "100.00"},
            pulses=100,
        )

        service = ShadowService()
        run = service.run(self.device, "pulses", ingest=False)

        self.assertEqual(run.legacy_only_count, 1)
        self.assertEqual(run.void_only_count, 0)

    def test_run_uses_last_void_reading_per_hour(self):
        """Legacy es horario; void es por minuto. Se compara el último valor de la hora."""
        hour_start = (timezone.now() - timedelta(minutes=60)).replace(minute=0, second=0, microsecond=0)
        InteractionDetail.objects.create(
            catchment_point=self.legacy_point,
            date_time_medition=hour_start,
            variable_values={"1": "150.00"},
            pulses=150,
        )
        # Tres lecturas void en la misma hora; la última debe usarse para comparar.
        RawReading.objects.create(
            device=self.device,
            variable="pulses",
            timestamp=hour_start + timedelta(minutes=10),
            raw_value="100.00",
        )
        RawReading.objects.create(
            device=self.device,
            variable="pulses",
            timestamp=hour_start + timedelta(minutes=30),
            raw_value="120.00",
        )
        RawReading.objects.create(
            device=self.device,
            variable="pulses",
            timestamp=hour_start + timedelta(minutes=50),
            raw_value="150.00",
        )

        service = ShadowService()
        run = service.run(self.device, "pulses", window_minutes=120, ingest=False)

        self.assertEqual(run.status, "completed")
        self.assertEqual(run.legacy_count, 1)
        self.assertEqual(run.void_count, 3)
        self.assertEqual(run.matched_count, 1)
        self.assertEqual(run.mismatched_count, 0)
        self.assertEqual(run.legacy_only_count, 0)
        self.assertEqual(run.void_only_count, 0)
