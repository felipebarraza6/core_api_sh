"""Tests for shadow mode on processed totals."""
import uuid
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from api.core.models import CatchmentPoint, InteractionDetail, ProjectCatchments
from decimal import Decimal
from django.contrib.auth import get_user_model

from void.models import (
    Device,
    Point,
    ProcessedReading,
    Provider,
    ShadowRun,
)
from void.services import ShadowService
from void.services.handlers.stateful_rulesets import apply_totalizer_schema


class ShadowTotalsTests(TestCase):
    def setUp(self):
        self.suffix = uuid.uuid4().hex[:8]
        User = get_user_model()
        self.user = User.objects.create_user(
            username=f"shadow_owner_{self.suffix}",
            email=f"shadow_{self.suffix}@smarthydro.cl",
            password="testpass123",
        )
        self.project = ProjectCatchments.objects.create(name=f"Shadow Project {self.suffix}")
        self.legacy_point = CatchmentPoint.objects.create(
            title=f"Shadow Point {self.suffix}",
            project=self.project,
            owner_user=self.user,
        )
        self.point = Point.objects.create(
            name=f"Shadow Point {self.suffix}",
            legacy_point=self.legacy_point,
        )
        self.provider = Provider.objects.create(
            name=f"Shadow Provider {self.suffix}",
            protocol="HTTP_REST",
        )
        self.device = Device.objects.create(
            point=self.point,
            provider=self.provider,
            external_id="dev-123",
            configuration={"variables": ["pulses"]},
        )
        self.config = apply_totalizer_schema(
            device=self.device,
            source_variable="pulses",
            internal_variable="totalizado",
            output_field="total",
            pulses_factor=1000,
        )

    def test_run_for_output_field_discovers_variable(self):
        now = timezone.now().replace(second=0, microsecond=0)
        InteractionDetail.objects.create(
            catchment_point=self.legacy_point,
            date_time_medition=now,
            total=150,
        )
        ProcessedReading.objects.create(
            device=self.device,
            variable="totalizado",
            timestamp=now,
            total=Decimal("150.000"),
        )

        service = ShadowService()
        run = service.run_for_output_field(self.device, output_field="total", ingest=False, process=False)

        self.assertEqual(run.status, "completed")
        self.assertEqual(run.variable, "totalizado")
        self.assertEqual(run.output_field, "total")
        self.assertEqual(run.matched_count, 1)

    def test_run_for_output_field_skips_when_no_config(self):
        self.config.delete()
        service = ShadowService()
        run = service.run_for_output_field(self.device, output_field="total", ingest=False, process=False)

        self.assertEqual(run.status, "skipped")
        self.assertIn("No hay config", run.error_message)

    def test_run_for_output_field_uses_internal_variable_when_output_empty(self):
        self.config.output_field = ""
        self.config.internal_variable = "total"
        self.config.save()

        now = timezone.now().replace(second=0, microsecond=0)
        InteractionDetail.objects.create(
            catchment_point=self.legacy_point,
            date_time_medition=now,
            total=200,
        )
        ProcessedReading.objects.create(
            device=self.device,
            variable="total",
            timestamp=now,
            total=Decimal("200.000"),
        )

        service = ShadowService()
        run = service.run_for_output_field(self.device, output_field="total", ingest=False, process=False)

        self.assertEqual(run.status, "completed")
        self.assertEqual(run.matched_count, 1)

    def test_tolerance_for_totals_allows_integer_rounding(self):
        now = timezone.now().replace(second=0, microsecond=0)
        InteractionDetail.objects.create(
            catchment_point=self.legacy_point,
            date_time_medition=now,
            total=150,
        )
        ProcessedReading.objects.create(
            device=self.device,
            variable="totalizado",
            timestamp=now,
            total=Decimal("150.400"),
        )

        service = ShadowService()
        run = service.run_for_output_field(self.device, output_field="total", ingest=False, process=False)

        self.assertEqual(run.status, "completed")
        self.assertEqual(run.matched_count, 1)


from decimal import Decimal
