"""
Tests de monotonicidad del totalizador ante fallos consecutivos.

Ítem 2 auditoría 2026-10-02: el 2º ciclo fallido no debe bajar el total a 0.
"""
from django.test import TestCase
from django.utils import timezone
from datetime import timedelta

from api.core.models import (
    Client,
    ProjectCatchments,
    CatchmentPoint,
    InteractionDetail,
    ProfileDataConfigCatchment,
)
from django.contrib.auth import get_user_model
from api.cronjobs.telemetry.controllers.total import total_m3
from api.cronjobs.telemetry.controllers.unified_processing import (
    process_totalizado_variable,
)

User = get_user_model()


class TotalizerMonotonicFailureTests(TestCase):
    """Fallo de getter no puede producir total < último válido."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="mono_user", password="x", email="m@test.com"
        )
        self.client_obj = Client.objects.create(name="Mono Client")
        self.project = ProjectCatchments.objects.create(
            name="Mono Project", client=self.client_obj
        )
        self.point = CatchmentPoint.objects.create(
            title="Mono Point",
            owner_user=self.user,
            project=self.project,
            frecuency="60",
        )
        self.profile = ProfileDataConfigCatchment.objects.get(point_catchment=self.point)
        self.profile.addition = 0
        self.profile.is_telemetry = True
        self.profile.save()
        self.point_dict = {
            "id": self.point.id,
            "profile_data_config": {
                "addition": 0,
                "max_diff_m3_per_hour": 500,
                "reconnection_threshold_hours": 2,
            },
            "frecuency": "60",
        }

    def test_second_consecutive_zero_keeps_last_valid_total(self):
        """
        Simula ola TheThings: hora1 fallo (is_error, pulses=0 guardado),
        hora2 otro fallo. El total no debe caer a 0.
        """
        now = timezone.now()
        # Lectura válida previa
        InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=now - timedelta(hours=2),
            total="180121",
            pulses=180121,
            is_error=False,
        )
        # Primer fallo: total preservado pero pulses=0 e is_error (comportamiento viejo)
        InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=now - timedelta(hours=1),
            total="180121",
            pulses=0,
            is_error=True,
        )

        # Segundo fallo: pulsos=0 otra vez
        result, meta = total_m3(
            pulses_factor=1000,
            value=0,
            point_catchment=self.point_dict,
            current_dt=now,
            return_full_details=True,
        )
        self.assertEqual(result, 180121)
        self.assertIn(meta.get("status"), ("ZERO_KEPT", "MONOTONIC_PRESERVED"))

    def test_zero_kept_restores_pulses_in_register(self):
        """process_totalizado_variable debe restaurar pulses al último válido.

        Tras integrar lectores: sin date_time, is_getter_success es False y
        process_totalizado sale temprano (el runner usa _apply_last_valid_*).
        Este test ejercita ZERO_KEPT con una lectura cero *válida* (timestamp OK).
        """
        now = timezone.now()
        InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=now - timedelta(hours=1),
            total="50000",
            pulses=50000,
            is_error=False,
        )
        # Lectura cero con timestamp = getter OK; ZERO_KEPT restaura pulses.
        data = {
            "value": 0,
            "date_time": now.strftime("%Y-%m-%dT%H:%M:%S"),
            "status": "ok",
        }
        variable = {"pulses_factor": 1000, "str_variable": "TOTAL"}
        created = {"date_time_medition": now.strftime("%Y-%m-%dT%H:%M:%S")}

        _, created = process_totalizado_variable(
            data, variable, self.point_dict, created, current_dt=now
        )
        self.assertEqual(created["total"], 50000)
        self.assertEqual(
            created["pulses"],
            50000,
            "pulses=0 envenenaría el siguiente ciclo",
        )

    def test_last_interaction_skips_error_records(self):
        """Baseline ignora is_error=True aunque sea el más reciente."""
        now = timezone.now()
        InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=now - timedelta(hours=2),
            total="99999",
            pulses=99999,
            is_error=False,
        )
        InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=now - timedelta(hours=1),
            total="0",
            pulses=0,
            is_error=True,
        )
        result = total_m3(
            pulses_factor=1000,
            value=0,
            point_catchment=self.point_dict,
            current_dt=now,
        )
        self.assertEqual(result, 99999)
