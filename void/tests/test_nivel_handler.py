"""Tests para nivel stateful de void (paridad con legacy process_nivel_variable)."""
import uuid
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from void.models import Device, Point, RawReading
from void.services.handlers.stateful_rulesets import apply_nivel_schema
from void.services.pipeline import PipelineService


class NivelStatefulTests(TestCase):
    def setUp(self):
        self.suffix = uuid.uuid4().hex[:8]
        self.point = Point.objects.create(
            name=f"P-Nivel-{self.suffix}",
            constants={"d3": 10.0},
        )
        self.device = Device.objects.create(point=self.point, configuration={})
        self.config = apply_nivel_schema(
            device=self.device,
            source_variable="lvl",
            internal_variable="nivel",
            output_field="nivel",
            offset=0,
            calculate_nivel=2,
            d3=10,
        )

    def _raw(self, value):
        return RawReading.objects.create(
            device=self.device,
            variable="nivel",
            source_variable="lvl",
            timestamp=timezone.now(),
            raw_value=str(value),
        )

    def _process(self, raw):
        return PipelineService().process_reading(raw)

    def test_simple_nivel_calculation(self):
        p = self._process(self._raw(8))
        self.assertEqual(p.nivel, Decimal("4.000"))
        self.assertEqual(p.water_table, Decimal("6.000"))

    def test_offset_applied(self):
        self.config.offset = Decimal("2")
        self.config.save()
        p = self._process(self._raw(8))
        self.assertEqual(p.nivel, Decimal("5.000"))

    def test_negative_corrected_with_historic(self):
        self._process(self._raw(8))
        p = self._process(self._raw(-2))
        # raw -2 se corrige al nivel histórico más alto (4.0); nivel = 4.0 / 2 = 2.0
        self.assertEqual(p.nivel, Decimal("2.000"))

    def test_negative_without_history_becomes_zero(self):
        p = self._process(self._raw(-5))
        self.assertEqual(p.nivel, Decimal("0.000"))

    def test_invalid_base_returns_zero(self):
        self.config.extra_data = {"calculate_nivel": 0, "d3": 10}
        self.config.save()
        p = self._process(self._raw(8))
        self.assertEqual(p.nivel, Decimal("0.000"))

    def test_invalid_d3_returns_zero_water_table(self):
        self.config.extra_data = {"calculate_nivel": 2, "d3": 0}
        self.config.save()
        p = self._process(self._raw(8))
        self.assertEqual(p.nivel, Decimal("4.000"))
        self.assertEqual(p.water_table, Decimal("0.000"))

    def test_water_table_negative_clamped(self):
        self.config.extra_data = {"calculate_nivel": 2, "d3": 3}
        self.config.save()
        p = self._process(self._raw(8))
        self.assertEqual(p.water_table, Decimal("0.000"))

    def test_d3_from_point_constants(self):
        self.config.extra_data = {"calculate_nivel": 2}
        self.config.save()
        p = self._process(self._raw(8))
        self.assertEqual(p.water_table, Decimal("6.000"))


class NivelPipelineIntegrationTests(TestCase):
    def setUp(self):
        self.suffix = uuid.uuid4().hex[:8]
        self.point = Point.objects.create(
            name=f"P-Nivel-Int-{self.suffix}",
            constants={"d3": 10.0},
        )
        self.device = Device.objects.create(point=self.point, configuration={})
        apply_nivel_schema(
            device=self.device,
            source_variable="lvl",
            internal_variable="nivel",
            output_field="nivel",
            calculate_nivel=2,
            d3=10,
        )

    def test_pipeline_uses_nivel_stateful(self):
        raw = RawReading.objects.create(
            device=self.device,
            variable="nivel",
            source_variable="lvl",
            timestamp=timezone.now(),
            raw_value="8",
        )
        processed = PipelineService().process_reading(raw)
        self.assertEqual(processed.nivel, Decimal("4.000"))
        self.assertEqual(processed.water_table, Decimal("6.000"))
