"""
Tests de regresión para el fallback de pulsos negativos en total_m3.

Valida que el redondeo (no truncamiento) se aplique al mantener el último
total válido cuando un sensor envía pulsos negativos.
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta

from api.core.models import (
    Client, ProjectCatchments, CatchmentPoint,
    InteractionDetail, ProfileDataConfigCatchment, CounterResetLog
)
from api.cronjobs.telemetry.controllers.total import total_m3

User = get_user_model()


class TotalNegativePulsesRegressionTests(TestCase):
    """Tests para validar redondeo correcto en fallback de pulsos negativos."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            email='test@example.com'
        )
        self.client_obj = Client.objects.create(name="Test Client")
        self.project = ProjectCatchments.objects.create(
            name="Test Project", client=self.client_obj
        )
        self.point = CatchmentPoint.objects.create(
            title="Test Point",
            owner_user=self.user,
            project=self.project,
            frecuency="60"
        )
        self.profile = ProfileDataConfigCatchment.objects.create(
            point_catchment=self.point,
            addition=0,
        )

    def test_negative_pulses_rounds_instead_of_truncates(self):
        """
        Si el último total era '1234.7', un pulso negativo debe retornar 1235
        (redondeo), no 1234 (truncamiento).
        """
        now = timezone.now()
        InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=now - timedelta(hours=1),
            total="1234.7",
            pulses=1234700,
            total_diff=10,
            flow=0.0,
        )

        result = total_m3(
            pulses_factor=1000,
            value=-5,
            point_catchment={"id": self.point.id},
            current_dt=now,
        )

        # 1234.7 redondea a 1235, NO trunca a 1234
        self.assertEqual(result, 1235)

    def test_negative_pulses_creates_counter_reset_log(self):
        """Verifica que se genere auditoría CounterResetLog para pulsos negativos."""
        now = timezone.now()
        InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=now - timedelta(hours=1),
            total="1000.4",
            pulses=1000400,
            total_diff=5,
            flow=0.0,
        )

        total_m3(
            pulses_factor=1000,
            value=-1,
            point_catchment={"id": self.point.id},
            current_dt=now,
        )

        log = CounterResetLog.objects.filter(
            point_catchment=self.point,
            reset_type="NEGATIVE_PULSES"
        ).first()

        self.assertIsNotNone(log)
        self.assertEqual(float(log.total_before), 1000.4)
        self.assertEqual(float(log.total_after), 1000.0)  # 1000.4 truncado a 1000 en log
