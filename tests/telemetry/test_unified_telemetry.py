"""
Tests para el Sistema Unificado de Telemetría V3.1
Valida la correcta integración de Celery tasks y la lógica unificada
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock
import pytz

from api.core.models import CatchmentPoint, TelemetryRecord, Variable
from api.core.tasks.telemetry import (
    collect_telemetry,
    process_telemetry_batch,
    process_single_point_unified,
    ingest_telemetry_data,
    get_data_with_retry,
)


@pytest.fixture
def mock_catchment_point():
    """Crea un punto de captación de prueba"""
    point = Mock(spec=CatchmentPoint)
    point.id = 123
    point.title = "Pozo Test"
    point.frecuency = "5"
    return point


@pytest.fixture
def mock_profile_config():
    """Configuración de perfil de prueba"""
    return {
        "token_service": "test_token_12345",
        "scheme": {
            "variables": [
                {
                    "str_variable": "flow_sensor_1",
                    "type_variable": "CAUDAL",
                    "service": "TWIN",
                    "token_service": None,
                },
                {
                    "str_variable": "level_sensor_1",
                    "type_variable": "NIVEL",
                    "service": "TWIN",
                    "token_service": None,
                },
            ]
        },
    }


@pytest.fixture
def mock_telemetry_data():
    """Datos de telemetría de prueba"""
    return {"value": 125.5, "date_time": "2026-01-17T15:30:00"}


class TestCollectTelemetry:
    """Tests para el task principal collect_telemetry"""

    @patch("api.core.tasks.telemetry.CatchmentPoint")
    @patch("api.core.tasks.telemetry.process_telemetry_batch")
    def test_collect_telemetry_no_points(self, mock_batch, mock_cp_model):
        """Debe retornar sin error cuando no hay puntos configurados"""
        # Simular que no hay puntos para la frecuencia
        mock_cp_model.objects.filter.return_value.select_related.return_value.distinct.return_value.count.return_value = (
            0
        )
        mock_cp_model.objects.filter.return_value.select_related.return_value.distinct.return_value.exists.return_value = (
            False
        )

        result = collect_telemetry("5")

        assert result["status"] == "completed"
        assert result["points_processed"] == 0
        assert result["frequency"] == "5"

    @patch("api.core.tasks.telemetry.CatchmentPoint")
    @patch("api.core.tasks.telemetry.group")
    def test_collect_telemetry_with_points(self, mock_group, mock_cp_model):
        """Debe crear batches y dispatcharlos cuando hay puntos"""
        # Simular 25 puntos (2 batches)
        mock_queryset = MagicMock()
        mock_queryset.count.return_value = 25
        mock_queryset.values_list.return_value = list(range(1, 26))

        mock_cp_model.objects.filter.return_value.select_related.return_value.distinct.return_value = (
            mock_queryset
        )

        mock_job = Mock()
        mock_group.return_value = mock_job

        result = collect_telemetry("5")

        assert result["status"] == "dispatched"
        assert result["points_count"] == 25
        assert result["frequency"] == "5"
        assert result["batches"] == 2  # 25 puntos / 20 batch_size = 2 batches
        mock_job.apply_async.assert_called_once()

    def test_collect_telemetry_different_frequencies(self):
        """Debe manejar diferentes frecuencias correctamente"""
        frequencies = ["1", "5", "10", "60"]

        for freq in frequencies:
            with patch("api.core.tasks.telemetry.CatchmentPoint") as mock_cp:
                mock_cp.objects.filter.return_value.select_related.return_value.distinct.return_value.count.return_value = (
                    0
                )
                result = collect_telemetry(freq)
                assert result["frequency"] == freq


class TestProcessTelemetryBatch:
    """Tests para process_telemetry_batch"""

    @patch("api.core.tasks.telemetry.process_single_point_unified")
    def test_process_batch_all_success(self, mock_process_point):
        """Debe procesar todos los puntos exitosamente"""
        mock_process_point.return_value = True
        point_ids = [1, 2, 3, 4, 5]

        result = process_telemetry_batch(point_ids, "5")

        assert result["processed"] == 5
        assert result["errors"] == 0
        assert result["batch_size"] == 5
        assert mock_process_point.call_count == 5

    @patch("api.core.tasks.telemetry.process_single_point_unified")
    def test_process_batch_with_errors(self, mock_process_point):
        """Debe manejar errores en puntos individuales"""
        # Simular 3 éxitos y 2 fallos
        mock_process_point.side_effect = [True, False, True, False, True]
        point_ids = [1, 2, 3, 4, 5]

        result = process_telemetry_batch(point_ids, "5")

        assert result["processed"] == 3
        assert result["errors"] == 2
        assert result["batch_size"] == 5

    @patch("api.core.tasks.telemetry.process_single_point_unified")
    def test_process_batch_handles_exceptions(self, mock_process_point):
        """Debe capturar excepciones y continuar procesando"""
        # Simular que el punto 2 lanza excepción
        mock_process_point.side_effect = [
            True,
            Exception("API timeout"),
            True,
            True,
            True,
        ]
        point_ids = [1, 2, 3, 4, 5]

        result = process_telemetry_batch(point_ids, "5")

        assert result["processed"] == 4
        assert result["errors"] == 1


class TestProcessSinglePointUnified:
    """Tests para process_single_point_unified"""

    @patch("api.core.tasks.telemetry.ingest_telemetry_data")
    @patch("api.core.tasks.telemetry.TelemetryCache")
    @patch("api.core.tasks.telemetry.CatchmentPoint")
    @patch("api.core.tasks.telemetry.CatchmentPointSerializerDetailCron")
    def test_process_point_success(
        self, mock_serializer, mock_cp_model, mock_cache, mock_ingest
    ):
        """Debe procesar un punto exitosamente"""
        # Setup mocks
        mock_point = Mock()
        mock_point.id = 123
        mock_cp_model.objects.select_related.return_value.get.return_value = (
            mock_point
        )

        mock_serializer.return_value.data = {
            "id": 123,
            "profile_data_config": {
                "token_service": "test_token",
                "scheme": {"variables": [{"str_variable": "test"}]},
            },
        }

        mock_ingest.return_value = True

        result = process_single_point_unified(123, "5")

        assert result is True
        mock_ingest.assert_called_once()
        mock_cache.invalidate_point_cache.assert_called_once_with(123)

    @patch("api.core.tasks.telemetry.CatchmentPoint")
    def test_process_point_not_found(self, mock_cp_model):
        """Debe manejar puntos que no existen"""
        mock_cp_model.objects.select_related.return_value.get.side_effect = (
            CatchmentPoint.DoesNotExist
        )

        result = process_single_point_unified(999, "5")

        assert result is False

    @patch("api.core.tasks.telemetry.CatchmentPoint")
    @patch("api.core.tasks.telemetry.CatchmentPointSerializerDetailCron")
    def test_process_point_missing_config(self, mock_serializer, mock_cp_model):
        """Debe retornar False si falta configuración"""
        mock_point = Mock()
        mock_cp_model.objects.select_related.return_value.get.return_value = (
            mock_point
        )

        # Sin variables o sin token
        mock_serializer.return_value.data = {
            "id": 123,
            "profile_data_config": {
                "token_service": None,  # ← Sin token
                "scheme": {"variables": []},
            },
        }

        result = process_single_point_unified(123, "5")

        assert result is False


class TestIngestTelemetryData:
    """Tests para ingest_telemetry_data"""

    @patch("api.core.tasks.telemetry.save_telemetry_data")
    @patch("api.core.tasks.telemetry.determine_dga_send")
    @patch("api.core.tasks.telemetry.process_variable_safely")
    @patch("api.core.tasks.telemetry.get_data_with_retry")
    def test_ingest_basic_flow(
        self, mock_get_data, mock_process_var, mock_determine_dga, mock_save
    ):
        """Debe ingestar datos básicos correctamente"""
        # Setup
        variables = [
            {
                "str_variable": "flow_sensor",
                "type_variable": "CAUDAL",
                "service": "TWIN",
            }
        ]
        token = "test_token"
        point_catchment = {"id": 123}

        mock_get_data.return_value = {"value": 100.5, "date_time": "2026-01-17T15:30:00"}
        mock_process_var.return_value = (None, {"flow": 100.5})
        mock_determine_dga.return_value = True

        result = ingest_telemetry_data(variables, token, point_catchment, "5")

        assert result is True
        mock_save.assert_called_once()
        call_args = mock_save.call_args[0]
        assert call_args[0] == 123  # point_id
        assert call_args[1]["send_dga"] is True

    @patch("api.core.tasks.telemetry.get_data_with_retry")
    def test_ingest_skip_caudal_promedio(self, mock_get_data):
        """Debe saltar variables de tipo CAUDAL_PROMEDIO"""
        variables = [
            {
                "str_variable": "calculated_flow",
                "type_variable": "CAUDAL_PROMEDIO",  # ← Se calcula, no se pide
                "service": "TWIN",
            }
        ]
        token = "test_token"
        point_catchment = {"id": 123}

        ingest_telemetry_data(variables, token, point_catchment, "5")

        # No debe llamar al getter para CAUDAL_PROMEDIO
        mock_get_data.assert_not_called()

    @patch("api.core.tasks.telemetry.get_data_with_retry")
    def test_ingest_no_valid_data(self, mock_get_data):
        """Debe retornar False si no hay datos válidos"""
        variables = [{"str_variable": "test", "type_variable": "CAUDAL", "service": "TWIN"}]
        token = "test_token"
        point_catchment = {"id": 123}

        # Simular que no hay datos
        mock_get_data.return_value = None

        result = ingest_telemetry_data(variables, token, point_catchment, "5")

        assert result is False

    def test_ingest_timestamp_format_hourly(self):
        """Debe formatear timestamp correctamente para frecuencia 60"""
        with patch("api.core.tasks.telemetry.get_data_with_retry") as mock_get_data:
            with patch(
                "api.core.tasks.telemetry.process_variable_safely"
            ) as mock_process:
                with patch("api.core.tasks.telemetry.save_telemetry_data") as mock_save:
                    with patch("api.core.tasks.telemetry.determine_dga_send"):
                        mock_get_data.return_value = {"value": 100, "date_time": None}
                        mock_process.return_value = (None, {})

                        variables = [
                            {
                                "str_variable": "test",
                                "type_variable": "CAUDAL",
                                "service": "TWIN",
                            }
                        ]

                        ingest_telemetry_data(variables, "token", {"id": 123}, "60")

                        # Verificar que el timestamp tiene formato :00:00
                        call_args = mock_save.call_args[0][1]
                        timestamp = call_args["date_time_medition"]
                        assert timestamp.endswith(":00:00")


class TestGetDataWithRetry:
    """Tests para get_data_with_retry"""

    @patch("api.core.tasks.telemetry.get_data_tdata")
    def test_retry_success_first_attempt(self, mock_getter):
        """Debe retornar datos en el primer intento"""
        mock_getter.return_value = {"value": 100, "date_time": "2026-01-17T15:30:00"}

        result = get_data_with_retry("TWIN", "token", "sensor_1")

        assert result["value"] == 100
        assert mock_getter.call_count == 1

    @patch("api.core.tasks.telemetry.get_data_tdata")
    @patch("api.core.tasks.telemetry.time.sleep")
    def test_retry_success_after_failures(self, mock_sleep, mock_getter):
        """Debe reintentar y eventualmente tener éxito"""
        # Fallar 2 veces, luego éxito
        mock_getter.side_effect = [
            None,
            None,
            {"value": 100, "date_time": "2026-01-17T15:30:00"},
        ]

        result = get_data_with_retry("TWIN", "token", "sensor_1")

        assert result["value"] == 100
        assert mock_getter.call_count == 3
        assert mock_sleep.call_count == 2  # Sleep entre intentos

    @patch("api.core.tasks.telemetry.get_data_tdata")
    @patch("api.core.tasks.telemetry.time.sleep")
    def test_retry_max_retries_exceeded(self, mock_sleep, mock_getter):
        """Debe retornar None después de max_retries"""
        mock_getter.return_value = None  # Siempre falla

        result = get_data_with_retry("TWIN", "token", "sensor_1", max_retries=3)

        assert result is None
        assert mock_getter.call_count == 3

    @patch("api.core.tasks.telemetry.get_data_thethings")
    def test_retry_service_mapping_nettra(self, mock_getter):
        """Debe mapear correctamente el servicio NETTRA"""
        mock_getter.return_value = {"value": 100, "date_time": "2026-01-17T15:30:00"}

        get_data_with_retry("NETTRA", "token", "sensor_1")

        mock_getter.assert_called_once_with("token", "sensor_1")

    @patch("api.core.tasks.telemetry.get_data_tago")
    def test_retry_service_mapping_novus(self, mock_getter):
        """Debe mapear correctamente el servicio NOVUS"""
        mock_getter.return_value = {"value": 100, "date_time": "2026-01-17T15:30:00"}

        get_data_with_retry("NOVUS", "token", "sensor_1")

        mock_getter.assert_called_once_with("token", "sensor_1")

    @patch("api.core.tasks.telemetry.get_data_tdata")
    def test_retry_unknown_service_defaults_to_twin(self, mock_getter):
        """Debe usar TWIN como default para servicios desconocidos"""
        mock_getter.return_value = {"value": 100, "date_time": "2026-01-17T15:30:00"}

        get_data_with_retry("UNKNOWN_SERVICE", "token", "sensor_1")

        mock_getter.assert_called_once_with("token", "sensor_1")

    @patch("api.core.tasks.telemetry.get_data_tdata")
    @patch("api.core.tasks.telemetry.time.sleep")
    def test_retry_backoff_timing(self, mock_sleep, mock_getter):
        """Debe usar backoff exponencial entre reintentos"""
        mock_getter.return_value = None

        get_data_with_retry("TWIN", "token", "sensor_1", max_retries=3, backoff_factor=2)

        # Verificar que sleep se llamó con backoff exponencial: 2^0=1, 2^1=2
        assert mock_sleep.call_count == 2
        calls = [call[0][0] for call in mock_sleep.call_args_list]
        assert calls == [1, 2]  # backoff_factor ** attempt


class TestIntegration:
    """Tests de integración end-to-end"""

    @pytest.mark.django_db
    def test_full_telemetry_flow(self):
        """Test de integración completo del flujo de telemetría"""
        # Este test requeriría fixtures de base de datos
        # Lo dejamos como placeholder para implementación futura
        pass


# Markers para categorizar tests
pytestmark = [
    pytest.mark.unit,
    pytest.mark.telemetry,
]
