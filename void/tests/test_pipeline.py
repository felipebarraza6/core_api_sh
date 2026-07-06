"""Tests for void processing pipeline."""
from datetime import datetime
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from void.models import (
    Device,
    DeviceVariableConfig,
    Point,
    ProcessedReading,
    ProcessingSchema,
    ProcessingStep,
    RawReading,
)
from void.services.handlers.stateful_rulesets import apply_totalizer_schema
from void.services.pipeline import PipelineService


class PipelineServiceTests(TestCase):
    def setUp(self):
        self.point = Point.objects.create(name="P1")
        self.device = Device.objects.create(
            point=self.point,
            configuration={"pulses_factor": 1000, "variables": ["pulses"]},
        )
        apply_totalizer_schema(
            device=self.device,
            source_variable="pulses",
            internal_variable="pulses",
            pulses_factor=1000,
        )
        self.schema = ProcessingSchema.objects.create(
            name="Pulses validation",
            version="1.0",
            applies_to={"devices": [str(self.device.id)]},
        )
        ProcessingStep.objects.create(
            schema=self.schema,
            order=1,
            step_type="filter",
            name="Filter negatives",
            configuration={"min_value": 0, "action": "drop"},
        )

    def test_pipeline_creates_processed_reading(self):
        raw = RawReading.objects.create(
            device=self.device,
            variable="pulses",
            timestamp=timezone.now(),
            raw_value="5",
        )
        service = PipelineService()
        processed = service.process_reading(raw)

        self.assertEqual(processed.device, self.device)
        self.assertEqual(processed.variable, "pulses")
        self.assertEqual(processed.total, 5)

    def test_pipeline_filter_drops_invalid_value(self):
        # El handler stateful se ejecuta primero; usamos un valor que el handler
        # acepte (no negativo) pero que el schema filtre por max_value.
        raw = RawReading.objects.create(
            device=self.device,
            variable="pulses",
            timestamp=timezone.now(),
            raw_value="5",
        )
        # Ajustamos el filtro del schema para rechazar valores > 3.
        filter_step = self.schema.steps.first()
        filter_step.configuration = {"min_value": 0, "max_value": 3, "action": "drop"}
        filter_step.save()

        service = PipelineService()
        processed = service.process_reading(raw)

        self.assertTrue(processed.is_error)
        self.assertIn("fuera de rango", processed.error_message)

    def test_pipeline_no_schema(self):
        self.schema.delete()
        raw = RawReading.objects.create(
            device=self.device,
            variable="pulses",
            timestamp=timezone.now(),
            raw_value="10",
        )
        service = PipelineService()
        processed = service.process_reading(raw)

        self.assertIsNone(processed.processing_schema)
        self.assertFalse(processed.is_error)

    def test_pipeline_custom_schema_per_variable(self):
        """Una variable puede tener su propio schema declarativo stateful."""
        from void.models import ProcessingRule

        custom_schema = ProcessingSchema.objects.create(
            name="PH custom",
            version="1.0",
        )
        step = ProcessingStep.objects.create(
            schema=custom_schema,
            order=1,
            step_type="stateful",
            name="Scale ph",
        )
        ProcessingRule.objects.create(
            step=step,
            order=1,
            action="set_output",
            action_params={"output": "total", "formula": "value / 10"},
        )
        DeviceVariableConfig.objects.create(
            device=self.device,
            source_variable="ph_raw",
            internal_variable="other",
            processing_type="stateful",
            custom_schema=custom_schema,
        )

        raw = RawReading.objects.create(
            device=self.device,
            variable="other",
            source_variable="ph_raw",
            timestamp=timezone.now(),
            raw_value="72",
        )
        processed = PipelineService().process_reading(raw)

        self.assertFalse(processed.is_error)
        # 72 / 10 = 7.2
        self.assertEqual(processed.total, Decimal("7.2"))
