"""Tests for void StatefulRuleHandler."""
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from void.models import (
    Device,
    DeviceVariableConfig,
    DeviceVariableState,
    Point,
    ProcessingRule,
    ProcessingSchema,
    ProcessingStep,
    RawReading,
)
from void.services.handlers.stateful_rulesets import apply_nivel_schema, apply_totalizer_schema, create_totalizer_schema
from void.services.pipeline import PipelineService


class StatefulRuleHandlerTests(TestCase):
    def setUp(self):
        self.point = Point.objects.create(name="P-Stateful")
        self.device = Device.objects.create(
            point=self.point,
            configuration={"variables": ["pulses"]},
        )

    def _create_counter_schema(self):
        """Schema stateful simple: acumula value en state_total y emite total."""
        schema = ProcessingSchema.objects.create(
            name="Counter v1",
            version="1.0",
        )
        step = ProcessingStep.objects.create(
            schema=schema,
            order=1,
            step_type="stateful",
            name="Acumulador",
        )
        # Salida = estado acumulado + valor actual.
        ProcessingRule.objects.create(
            step=step,
            order=1,
            condition="",
            action="set_output",
            action_params={
                "output": "total",
                "formula": "(state_total or 0) + value",
            },
        )
        # Actualiza el estado.
        ProcessingRule.objects.create(
            step=step,
            order=2,
            condition="",
            action="update_state",
            action_params={
                "key": "total",
                "formula": "(state_total or 0) + value",
            },
        )
        return schema

    def test_simple_counter_accumulates(self):
        schema = self._create_counter_schema()
        DeviceVariableConfig.objects.create(
            device=self.device,
            source_variable="pulses",
            internal_variable="pulses",
            processing_type="stateful",
            custom_schema=schema,
            pulses_factor=1000,
        )

        for value in [10, 20, 30]:
            raw = RawReading.objects.create(
                device=self.device,
                variable="pulses",
                source_variable="pulses",
                timestamp=timezone.now(),
                raw_value=str(value),
            )
            PipelineService().process_reading(raw)

        state = DeviceVariableState.objects.get(device=self.device, variable="pulses")
        self.assertEqual(Decimal(state.state["total"]), Decimal("60"))

    def test_zero_keeps_last_total(self):
        """Regla condicional: si value == 0, mantener total anterior."""
        schema = ProcessingSchema.objects.create(
            name="Counter zero keep",
            version="1.0",
        )
        step = ProcessingStep.objects.create(
            schema=schema,
            order=1,
            step_type="stateful",
            name="Acumulador con keep zero",
        )
        # Caso value == 0: output = state_total, no actualiza estado.
        ProcessingRule.objects.create(
            step=step,
            order=1,
            condition="value == 0 and (state_total or 0) > 0",
            action="set_output",
            action_params={"output": "total", "formula": "state_total"},
        )
        ProcessingRule.objects.create(
            step=step,
            order=2,
            condition="value == 0 and (state_total or 0) > 0",
            action="stop",
            action_params={},
        )
        # Caso normal.
        ProcessingRule.objects.create(
            step=step,
            order=3,
            condition="",
            action="set_output",
            action_params={"output": "total", "formula": "(state_total or 0) + value"},
        )
        ProcessingRule.objects.create(
            step=step,
            order=4,
            condition="",
            action="update_state",
            action_params={"key": "total", "formula": "(state_total or 0) + value"},
        )

        DeviceVariableConfig.objects.create(
            device=self.device,
            source_variable="pulses",
            internal_variable="pulses",
            processing_type="stateful",
            custom_schema=schema,
            pulses_factor=1000,
        )

        for value in [10, 20, 0, 30]:
            raw = RawReading.objects.create(
                device=self.device,
                variable="pulses",
                source_variable="pulses",
                timestamp=timezone.now(),
                raw_value=str(value),
            )
            PipelineService().process_reading(raw)

        state = DeviceVariableState.objects.get(device=self.device, variable="pulses")
        self.assertEqual(Decimal(state.state["total"]), Decimal("60"))

        # La lectura con 0 emitió total=30 (el total previo).
        zero_processed = self.device.processed_readings.filter(
            variable="pulses", raw_reading__raw_value="0"
        ).first()
        self.assertIsNotNone(zero_processed)
        self.assertEqual(zero_processed.total, Decimal("30"))

    def test_partial_reset_compensates_offset(self):
        """Simula totalizador: pulsos bajan -> compensar offset."""
        schema = ProcessingSchema.objects.create(
            name="Totalizer simplified",
            version="1.0",
        )
        step = ProcessingStep.objects.create(
            schema=schema,
            order=1,
            step_type="stateful",
            name="Totalizador simplificado",
        )
        # raw_m3 = value * pulses_factor / 1000
        # Caso reset parcial: value < state_last_pulses y value > 0.
        ProcessingRule.objects.create(
            step=step,
            order=1,
            condition="(state_last_pulses or 0) > 0 and value > 0 and value < state_last_pulses",
            action="update_state",
            action_params={
                "key": "offset",
                "formula": "(state_offset or 0) + (state_last_pulses * pulses_factor / 1000)",
            },
        )
        # total = raw_m3 + offset
        ProcessingRule.objects.create(
            step=step,
            order=2,
            condition="",
            action="set_output",
            action_params={
                "output": "total",
                "formula": "(value * pulses_factor / 1000) + (state_offset or 0)",
            },
        )
        # Guardar last_pulses y last_total.
        ProcessingRule.objects.create(
            step=step,
            order=3,
            condition="",
            action="update_state",
            action_params={"key": "last_pulses", "formula": "value"},
        )
        ProcessingRule.objects.create(
            step=step,
            order=4,
            condition="",
            action="update_state",
            action_params={
                "key": "last_total",
                "formula": "(value * pulses_factor / 1000) + (state_offset or 0)",
            },
        )

        DeviceVariableConfig.objects.create(
            device=self.device,
            source_variable="pulses",
            internal_variable="pulses",
            processing_type="stateful",
            custom_schema=schema,
            pulses_factor=1000,
        )

        # 10 pulsos -> 10 m3
        raw1 = RawReading.objects.create(
            device=self.device,
            variable="pulses",
            source_variable="pulses",
            timestamp=timezone.now(),
            raw_value="10",
        )
        processed1 = PipelineService().process_reading(raw1)
        self.assertEqual(processed1.total, Decimal("10.000"))

        # Reset parcial: 3 pulsos. Offset += 10 -> offset=10. Total = 3 + 10 = 13.
        raw2 = RawReading.objects.create(
            device=self.device,
            variable="pulses",
            source_variable="pulses",
            timestamp=timezone.now(),
            raw_value="3",
        )
        processed2 = PipelineService().process_reading(raw2)
        self.assertEqual(processed2.total, Decimal("13.000"))

        state = DeviceVariableState.objects.get(device=self.device, variable="pulses")
        self.assertEqual(Decimal(state.state["offset"]), Decimal("10"))
        self.assertEqual(Decimal(state.state["last_pulses"]), Decimal("3"))

    def test_totalizer_ruleset_basic_flow(self):
        """El helper create_totalizer_schema produce totales monotónicos."""
        schema = create_totalizer_schema(name="Totalizador test")
        DeviceVariableConfig.objects.create(
            device=self.device,
            source_variable="pulses",
            internal_variable="pulses",
            processing_type="stateful",
            custom_schema=schema,
            pulses_factor=1000,
        )

        base_ts = timezone.now()
        readings = [
            ("10", base_ts),                          # 10 m3
            ("15", base_ts + timedelta(hours=1)),     # +5 m3
            ("0", base_ts + timedelta(hours=2)),      # mantener 15
            ("5", base_ts + timedelta(hours=3)),      # reset parcial: offset += 15 -> total = 20
        ]
        for value, ts in readings:
            raw = RawReading.objects.create(
                device=self.device,
                variable="pulses",
                source_variable="pulses",
                timestamp=ts,
                raw_value=value,
            )
            PipelineService().process_reading(raw)

        state = DeviceVariableState.objects.get(device=self.device, variable="pulses")
        self.assertEqual(Decimal(state.state["offset"]), Decimal("15"))
        self.assertEqual(Decimal(state.state["last_pulses"]), Decimal("5"))

        last = self.device.processed_readings.filter(variable="pulses").order_by("-timestamp").first()
        self.assertIsNotNone(last)
        self.assertEqual(last.total, Decimal("20.000"))

        zero = self.device.processed_readings.filter(
            variable="pulses", raw_reading__raw_value="0"
        ).first()
        self.assertEqual(zero.total, Decimal("15.000"))

    def test_totalizer_schema_is_reused_as_template(self):
        """create_totalizer_schema devuelve la misma plantilla si ya existe."""
        schema1 = create_totalizer_schema()
        schema2 = create_totalizer_schema()
        self.assertEqual(schema1.id, schema2.id)
        self.assertTrue(schema1.is_template)

    def test_apply_totalizer_schema_links_shared_template(self):
        """apply_totalizer_schema asigna la plantilla compartida a dos devices."""
        point2 = Point.objects.create(name="P-Stateful-2")
        device2 = Device.objects.create(point=point2, configuration={"variables": ["pulses"]})

        config1 = apply_totalizer_schema(
            self.device, source_variable="pulses", pulses_factor=1000
        )
        config2 = apply_totalizer_schema(
            device2, source_variable="pulses", pulses_factor=500
        )

        self.assertEqual(config1.processing_type, "stateful")
        self.assertEqual(config2.processing_type, "stateful")
        self.assertEqual(config1.custom_schema, config2.custom_schema)
        self.assertTrue(config1.custom_schema.is_template)
        self.assertEqual(config1.pulses_factor, 1000)
        self.assertEqual(config2.pulses_factor, 500)

        raw = RawReading.objects.create(
            device=device2,
            variable="pulses",
            source_variable="pulses",
            timestamp=timezone.now(),
            raw_value="10",
        )
        processed = PipelineService().process_reading(raw)
        # factor 500 -> (10 * 500) / 1000 = 5 m3
        self.assertEqual(processed.total, Decimal("5.000"))

    def test_totalizer_max_diff_is_configurable(self):
        """El umbral max_diff_m3_per_hour se lee de DeviceVariableConfig."""
        apply_totalizer_schema(
            self.device,
            source_variable="pulses",
            pulses_factor=1000,
            max_diff_m3_per_hour=1,  # muy restrictivo
        )
        base_ts = timezone.now()

        # Primera lectura: 10 m3
        raw1 = RawReading.objects.create(
            device=self.device,
            variable="pulses",
            source_variable="pulses",
            timestamp=base_ts,
            raw_value="10",
        )
        PipelineService().process_reading(raw1)

        # Segunda lectura 1h después: salto de 100 m3 > 1 m3/h -> log de salto masivo pero se acepta.
        raw2 = RawReading.objects.create(
            device=self.device,
            variable="pulses",
            source_variable="pulses",
            timestamp=base_ts + timedelta(hours=1),
            raw_value="110",
        )
        processed2 = PipelineService().process_reading(raw2)
        self.assertEqual(processed2.total, Decimal("110.000"))
        self.assertTrue(
            self.device.events.filter(event_type="massive_jump").exists()
        )

    def test_totalizer_output_field_is_configurable(self):
        """El resultado del totalizador puede guardarse en un campo distinto."""
        apply_totalizer_schema(
            self.device,
            source_variable="pulses",
            output_field="volume",
            pulses_factor=1000,
        )
        raw = RawReading.objects.create(
            device=self.device,
            variable="pulses",
            source_variable="pulses",
            timestamp=timezone.now(),
            raw_value="7",
        )
        processed = PipelineService().process_reading(raw)
        self.assertIsNone(processed.total)
        self.assertEqual(processed.extra_values.get("volume"), "7")

    def test_nivel_schema_corrects_negative_with_historic(self):
        """Nivel negativo se corrige usando el nivel histórico más alto."""
        apply_nivel_schema(
            self.device,
            source_variable="nivel_raw",
            internal_variable="nivel",
            offset=0,
            calculate_nivel=1,
        )

        base_ts = timezone.now()
        # Primera lectura: 10 -> nivel=10, highest=10
        raw1 = RawReading.objects.create(
            device=self.device,
            variable="nivel",
            source_variable="nivel_raw",
            timestamp=base_ts,
            raw_value="10",
        )
        processed1 = PipelineService().process_reading(raw1)
        self.assertEqual(processed1.nivel, Decimal("10.000"))

        # Segunda lectura: -5 -> debe corregirse a highest_nivel=10
        raw2 = RawReading.objects.create(
            device=self.device,
            variable="nivel",
            source_variable="nivel_raw",
            timestamp=base_ts + timedelta(minutes=5),
            raw_value="-5",
        )
        processed2 = PipelineService().process_reading(raw2)
        self.assertEqual(processed2.nivel, Decimal("10.000"))
        self.assertTrue(processed2.extra_values.get("nivel_corrected"))

    def test_nivel_schema_uses_calculate_nivel(self):
        """El divisor calculate_nivel se aplica correctamente."""
        apply_nivel_schema(
            self.device,
            source_variable="nivel_raw",
            internal_variable="nivel",
            offset=0,
            calculate_nivel=10,
        )

        raw = RawReading.objects.create(
            device=self.device,
            variable="nivel",
            source_variable="nivel_raw",
            timestamp=timezone.now(),
            raw_value="50",
        )
        processed = PipelineService().process_reading(raw)
        self.assertEqual(processed.nivel, Decimal("5.000"))

    def test_totalizer_compute_flow(self):
        """El totalizador puede derivar caudal promedio cuando compute_flow=True."""
        apply_totalizer_schema(
            self.device,
            source_variable="pulses",
            pulses_factor=1000,
            compute_flow=True,
        )

        base_ts = timezone.now()
        # 10 m3 a t=0 -> flow=0 (sin anterior)
        raw1 = RawReading.objects.create(
            device=self.device,
            variable="pulses",
            source_variable="pulses",
            timestamp=base_ts,
            raw_value="10",
        )
        processed1 = PipelineService().process_reading(raw1)
        self.assertEqual(processed1.total, Decimal("10.000"))
        self.assertEqual(processed1.flow, Decimal("0.000"))

        # 15 m3 a t=1h -> diff=5 m3 / 3600s * 1000 = 1.388... L/s
        raw2 = RawReading.objects.create(
            device=self.device,
            variable="pulses",
            source_variable="pulses",
            timestamp=base_ts + timedelta(hours=1),
            raw_value="15",
        )
        processed2 = PipelineService().process_reading(raw2)
        self.assertEqual(processed2.total, Decimal("15.000"))
        self.assertAlmostEqual(float(processed2.flow), 5 / 3.6, places=3)
