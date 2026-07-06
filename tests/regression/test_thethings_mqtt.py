"""
Tests de regresión para el subscriber MQTT de TheThings.io.

Valida que los mensajes MQTT se parseen correctamente, se busque el punto
por token, y se guarde/actualice un InteractionDetail usando la misma lógica
de procesamiento unificado.
"""

import json
from datetime import timedelta

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone

from api.core.models import (
    CatchmentPoint, Client, ProjectCatchments,
    InteractionDetail, ProfileDataConfigCatchment,
    SchemesCatchment, Variable, TelemetryProvider,
)
from void.services.mqtt_thethings import (
    _parse_payload,
    _to_iso_datetime,
    _truncate_meditation,
    _lookup_point_by_token,
    _save_mqtt_measurement,
)

User = get_user_model()


class TheThingsMQTTParsingTests(TestCase):
    """Tests para funciones puras de parseo."""

    def test_parse_payload_with_values_key(self):
        """Parsea payload con estructura {'values': [...]}."""
        payload = json.dumps({
            "values": [
                {"key": "total", "value": 123, "datetime": "2026-07-06T14:30:00.000Z"},
            ]
        }).encode("utf-8")
        result = _parse_payload(payload)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["key"], "total")
        self.assertEqual(result[0]["value"], 123)

    def test_parse_payload_array(self):
        """Parsea payload que es un array directo."""
        payload = json.dumps([
            {"key": "nivel", "value": 12.5, "datetime": "2026-07-06T14:30:00.000Z"},
        ]).encode("utf-8")
        result = _parse_payload(payload)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["key"], "nivel")

    def test_parse_payload_invalid_json(self):
        """Payload inválido retorna lista vacía sin crash."""
        result = _parse_payload(b"not json")
        self.assertEqual(result, [])

    def test_to_iso_datetime(self):
        """Convierte datetime de TheThings.io al formato interno."""
        self.assertEqual(
            _to_iso_datetime("2026-07-06T14:30:00.000Z"),
            "2026-07-06T14:30:00",
        )
        self.assertEqual(
            _to_iso_datetime("2026-07-06T14:30:00Z"),
            "2026-07-06T14:30:00",
        )

    def test_truncate_meditation(self):
        """Trunca timestamp al slot según frecuencia."""
        self.assertEqual(
            _truncate_meditation("2026-07-06T14:30:25", "60"),
            "2026-07-06T14:00:00",
        )
        self.assertEqual(
            _truncate_meditation("2026-07-06T14:30:25", "1"),
            "2026-07-06T14:30:00",
        )


