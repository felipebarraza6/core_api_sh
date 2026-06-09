"""
Tests de regresión para validación min/max sobre valor PROCESADO (P1.7)
========================================================================

Valida que _validate_variable_range reciba el valor procesado (m³, metros, L/s)
en vez del valor crudo (pulsos, raw sensor).
"""

from django.test import TestCase
from django.utils import timezone
from datetime import timedelta

from api.core.models import (
    CatchmentPoint, InteractionDetail, ProfileDataConfigCatchment,
    User, Client, ProjectCatchments
)
from api.cronjobs.telemetry.controllers.unified_processing import process_variable_safely


class ProcessedValidationTests(TestCase):
    """Tests para validación post-procesamiento."""

    def setUp(self):
        self.user = User.objects.create(username="testuser", email="test@example.com")
        self.client = Client.objects.create(name="Test Client")
        self.project = ProjectCatchments.objects.create(name="Test Project", client=self.client)
        self.point = CatchmentPoint.objects.create(
            title="Test Point", owner_user=self.user, project=self.project
        )
        self.profile = ProfileDataConfigCatchment.objects.create(
            point_catchment=self.point,
            is_telemetry=True,
            d3=10.0,
            d5=100.0,
            d6=50.0,
        )
        self.point_catchment_dict = {
            "id": self.point.id,
            "profile_data_config": {
                "d3": 10.0,
                "d5": 100.0,
                "d6": 50.0,
                "nivel_offset": 0,
                "max_diff_m3_per_hour": 500,
                "max_flow_ls": 150,
            }
        }

    def test_totalizado_validates_processed_not_raw(self):
        """
        TOTALIZADO: 5 pulsos * factor 1000 / 1000 = 5 m³.
        min_value=10 m³ → debe marcar is_error=True porque 5 < 10.
        Si validara raw, 5 > 10 fallaría (bug anterior validaba pulsos, no m³).
        """
        # Preparar historial para que total_m3 no falle
        InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=timezone.now() - timedelta(hours=1),
            total="0",
            pulses=0,
            total_diff=0,
            flow=0.0,
        )

        data = {"value": 5, "date_time": "2025-01-01T10:00:00"}
        variable = {
            "type_variable": "TOTALIZADO",
            "str_variable": "TOTAL_TEST",
            "pulses_factor": 1000,
            "min_value": 10.0,  # 10 m³ mínimo
            "max_value": None,
        }
        created_register = {"date_time_medition": "2025-01-01T10:00:00"}

        _, created_register = process_variable_safely(
            variable=variable,
            data=data,
            point_catchment=self.point_catchment_dict,
            created_register=created_register,
            medition_str="2025-01-01T10:00:00",
        )

        # El total procesado es 5 m³, que está por debajo del mínimo 10 m³
        self.assertTrue(created_register.get("is_error"), "Debe marcar error porque total=5 < min=10")

    def test_totalizado_processed_within_range(self):
        """
        TOTALIZADO: 15 pulsos * factor 1000 / 1000 = 15 m³.
        min_value=10, max_value=100 → debe pasar (15 está en rango).
        """
        InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=timezone.now() - timedelta(hours=1),
            total="0",
            pulses=0,
            total_diff=0,
            flow=0.0,
        )

        data = {"value": 15, "date_time": "2025-01-01T10:00:00"}
        variable = {
            "type_variable": "TOTALIZADO",
            "str_variable": "TOTAL_TEST",
            "pulses_factor": 1000,
            "min_value": 10.0,
            "max_value": 100.0,
        }
        created_register = {"date_time_medition": "2025-01-01T10:00:00"}

        _, created_register = process_variable_safely(
            variable=variable,
            data=data,
            point_catchment=self.point_catchment_dict,
            created_register=created_register,
            medition_str="2025-01-01T10:00:00",
        )

        self.assertFalse(created_register.get("is_error", False), "No debe marcar error porque total=15 está en rango")

    def test_nivel_validates_processed_not_raw(self):
        """
        NIVEL: raw=50, calculate_nivel=10 → nivel=5.0 mt.
        max_value=3.0 → debe marcar is_error=True porque 5.0 > 3.0.
        """
        data = {"value": 50, "date_time": "2025-01-01T10:00:00"}
        variable = {
            "type_variable": "NIVEL",
            "str_variable": "NIVEL_TEST",
            "calculate_nivel": 10,
            "min_value": None,
            "max_value": 3.0,
        }
        created_register = {"date_time_medition": "2025-01-01T10:00:00"}

        _, created_register = process_variable_safely(
            variable=variable,
            data=data,
            point_catchment=self.point_catchment_dict,
            created_register=created_register,
            medition_str="2025-01-01T10:00:00",
        )

        # 50 / 10 = 5.0 metros > max 3.0
        self.assertTrue(created_register.get("is_error"), "Debe marcar error porque nivel=5.0 > max=3.0")
