"""Tests para totalizador stateful de void (paridad con legacy controllers/total.py)."""
import uuid
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from void.models import (
    CounterResetLog,
    Device,
    DeviceEvent,
    DeviceVariableConfig,
    DeviceVariableState,
    Point,
    RawReading,
)
from void.services.handlers.stateful_rulesets import apply_totalizer_schema, create_totalizer_schema
from void.services.pipeline import PipelineService


class TotalizerStatefulTests(TestCase):
    def setUp(self):
        self.suffix = uuid.uuid4().hex[:8]
        self.point = Point.objects.create(
            name=f"P-Totalizer-{self.suffix}",
            frequency_minutes=60,
        )
        self.device = Device.objects.create(point=self.point, configuration={})
        self.config = apply_totalizer_schema(
            device=self.device,
            source_variable="pulses",
            internal_variable="total",
            output_field="total",
            pulses_factor=1000,
            max_diff_m3_per_hour=500,
            reconnection_threshold_hours=2,
            compute_flow=True,
        )

    def _raw(self, value, minutes_ago=0):
        ts = timezone.now() - timedelta(minutes=minutes_ago)
        return RawReading.objects.create(
            device=self.device,
            variable="total",
            source_variable="pulses",
            timestamp=ts,
            raw_value=str(value),
        )

    def _process(self, raw):
        return PipelineService().process_reading(raw)

    def test_simple_accumulation(self):
        p1 = self._process(self._raw(10))
        self.assertEqual(p1.total, Decimal("10.000"))
        self.assertEqual(p1.pulses, 10)

        p2 = self._process(self._raw(25))
        self.assertEqual(p2.total, Decimal("25.000"))
        self.assertEqual(p2.total_diff, Decimal("15.000"))

    def test_negative_pulses_keeps_last_total(self):
        self._process(self._raw(10))
        p = self._process(self._raw(-5))

        self.assertTrue(p.is_error)
        self.assertEqual(p.total, Decimal("10.000"))
        self.assertTrue(
            CounterResetLog.objects.filter(
                device=self.device, reset_type="NEGATIVE_PULSES"
            ).exists()
        )

    def test_zero_kept(self):
        self._process(self._raw(10))
        p = self._process(self._raw(0))

        self.assertEqual(p.total, Decimal("10.000"))
        self.assertTrue(
            CounterResetLog.objects.filter(
                device=self.device, reset_type="ZERO_KEPT"
            ).exists()
        )

    def test_partial_reset_compensates_offset(self):
        self._process(self._raw(10000))
        p = self._process(self._raw(8000))

        # 8000 pulsos = 8000 m³. Offset compensa 10000 pulsos = 10000 m³.
        self.assertEqual(p.total, Decimal("18000.000"))
        self.assertTrue(
            CounterResetLog.objects.filter(
                device=self.device, reset_type="PARTIAL"
            ).exists()
        )

    def test_noise_drop(self):
        self._process(self._raw(10000))
        p = self._process(self._raw(9995))

        self.assertEqual(p.total, Decimal("10000.000"))
        self.assertTrue(
            CounterResetLog.objects.filter(
                device=self.device, reset_type="NOISE_DROP"
            ).exists()
        )

    def test_partial_rejected_without_reconnection(self):
        self._process(self._raw(10000))
        p = self._process(self._raw(500))

        self.assertEqual(p.total, Decimal("10000.000"))
        self.assertTrue(
            CounterResetLog.objects.filter(
                device=self.device, reset_type="PARTIAL_REJECTED"
            ).exists()
        )

    def test_reconnection_allows_jump(self):
        ts_old = timezone.now() - timedelta(hours=6)
        r1 = RawReading.objects.create(
            device=self.device,
            variable="total",
            source_variable="pulses",
            timestamp=ts_old,
            raw_value="1000",
        )
        self._process(r1)

        p = self._process(self._raw(5000))
        self.assertTrue(p.is_reconnection)
        self.assertEqual(p.total, Decimal("5000.000"))

    def test_massive_jump_logged_but_accepted(self):
        self._process(self._raw(10))
        p = self._process(self._raw(1010))

        self.assertEqual(p.total, Decimal("1010.000"))
        self.assertTrue(
            DeviceEvent.objects.filter(
                device=self.device, event_type="massive_jump"
            ).exists()
        )

    def test_flow_computation(self):
        self._process(self._raw(10, minutes_ago=60))
        p = self._process(self._raw(20))

        self.assertEqual(p.total_diff, Decimal("10.000"))
        self.assertAlmostEqual(float(p.flow), 2.778, places=2)

    def test_daily_diff(self):
        p1 = self._process(self._raw(10))
        self.assertEqual(p1.total_today_diff, Decimal("0"))

        p2 = self._process(self._raw(25))
        self.assertEqual(p2.total_today_diff, Decimal("15.000"))


class TotalizerPipelineIntegrationTests(TestCase):
    def setUp(self):
        self.suffix = uuid.uuid4().hex[:8]
        self.point = Point.objects.create(
            name=f"P-Totalizer-Int-{self.suffix}",
            frequency_minutes=60,
        )
        self.device = Device.objects.create(point=self.point, configuration={})
        apply_totalizer_schema(
            device=self.device,
            source_variable="pulses",
            internal_variable="total",
            output_field="total",
            pulses_factor=1000,
        )

    def test_pipeline_uses_totalizer(self):
        raw = RawReading.objects.create(
            device=self.device,
            variable="total",
            source_variable="pulses",
            timestamp=timezone.now(),
            raw_value="100",
        )
        processed = PipelineService().process_reading(raw)
        self.assertEqual(processed.total, Decimal("100.000"))
        self.assertEqual(processed.pulses, 100)
        self.assertEqual(processed.processor_version, "void.pipeline.v2")


class TotalizerTemplateTests(TestCase):
    def test_schema_is_template_and_reusable(self):
        s1 = create_totalizer_schema()
        s2 = create_totalizer_schema()
        self.assertEqual(s1.id, s2.id)
        self.assertTrue(s1.is_template)