class TheThingsMQTTProcessingTests(TestCase):
    """Tests de procesamiento y guardado en BD."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='mqtt_test_user', password='testpass', email='mqtt@example.com'
        )
        self.client_obj = Client.objects.create(name="MQTT Test Client")
        self.project = ProjectCatchments.objects.create(
            name="MQTT Test Project", client=self.client_obj
        )
        self.provider = TelemetryProvider.objects.create(
            name="TheThings Test",
            handler_name="thethings",
            protocol="MQTT",
            is_active=True,
        )
        self.point = CatchmentPoint.objects.create(
            title="MQTT Test Point",
            owner_user=self.user,
            project=self.project,
            frecuency="60",
            is_thethings=True,
            telemetry_provider=self.provider,
        )
        self.profile = ProfileDataConfigCatchment.objects.create(
            point_catchment=self.point,
            is_telemetry=True,
            token_service="TOKEN_MQTT_TEST",
            d1=10.0,
            d3=5.0,
            nivel_offset=0.0,
            addition=0.0,
            disable_thethings_polling=False,
        )
        self.scheme = SchemesCatchment.objects.create(
            name="MQTT Test Scheme", description="Test"
        )
        self.scheme.points_catchment.add(self.point)

        self.var_total = Variable.objects.create(
            scheme_catchment=self.scheme,
            str_variable="pulsos",
            label="Totalizador",
            type_variable="TOTALIZADO",
            pulses_factor=1000,
            provider=self.provider,
        )
        self.var_nivel = Variable.objects.create(
            scheme_catchment=self.scheme,
            str_variable="nivel",
            label="Nivel",
            type_variable="NIVEL",
            calculate_nivel=2,
            provider=self.provider,
        )

    def test_lookup_point_by_token_profile(self):
        """Encuentra punto usando token del profile."""
        point = _lookup_point_by_token("TOKEN_MQTT_TEST")
        self.assertEqual(point, self.point)

    def test_lookup_point_by_token_variable(self):
        """Fallback: encuentra punto usando token de variable."""
        self.profile.token_service = ""
        self.profile.save()
        self.var_total.token_service = "TOKEN_VAR_FALLBACK"
        self.var_total.save()
        point = _lookup_point_by_token("TOKEN_VAR_FALLBACK")
        self.assertEqual(point, self.point)

    def test_lookup_point_by_token_not_found(self):
        """Token inexistente retorna None."""
        self.assertIsNone(_lookup_point_by_token("TOKEN_INEXISTENTE"))

    def test_save_mqtt_measurement_creates_record(self):
        """Un mensaje MQTT con total y nivel crea un InteractionDetail."""
        from api.core.serializers import CatchmentPointSerializerDetailCron

        point_data = CatchmentPointSerializerDetailCron(self.point).data
        values = [
            {"key": "pulsos", "value": 150, "datetime": "2026-07-06T14:30:00.000Z"},
            {"key": "nivel", "value": 3.5, "datetime": "2026-07-06T14:30:00.000Z"},
        ]

        result = _save_mqtt_measurement(point_data, "TOKEN_MQTT_TEST", values)
        self.assertTrue(result)

        record = InteractionDetail.objects.get(
            catchment_point=self.point,
            date_time_medition="2026-07-06T14:00:00",
        )
        self.assertEqual(record.pulses, 150)
        self.assertEqual(record.total, "150")
        self.assertEqual(float(record.nivel), 1.75)  # 3.5 / calculate_nivel(2)
        self.assertEqual(record.variable_values, {
            str(self.var_total.id): 150,
            str(self.var_nivel.id): 3.5,
        })
        self.assertEqual(
            record.date_time_last_logger.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
            "2026-07-06T14:30:00"
        )

    def test_save_mqtt_measurement_updates_existing_record(self):
        """Múltiples mensajes en el mismo slot horario actualizan el mismo registro."""
        from api.core.serializers import CatchmentPointSerializerDetailCron

        point_data = CatchmentPointSerializerDetailCron(self.point).data

        # Primer mensaje: solo total
        _save_mqtt_measurement(
            point_data,
            "TOKEN_MQTT_TEST",
            [{"key": "pulsos", "value": 100, "datetime": "2026-07-06T14:20:00.000Z"}],
        )

        # Segundo mensaje: solo nivel (mismo slot horario)
        _save_mqtt_measurement(
            point_data,
            "TOKEN_MQTT_TEST",
            [{"key": "nivel", "value": 4.0, "datetime": "2026-07-06T14:40:00.000Z"}],
        )

        records = InteractionDetail.objects.filter(catchment_point=self.point)
        self.assertEqual(records.count(), 1)

        record = records.first()
        self.assertEqual(record.pulses, 100)
        self.assertEqual(float(record.nivel), 2.0)  # 4.0 / 2

    def test_save_mqtt_measurement_ignores_unknown_variable(self):
        """Variables no configuradas se ignoran pero no fallan."""
        from api.core.serializers import CatchmentPointSerializerDetailCron

        point_data = CatchmentPointSerializerDetailCron(self.point).data
        values = [
            {"key": "temperatura", "value": 25, "datetime": "2026-07-06T14:30:00.000Z"},
        ]

        result = _save_mqtt_measurement(point_data, "TOKEN_MQTT_TEST", values)
        self.assertFalse(result)
        self.assertFalse(
            InteractionDetail.objects.filter(catchment_point=self.point).exists()
        )


class TheThingsMQTTPollingFilterTests(TestCase):
    """Tests para el filtro de polling unificado."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='filter_test_user', password='testpass', email='filter@example.com'
        )
        self.client_obj = Client.objects.create(name="Filter Test Client")
        self.project = ProjectCatchments.objects.create(
            name="Filter Test Project", client=self.client_obj
        )
        self.provider = TelemetryProvider.objects.create(
            name="TheThings Filter",
            handler_name="thethings",
            protocol="MQTT",
            is_active=True,
        )
        self.point = CatchmentPoint.objects.create(
            title="Filter Test Point",
            owner_user=self.user,
            project=self.project,
            frecuency="60",
            is_thethings=True,
            telemetry_provider=self.provider,
        )
        self.profile = ProfileDataConfigCatchment.objects.create(
            point_catchment=self.point,
            is_telemetry=True,
            token_service="TOKEN_FILTER",
            disable_thethings_polling=True,
        )
        self.scheme = SchemesCatchment.objects.create(name="Filter Scheme")
        self.scheme.points_catchment.add(self.point)
        Variable.objects.create(
            scheme_catchment=self.scheme,
            str_variable="pulsos",
            type_variable="TOTALIZADO",
            provider=self.provider,
        )

    def test_unified_run_excludes_disabled_thethings_polling(self):
        """Punto con disable_thethings_polling=True no es procesado por el cron unificado."""
        from unittest.mock import patch
        from api.cronjobs.telemetry.telemetry_unified import run

        with patch("api.cronjobs.telemetry.telemetry_unified._process_point") as mock_process:
            run(frequency="60", point_type="thethings")
            mock_process.assert_not_called()
