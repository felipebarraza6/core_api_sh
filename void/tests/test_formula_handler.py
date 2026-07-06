"""Tests for void FormulaHandler."""
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from void.models import (
    Device,
    DeviceVariableConfig,
    Point,
    RawReading,
)
from void.services.pipeline import PipelineService


class FormulaHandlerTests(TestCase):
    def setUp(self):
        self.point = Point.objects.create(
            name="P-Formula",
            constants={"d1": "1.5", "d2": "2.0", "d3": "0.5"},
        )
        self.device = Device.objects.create(
            point=self.point,
            configuration={"variables": ["nivel", "caudal"]},
        )

    def test_nivel_with_offset(self):
        """value + offset se guarda en el campo configurado."""
        DeviceVariableConfig.objects.create(
            device=self.device,
            source_variable="nivel_raw",
            internal_variable="nivel",
            processing_type="formula",
            formula="value + offset",
            output_field="nivel",
            scale="1",
            offset="0.25",
        )
        raw = RawReading.objects.create(
            device=self.device,
            variable="nivel",
            source_variable="nivel_raw",
            timestamp=timezone.now(),
            raw_value="10",
        )
        processed = PipelineService().process_reading(raw)

        self.assertFalse(processed.is_error)
        self.assertEqual(processed.nivel, Decimal("10.25"))

    def test_flow_with_scale(self):
        """value * scale produce caudal en L/s."""
        DeviceVariableConfig.objects.create(
            device=self.device,
            source_variable="flow_raw",
            internal_variable="caudal",
            processing_type="formula",
            formula="value * scale",
            output_field="flow",
            scale="0.1",
            offset="0",
        )
        raw = RawReading.objects.create(
            device=self.device,
            variable="caudal",
            source_variable="flow_raw",
            timestamp=timezone.now(),
            raw_value="50",
        )
        processed = PipelineService().process_reading(raw)

        self.assertFalse(processed.is_error)
        self.assertEqual(processed.flow, Decimal("5.000"))

    def test_point_constants_in_formula(self):
        """d1/d2/d3 del punto están disponibles en la fórmula."""
        DeviceVariableConfig.objects.create(
            device=self.device,
            source_variable="pressure_raw",
            internal_variable="pressure",
            processing_type="formula",
            formula="(value * d1) + d2 - d3",
            output_field="water_table",
            scale="1",
            offset="0",
        )
        raw = RawReading.objects.create(
            device=self.device,
            variable="pressure",
            source_variable="pressure_raw",
            timestamp=timezone.now(),
            raw_value="2",
        )
        processed = PipelineService().process_reading(raw)

        # (2 * 1.5) + 2.0 - 0.5 = 3 + 2 - 0.5 = 4.5
        self.assertFalse(processed.is_error)
        self.assertEqual(processed.water_table, Decimal("4.500"))

    def test_unknown_output_goes_to_extra_values(self):
        """Si output_field no es un campo fijo, va a extra_values."""
        DeviceVariableConfig.objects.create(
            device=self.device,
            source_variable="custom_raw",
            internal_variable="custom",
            processing_type="formula",
            formula="value * 2",
            output_field="custom_metric",
            scale="1",
            offset="0",
        )
        raw = RawReading.objects.create(
            device=self.device,
            variable="custom",
            source_variable="custom_raw",
            timestamp=timezone.now(),
            raw_value="7",
        )
        processed = PipelineService().process_reading(raw)

        self.assertFalse(processed.is_error)
        self.assertEqual(processed.extra_values.get("custom_metric"), "14")

    def test_invalid_formula_flags_error(self):
        """Una fórmula con nombre no permitido marca error."""
        DeviceVariableConfig.objects.create(
            device=self.device,
            source_variable="bad_raw",
            internal_variable="bad",
            processing_type="formula",
            formula="value + unknown_var",
            output_field="bad",
            scale="1",
            offset="0",
        )
        raw = RawReading.objects.create(
            device=self.device,
            variable="bad",
            source_variable="bad_raw",
            timestamp=timezone.now(),
            raw_value="1",
        )
        processed = PipelineService().process_reading(raw)

        self.assertTrue(processed.is_error)
        self.assertIn("unknown_var", processed.error_message)

    def test_non_numeric_raw_value_is_error(self):
        """Un valor crudo no numérico se reporta como error."""
        DeviceVariableConfig.objects.create(
            device=self.device,
            source_variable="nan_raw",
            internal_variable="nan",
            processing_type="formula",
            formula="value",
            output_field="nan",
            scale="1",
            offset="0",
        )
        raw = RawReading.objects.create(
            device=self.device,
            variable="nan",
            source_variable="nan_raw",
            timestamp=timezone.now(),
            raw_value="not-a-number",
        )
        processed = PipelineService().process_reading(raw)

        self.assertTrue(processed.is_error)
        self.assertIn("no numérico", processed.error_message)
