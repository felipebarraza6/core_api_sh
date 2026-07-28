"""
Tests de regresión para auditoría de telemetría con SystemEvent
===============================================================

Valida que cada anomalía detectada en el procesamiento de telemetría
genere un SystemEvent en la base de datos.
"""

import pytz
from django.test import TestCase
from django.utils import timezone
from datetime import timedelta

from unittest.mock import patch

from django.contrib.auth import get_user_model
from api.core.models import CatchmentPoint, ProjectCatchments, Client
from api.core.models.alerts import SystemEvent
from api.core.models import ProfileDataConfigCatchment, InteractionDetail, SchemesCatchment, Variable

User = get_user_model()
from api.cronjobs.telemetry.utils.audit import emit_system_event
from api.cronjobs.telemetry.controllers.total import total_m3
from api.cronjobs.telemetry.controllers.flow import average_flow
from api.cronjobs.telemetry.controllers.nivel import nivel_mt
from api.cronjobs.telemetry.telemetry_unified import _process_point


class TelemetryAuditTestCase(TestCase):
    """Tests para validar que las anomalías generan SystemEvent."""

    def setUp(self):
        """Crear datos base para tests."""
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client = Client.objects.create(name="Test Client")
        self.project = ProjectCatchments.objects.create(
            name="Test Project", client=self.client
        )
        self.point = CatchmentPoint.objects.create(
            title="Test Point",
            project=self.project,
            owner_user=self.user,
            frecuency=60,
        )
        ProfileDataConfigCatchment.objects.create(
            point_catchment=self.point,
            max_diff_m3_per_hour=500,
            max_flow_ls=150,
        )

    def test_emit_system_event_creates_record(self):
        """El helper emit_system_event debe crear un SystemEvent."""
        emit_system_event(
            event_type="MEASUREMENT_ERROR",
            point_id=self.point.id,
            title="Test event",
            message="This is a test event",
            severity="WARNING",
            extra_data={"test": True},
        )
        event = SystemEvent.objects.filter(point_catchment=self.point).first()
        self.assertIsNotNone(event)
        self.assertEqual(event.event_type, "MEASUREMENT_ERROR")
        self.assertEqual(event.severity, "WARNING")
        self.assertEqual(event.extra_data["test"], True)

    def test_emit_system_event_silences_exceptions(self):
        """El helper no debe lanzar excepciones si falla la BD."""
        # Título demasiado largo (>300) debería truncarse, no fallar
        try:
            emit_system_event(
                event_type="MEASUREMENT_ERROR",
                point_id=self.point.id,
                title="X" * 500,
                message="This is a test event",
                severity="WARNING",
            )
        except Exception:
            self.fail("emit_system_event raised an exception")
        event = SystemEvent.objects.filter(point_catchment=self.point).last()
        self.assertIsNotNone(event)
        self.assertEqual(len(event.title), 300)

    def test_nivel_negativo_creates_system_event(self):
        """nivel_mt con valor negativo debe generar SystemEvent."""
        result = nivel_mt(-215.644, 1.0, point_catchment_id=self.point.id)
        self.assertEqual(result, "00.00")
        event = SystemEvent.objects.filter(
            point_catchment=self.point,
            event_type="MEASUREMENT_ERROR",
        ).first()
        self.assertIsNotNone(event)
        self.assertIn("negativo", event.title.lower())

    def test_nivel_base_invalida_creates_system_event(self):
        """nivel_mt con base inválida debe generar SystemEvent."""
        result = nivel_mt(100, 0, point_catchment_id=self.point.id)
        self.assertEqual(result, "00.00")
        event = SystemEvent.objects.filter(
            point_catchment=self.point,
            event_type="MEASUREMENT_ERROR",
        ).first()
        self.assertIsNotNone(event)
        self.assertIn("base inválida", event.title.lower())

    def test_total_negative_pulses_creates_system_event(self):
        """Pulsos negativos en total_m3 deben generar SystemEvent CRITICAL."""
        point_data = {
            "id": self.point.id,
            "profile_data_config": {"max_diff_m3_per_hour": 500},
        }
        # Sin historial previo, debe retornar 0
        result = total_m3(1000, -10, point_data)
        self.assertEqual(result, 0)
        event = SystemEvent.objects.filter(
            point_catchment=self.point,
            event_type="MEASUREMENT_ERROR",
            severity="CRITICAL",
        ).first()
        self.assertIsNotNone(event)
        self.assertIn("pulsos negativos", event.title.lower())

    def test_emit_system_event_deduplicates_critical(self):
        """SystemEvent CRITICAL duplicado dentro del cooldown no se crea."""
        emit_system_event(
            event_type="API_ERROR",
            point_id=self.point.id,
            title="Getter sin timestamp",
            message="Primera ocurrencia",
            severity="CRITICAL",
        )
        self.assertEqual(
            SystemEvent.objects.filter(
                point_catchment=self.point,
                event_type="API_ERROR",
                severity="CRITICAL",
            ).count(),
            1,
        )

        # Segunda llamada inmediata: debe ser deduplicada
        emit_system_event(
            event_type="API_ERROR",
            point_id=self.point.id,
            title="Getter sin timestamp",
            message="Segunda ocurrencia",
            severity="CRITICAL",
        )
        self.assertEqual(
            SystemEvent.objects.filter(
                point_catchment=self.point,
                event_type="API_ERROR",
                severity="CRITICAL",
            ).count(),
            1,
        )

    def test_emit_system_event_allows_after_cooldown(self):
        """SystemEvent CRITICAL se permite después del cooldown."""
        # Crear un evento y luego forzar su fecha al pasado (>60 min)
        old_event = SystemEvent.objects.create(
            point_catchment=self.point,
            event_type="API_ERROR",
            title="Viejo",
            message="Viejo",
            severity="CRITICAL",
        )
        SystemEvent.objects.filter(id=old_event.id).update(
            created=timezone.now() - timedelta(minutes=61)
        )

        # Nueva llamada: debe crear otro evento porque el anterior expiró
        emit_system_event(
            event_type="API_ERROR",
            point_id=self.point.id,
            title="Nuevo",
            message="Nuevo",
            severity="CRITICAL",
        )
        count = SystemEvent.objects.filter(
            point_catchment=self.point,
            event_type="API_ERROR",
            severity="CRITICAL",
        ).count()
        self.assertEqual(count, 2)

    def test_emit_system_event_no_dedup_for_warning(self):
        """SystemEvent WARNING no se deduplica (solo CRITICAL)."""
        emit_system_event(
            event_type="MEASUREMENT_ERROR",
            point_id=self.point.id,
            title="Warning 1",
            message="Warning 1",
            severity="WARNING",
        )
        emit_system_event(
            event_type="MEASUREMENT_ERROR",
            point_id=self.point.id,
            title="Warning 2",
            message="Warning 2",
            severity="WARNING",
        )
        count = SystemEvent.objects.filter(
            point_catchment=self.point,
            event_type="MEASUREMENT_ERROR",
            severity="WARNING",
        ).count()
        self.assertEqual(count, 2)


    def test_average_flow_negative_diff_returns_zero(self):
        """
        Si el total actual es menor que el anterior (reset no detectado),
        diff_cubics < 0. El bug anterior asignaba diff_cubics = float(total)
        (volumen histórico completo), generando caudal ficticio.
        El fix fuerza diff_cubics = 0.0, retornando caudal 0.0.
        """
        now = timezone.now()
        chile = pytz.timezone("America/Santiago")
        if now.tzinfo is None:
            now = chile.localize(now)
        else:
            now = now.astimezone(chile)

        # Crear registro anterior con total alto
        InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=now - timedelta(hours=1),
            total="1000.0",
            pulses=1000000,
            total_diff=10,
            flow=5.0,
        )

        # El total actual es menor (reset no detectado: contador bajó a 500)
        result = average_flow(
            point_catchment={"id": self.point.id},
            total=500.0,
            date_lg=now,
        )
        self.assertEqual(result, 0.0)

    @patch("api.cronjobs.telemetry.telemetry_unified.get_data_with_retry")
    def test_unified_is_error_only_on_totalizado_failure(self, mock_get_data):
        """
        Si un getter retorna date_time=None y value=0 (fallo de API/sensor),
        is_error=True solo se marca para TOTALIZADO.
        Variables secundarias (NIVEL, CAUDAL) loguean warning pero mantienen
        el registro válido (is_error=False) para no invalidar lecturas por
        fallas parciales de sensores secundarios.
        """
        mock_get_data.return_value = None  # Simula fallo de getter

        # Crear esquema y variable de tipo NIVEL
        scheme = SchemesCatchment.objects.create(
            name="Test Scheme", description="Test"
        )
        scheme.points_catchment.add(self.point)

        Variable.objects.create(
            scheme_catchment=scheme,
            str_variable="nivel_sensor",
            label="Nivel",
            type_variable="NIVEL",
            token_service="dummy_token",
            service="TWIN",
        )

        now = timezone.now()
        chile = pytz.timezone("America/Santiago")
        if now.tzinfo is None:
            now = chile.localize(now)
        else:
            now = now.astimezone(chile)

        # Construir point_data como lo haría el serializer
        point_data = {
            "id": self.point.id,
            "profile_data_config": {
                "token_service": "",
                "scheme": {
                    "name": "Test Scheme",
                    "variables": [
                        {
                            "id": 1,
                            "str_variable": "nivel_sensor",
                            "type_variable": "NIVEL",
                            "token_service": "dummy_token",
                            "service": "TWIN",
                            "pulses_factor": None,
                            "convert_to_lt": False,
                            "calculate_nivel": None,
                            "store_average_flow": True,
                            "min_value": None,
                            "max_value": None,
                            "display_key": None,
                            "provider": None,
                        }
                    ],
                },
                "replicate_on_missing": False,
                "use_transaction_atomic": True,
            },
        }

        _process_point(point_data, now, "60", dry_run=False)

        # Verificar que el InteractionDetail creado tiene is_error=False
        # porque NIVEL es una variable secundaria; solo TOTALIZADO marca is_error=True
        record = InteractionDetail.objects.filter(
            catchment_point=self.point,
            date_time_medition=now.strftime("%Y-%m-%dT%H:00:00"),
        ).first()
        self.assertIsNotNone(record)
        self.assertFalse(record.is_error)
