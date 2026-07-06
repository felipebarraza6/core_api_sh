"""Flujo completo de ejemplo: proveedor Unipapel, punto P100, solo totalizado."""
from datetime import timedelta
from decimal import Decimal

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from void.models import Device, Point, Provider
from void.services.handlers.stateful_rulesets import apply_totalizer_schema


class UnipapelP100FlowTests(TestCase):
    """Valida el prototipo void con un caso realista de cliente."""

    def setUp(self):
        self.client = Client()

        # 1. Proveedor de telemetría para Unipapel.
        self.provider = Provider.objects.create(
            name="Unipapel",
            protocol="HTTP_REST",
            auth_type="API_KEY_HEADER",
            base_url="https://ingesta.unipapel.smarthydro.cl",
            auth_config={"api_key": "unipapel-api-key", "header_name": "X-API-Key"},
            metadata={"default_format": "json"},
        )

        # 2. Punto de captación P100.
        self.point = Point.objects.create(
            name="P100 - Captación Río Principal",
            code_internal="UNIPAPEL-P100",
            client="Unipapel",
            project="Planta Valdivia",
            frequency_minutes=60,
            constants={"d1": "0", "d2": "0", "d3": "0"},
        )

        # 3. Device asociado con token de ingesta.
        self.device = Device.objects.create(
            point=self.point,
            provider=self.provider,
            serial_number="UNI-LOGGER-P100",
            external_id="unipapel_p100",
            model="Novus FieldLogger 1000",
            configuration={
                "ingest_token": "tok-unipapel-p100",
                "variables": ["pulses"],
            },
        )

        # 4. Configuración stateful de totalizador.
        apply_totalizer_schema(
            device=self.device,
            source_variable="pulses",
            internal_variable="pulses",
            output_field="total",
            pulses_factor=1000,
            max_diff_m3_per_hour=500,
            reconnection_threshold_hours=2,
        )

    def _ingest(self, value, timestamp, source_variable="pulses"):
        """Helper que simula una llamada al endpoint de ingesta."""
        response = self.client.post(
            reverse("void:ingest"),
            data={
                "serial_number": self.device.serial_number,
                "source_variable": source_variable,
                "value": str(value),
                "timestamp": timestamp.isoformat().replace("+00:00", "Z"),
            },
            content_type="application/json",
            HTTP_X_DEVICE_TOKEN="tok-unipapel-p100",
        )
        self.assertEqual(response.status_code, 201, response.json())
        return response.json()

    def test_flujo_totalizacion_basica(self):
        """Secuencia normal de pulsos: acumulación monotónica."""
        base = timezone.now()

        r1 = self._ingest(100, base)
        self.assertEqual(r1["total"], "100.000")

        r2 = self._ingest(250, base + timedelta(hours=1))
        self.assertEqual(r2["total"], "250.000")

        r3 = self._ingest(400, base + timedelta(hours=2))
        self.assertEqual(r3["total"], "400.000")

    def test_flujo_reset_parcial(self):
        """El contador se reinicia parcialmente: se compensa con offset."""
        base = timezone.now()

        self._ingest(1000, base)
        self._ingest(1100, base + timedelta(hours=1))

        # Reset parcial: de 1100 baja a 200. Offset += 1100 -> total = 1300.
        r = self._ingest(200, base + timedelta(hours=2))
        self.assertEqual(r["total"], "1300.000")

    def test_flujo_pulsos_cero(self):
        """Pulsos en cero mantienen el último total."""
        base = timezone.now()

        self._ingest(500, base)
        self._ingest(0, base + timedelta(hours=1))

        processed = self.device.processed_readings.filter(
            variable="pulses", raw_reading__raw_value="0"
        ).first()
        self.assertIsNotNone(processed)
        self.assertEqual(processed.total, Decimal("500.000"))

    def test_flujo_salto_masivo_detectado(self):
        """Un salto mayor al máximo permitido genera evento pero se acepta."""
        base = timezone.now()

        self._ingest(10, base)
        # 1h después: salto de 600 m3 > 500 m3/h -> evento massive_jump.
        r = self._ingest(610, base + timedelta(hours=1))
        self.assertEqual(r["total"], "610.000")
        self.assertTrue(
            self.device.events.filter(event_type="massive_jump").exists()
        )

    def test_flujo_reutiliza_misma_plantilla(self):
        """Otro punto Unipapel reutiliza el schema template."""
        point2 = Point.objects.create(
            name="P101 - Captación Secundaria",
            code_internal="UNIPAPEL-P101",
            client="Unipapel",
        )
        device2 = Device.objects.create(
            point=point2,
            provider=self.provider,
            serial_number="UNI-LOGGER-P101",
            configuration={"ingest_token": "tok-unipapel-p101", "variables": ["pulses"]},
        )
        apply_totalizer_schema(device2, source_variable="pulses", pulses_factor=1000)

        config1 = self.device.variable_configs.get(source_variable="pulses")
        config2 = device2.variable_configs.get(source_variable="pulses")
        self.assertEqual(config1.custom_schema, config2.custom_schema)
        self.assertTrue(config1.custom_schema.is_template)
