"""
Tests de regresión para el getter universal de telemetría.

Valida que get_data_universal despache correctamente a cada handler
(tdata, thethings, tago, generic_json) y que el fallback legacy funcione.
"""
from django.test import TestCase
from unittest.mock import patch, MagicMock
import json

from api.cronjobs.telemetry.getters.universal import get_data_universal
from api.cronjobs.telemetry.getters.generic import get_data_generic


class TelemetryProviderDispatchTests(TestCase):
    """Tests para validar el dispatcher universal."""

    def test_fallback_tdata_when_no_provider(self):
        """Si provider es None, debe hacer fallback a get_data_tdata."""
        with patch("api.cronjobs.telemetry.getters.universal.get_data_tdata") as mock_tdata:
            mock_tdata.return_value = {"value": 42, "date_time": "2025-01-01T10:00:00"}

            result = get_data_universal(None, "TOKEN_123", "pulsos")

            mock_tdata.assert_called_once_with(None, "TOKEN_123", "pulsos")
            self.assertEqual(result["value"], 42)

    def test_dispatch_tdata(self):
        """Provider con handler_name='tdata' debe llamar get_data_tdata."""
        provider = {"handler_name": "tdata", "base_url": "https://api.example.com"}

        with patch("api.cronjobs.telemetry.getters.universal.get_data_tdata") as mock_tdata:
            mock_tdata.return_value = {"value": 100, "date_time": "2025-01-01T10:00:00"}

            result = get_data_universal(provider, "DEV_001", "variable_x")

            mock_tdata.assert_called_once_with(provider, "DEV_001", "variable_x")
            self.assertEqual(result["value"], 100)

    def test_dispatch_thethings(self):
        """Provider con handler_name='thethings' debe llamar get_data_thethings."""
        provider = {"handler_name": "thethings", "base_url": "https://api.thethings.io/v2"}

        with patch("api.cronjobs.telemetry.getters.universal.get_data_thethings") as mock_things:
            mock_things.return_value = {"value": 50, "date_time": "2025-01-01T10:00:00"}

            result = get_data_universal(provider, "THING_01", "temperature")

            mock_things.assert_called_once_with(provider, "THING_01", "temperature")
            self.assertEqual(result["value"], 50)

    def test_dispatch_tago(self):
        """Provider con handler_name='tago' debe llamar get_data_tago."""
        provider = {"handler_name": "tago", "base_url": "https://api.tago.io"}

        with patch("api.cronjobs.telemetry.getters.universal.get_data_tago") as mock_tago:
            mock_tago.return_value = {"value": 99.5, "date_time": "2025-01-01T10:00:00"}

            result = get_data_universal(provider, "TAGO_DEV", "flow")

            mock_tago.assert_called_once_with(provider, "TAGO_DEV", "flow")
            self.assertEqual(result["value"], 99.5)

    def test_dispatch_generic_json(self):
        """Provider con handler_name='generic_json' debe llamar get_data_generic."""
        provider = {
            "handler_name": "generic_json",
            "base_url": "https://generic.api.com",
            "parser_config": {
                "value_field": "data.value",
                "timestamp_field": "data.ts",
                "timestamp_format": "iso8601",
            },
        }

        with patch("api.cronjobs.telemetry.getters.universal.get_data_generic") as mock_generic:
            mock_generic.return_value = {"value": 77, "date_time": "2025-01-01T10:00:00"}

            result = get_data_universal(provider, "GEN_01", "metric")

            mock_generic.assert_called_once_with(provider, "GEN_01", "metric")
            self.assertEqual(result["value"], 77)

    def test_unknown_handler_defaults_to_generic(self):
        """Un handler desconocido debe caer en get_data_generic por defecto."""
        provider = {"handler_name": "future_handler_v2"}

        with patch("api.cronjobs.telemetry.getters.universal.get_data_generic") as mock_generic:
            mock_generic.return_value = {"value": 0, "date_time": None}

            result = get_data_universal(provider, "DEV", "var")

            mock_generic.assert_called_once()
            self.assertEqual(result, {"value": 0, "date_time": None})

    def test_all_handlers_dispatch_correctly(self):
        """Validar que todos los handlers conocidos se despachan sin error (con mocks)."""
        handlers = ["tdata", "thethings", "tago", "generic_json"]
        for handler in handlers:
            with self.subTest(handler=handler):
                provider = {"handler_name": handler}
                with patch("api.cronjobs.telemetry.getters.universal.get_data_tdata") as mock_tdata, \
                     patch("api.cronjobs.telemetry.getters.universal.get_data_thethings") as mock_things, \
                     patch("api.cronjobs.telemetry.getters.universal.get_data_tago") as mock_tago, \
                     patch("api.cronjobs.telemetry.getters.universal.get_data_generic") as mock_generic:
                    mock_tdata.return_value = {"value": 1}
                    mock_things.return_value = {"value": 2}
                    mock_tago.return_value = {"value": 3}
                    mock_generic.return_value = {"value": 4}
                    result = get_data_universal(provider, "TOK", "VAR")
                    self.assertIn("value", result)


class GenericGetterTests(TestCase):
    """Tests para el parser JSON genérico configurable."""

    @patch("api.cronjobs.telemetry.getters.generic.requests.get")
    def test_generic_parses_nested_json(self, mock_get):
        """Parser debe navegar paths anidados y extraer valor + timestamp."""
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "result": {
                "items": [
                    {
                        "sensor": {"reading": 123.45},
                        "meta": {"created": "2025-06-15T14:30:00+00:00"},
                    }
                ]
            }
        }
        mock_get.return_value = mock_response

        provider = {
            "base_url": "https://api.example.com",
            "endpoint_template": "/devices/{token}/vars/{variable}",
            "auth_type": "NONE",
            "timeout_seconds": 5,
            "retry_attempts": 1,
            "parser_config": {
                "response_root_key": "result.items.0",
                "value_field": "sensor.reading",
                "timestamp_field": "meta.created",
                "timestamp_format": "iso8601",
            },
        }

        result = get_data_generic(provider, "DEV_01", "temp")

        self.assertEqual(result["value"], 123.45)
        self.assertEqual(result["date_time"], "2025-06-15T14:30:00")
        mock_get.assert_called_once()

    @patch("api.cronjobs.telemetry.getters.generic.requests.get")
    def test_generic_handles_array_response(self, mock_get):
        """Parser debe manejar respuesta array con response_is_array."""
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = [
            {"value": 999, "ts": 1718455800000},  # epoch_ms
        ]
        mock_get.return_value = mock_response

        provider = {
            "base_url": "https://api.array.com",
            "auth_type": "NONE",
            "timeout_seconds": 5,
            "retry_attempts": 1,
            "parser_config": {
                "response_is_array": True,
                "response_array_index": 0,
                "value_field": "value",
                "timestamp_field": "ts",
                "timestamp_format": "epoch_ms",
            },
        }

        result = get_data_generic(provider, "TOK", "var")

        self.assertEqual(result["value"], 999)
        self.assertIsNotNone(result["date_time"])

    @patch("api.cronjobs.telemetry.getters.generic.requests.get")
    def test_generic_returns_zero_on_missing_value(self, mock_get):
        """Si el campo value no existe, debe retornar value=0."""
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"other": "field"}
        mock_get.return_value = mock_response

        provider = {
            "base_url": "https://api.empty.com",
            "auth_type": "NONE",
            "timeout_seconds": 5,
            "retry_attempts": 1,
            "parser_config": {
                "value_field": "value",
            },
        }

        result = get_data_generic(provider, "TOK", "var")

        self.assertEqual(result["value"], 0)
        self.assertIsNone(result["date_time"])
