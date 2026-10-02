"""
Tests de nivel negativo: no inventar máximo histórico.

Ítem 3 auditoría 2026-10-02.
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta

from api.core.models import (
    Client,
    ProjectCatchments,
    CatchmentPoint,
    InteractionDetail,
    ProfileDataConfigCatchment,
    SystemEvent,
)
from api.cronjobs.telemetry.controllers.unified_processing import (
    process_nivel_variable,
)

User = get_user_model()


class NegativeNivelFlaggedTests(TestCase):
    """Nivel negativo se flaggea; no se reemplaza por máximo histórico."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="nivel_user", password="x", email="n@test.com"
        )
        self.client_obj = Client.objects.create(name="Nivel Client")
        self.project = ProjectCatchments.objects.create(
            name="Nivel Project", client=self.client_obj
        )
        self.point = CatchmentPoint.objects.create(
            title="Nivel Point",
            owner_user=self.user,
            project=self.project,
        )
        ProfileDataConfigCatchment.objects.create(
            point_catchment=self.point, is_telemetry=True, d3=40
        )
        # Histórico alto que ANTES se usaba como reemplazo
        InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=timezone.now() - timedelta(days=1),
            nivel=94.00,
            water_table=1.00,
            total="1000",
        )
        self.point_dict = {
            "id": self.point.id,
            "profile_data_config": {
                "d3": 40.0,
                "nivel_offset": 0,
            },
        }

    def test_negative_nivel_not_replaced_by_historical_max(self):
        data = {"value": -2.20, "date_time": "2026-09-28T22:00:00"}
        variable = {"str_variable": "nivel", "calculate_nivel": 1}
        created = {}

        result = process_nivel_variable(data, variable, self.point_dict, created)

        # No debe ser 94 (máximo histórico)
        self.assertNotEqual(float(result["nivel"]), 94.0)
        self.assertEqual(str(result["nivel"]), "00.00")
        # No inventar freático = d3 - 0 = 40
        self.assertEqual(str(result["water_table"]), "00.00")
        self.assertIn("_nivel_invalid", result.get("variable_values", {}))
        self.assertIn("negativo_flagged", result["variable_values"]["_nivel_invalid"])

    def test_negative_nivel_emits_event(self):
        data = {"value": -1.5, "date_time": "2026-09-28T22:00:00"}
        variable = {"str_variable": "nivel", "calculate_nivel": 1}
        process_nivel_variable(data, variable, self.point_dict, {})
        event = SystemEvent.objects.filter(
            point_catchment=self.point,
            event_type="MEASUREMENT_ERROR",
        ).first()
        self.assertIsNotNone(event)
        self.assertIn("negativo", event.title.lower())
        self.assertEqual(event.extra_data.get("decision"), "FLAG_INVALID")

    def test_positive_nivel_still_computes_water_table(self):
        data = {"value": 10.0, "date_time": "2026-09-28T22:00:00"}
        variable = {"str_variable": "nivel", "calculate_nivel": 1}
        result = process_nivel_variable(data, variable, self.point_dict, {})
        self.assertEqual(str(result["nivel"]), "10.00")
        # water_table = d3 - nivel = 40 - 10 = 30
        self.assertEqual(str(result["water_table"]), "30.00")
        self.assertNotIn("_nivel_invalid", result.get("variable_values", {}))
