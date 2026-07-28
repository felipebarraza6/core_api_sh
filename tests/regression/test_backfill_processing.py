"""
Tests de regresión para backfill_processing.py
================================================

Valida que el procesamiento unificado en backfill funcione correctamente:
- Totales en cascada con base del registro anterior
- Caudal convertido a L/s
- Nivel con offset y water_table
- Gap detection
"""

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta

from api.core.models import (
    CatchmentPoint, Client, ProjectCatchments,
    InteractionDetail, ProfileDataConfigCatchment,
    SchemesCatchment, Variable,
)
from api.cronjobs.telemetry.controllers.backfill_processing import (
    process_backfill_range,
    detect_gaps,
    recalc_totals_cascade,
    process_flow_for_range,
    process_nivel_for_range,
)

User = get_user_model()


class BackfillProcessingTests(TestCase):
    """Tests para el procesamiento unificado de backfill."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser', password='testpass', email='test@example.com'
        )
        self.client_obj = Client.objects.create(name="Test Client")
        self.project = ProjectCatchments.objects.create(
            name="Test Project", client=self.client_obj
        )
        self.point = CatchmentPoint.objects.create(
            title="Test Point",
            owner_user=self.user,
            project=self.project,
            frecuency="60",
            is_tdata=True,
        )
        self.profile = ProfileDataConfigCatchment.objects.create(
            point_catchment=self.point,
            is_telemetry=True,
            d1=10.0,
            d3=5.0,
            nivel_offset=1.5,
            addition=0.0,
        )
        self.scheme = SchemesCatchment.objects.create(
            name="Test Scheme", description="Test"
        )
        self.scheme.points_catchment.add(self.point)

        # Variable TOTALIZADO
        self.var_total = Variable.objects.create(
            scheme_catchment=self.scheme,
            str_variable="5000",
            label="Acumulado",
            type_variable="TOTALIZADO",
            pulses_factor=1000,
        )
        # Variable CAUDAL con conversión
        self.var_caudal = Variable.objects.create(
            scheme_catchment=self.scheme,
            str_variable="5001",
            label="Caudal",
            type_variable="CAUDAL",
            convert_to_lt=True,
            calculate_nivel=2,
        )
        # Variable NIVEL
        self.var_nivel = Variable.objects.create(
            scheme_catchment=self.scheme,
            str_variable="5002",
            label="Nivel",
            type_variable="NIVEL",
            calculate_nivel=2,
        )

    def test_recalc_totals_cascade_with_base(self):
        """Totales deben calcularse en cascada usando el registro anterior como base."""
        now = timezone.now().replace(minute=0, second=0, microsecond=0)

        # Pre-rango: registro base (pulses=100, total=100)
        InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=now - timedelta(hours=2),
            pulses=100,
            total="100",
            total_diff=0,
        )

        # Rango: dos registros nuevos
        r1 = InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=now - timedelta(hours=1),
            pulses=110,
            total=None,
        )
        r2 = InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=now,
            pulses=125,
            total=None,
        )

        start_dt = now - timedelta(hours=1)
        end_dt = now + timedelta(hours=1)
        updated = recalc_totals_cascade(self.point, start_dt, end_dt)

        r1.refresh_from_db()
        r2.refresh_from_db()

        # diff = 110 - 100 = 10; total = 100 + 10 = 110
        self.assertEqual(r1.total, "110")
        # diff = 125 - 110 = 15; total = 110 + 15 = 125
        self.assertEqual(r2.total, "125")
        self.assertEqual(updated, 2)

    def test_recalc_totals_cascade_detects_reset(self):
        """Si pulses baja, debe detectarse como reset (diff = nuevo valor)."""
        now = timezone.now().replace(minute=0, second=0, microsecond=0)

        # Base: pulses=100, total=100
        InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=now - timedelta(hours=2),
            pulses=100,
            total="100",
        )

        # Reset: pulses baja a 10
        r1 = InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=now - timedelta(hours=1),
            pulses=10,
            total=None,
        )

        start_dt = now - timedelta(hours=1)
        end_dt = now + timedelta(hours=1)
        recalc_totals_cascade(self.point, start_dt, end_dt)

        r1.refresh_from_db()
        # diff = 10 (reset); total = 100 + 10 = 110
        self.assertEqual(r1.total, "110")

    def test_process_flow_converts_to_lt(self):
        """Caudal crudo debe convertirse a L/s cuando convert_to_lt=True."""
        now = timezone.now().replace(minute=0, second=0, microsecond=0)

        # Valor crudo = 36.0 m³/h → convert_to_lt=True → 36/3.6 = 10.0 L/s
        # calculate_nivel=2 → divide por 2 → 5.0 L/s
        r = InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=now,
            flow=36.0,
        )

        process_flow_for_range(self.point, now, now + timedelta(hours=1), self.var_caudal)
        r.refresh_from_db()
        self.assertEqual(r.flow, 5.0)

    def test_process_nivel_with_offset(self):
        """Nivel debe aplicar offset del profile y calcular water_table."""
        now = timezone.now().replace(minute=0, second=0, microsecond=0)

        # Raw nivel = 8.0; offset = 1.5 → 9.5
        # calculate_nivel = 2 → nivel = 9.5 / 2 = 4.75
        # water_table = d3 - nivel = 5.0 - 4.75 = 0.25
        r = InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=now,
            nivel=8.0,
            water_table=0.0,
        )

        process_nivel_for_range(
            self.point, now, now + timedelta(hours=1),
            self.var_nivel, self.profile
        )
        r.refresh_from_db()
        self.assertAlmostEqual(float(r.nivel), 4.75, places=2)
        self.assertAlmostEqual(float(r.water_table), 0.25, places=2)

    def test_detect_gaps_finds_missing_buckets(self):
        """Gap detection debe encontrar buckets faltantes."""
        now = timezone.now().replace(minute=0, second=0, microsecond=0)

        # Crear registros con un hueco (falta la hora 12)
        InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=now - timedelta(hours=2),
            pulses=100,
            total="100",
        )
        InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=now,
            pulses=120,
            total="120",
        )

        start_dt = now - timedelta(hours=2)
        end_dt = now + timedelta(hours=1)
        gaps = detect_gaps(self.point, start_dt, end_dt)

        # Debe encontrar 1 gap: la hora intermedia
        self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps[0]["missing_count"], 1)

    def test_process_backfill_range_integration(self):
        """Test de integración completo: ingesta + procesamiento."""
        now = timezone.now().replace(minute=0, second=0, microsecond=0)

        # Base pre-rango
        InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=now - timedelta(hours=2),
            pulses=100,
            total="100",
        )

        # Registros en rango con valores crudos
        r1 = InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=now - timedelta(hours=1),
            pulses=110,
            flow=36.0,
            nivel=8.0,
            total=None,
        )
        r2 = InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=now,
            pulses=125,
            flow=36.0,
            nivel=8.0,
            total=None,
        )

        start_dt = now - timedelta(hours=1)
        end_dt = now + timedelta(hours=1)
        results = process_backfill_range(self.point, start_dt, end_dt)

        r1.refresh_from_db()
        r2.refresh_from_db()

        # Totales
        self.assertEqual(r1.total, "110")
        self.assertEqual(r2.total, "125")

        # Caudal procesado
        self.assertEqual(r1.flow, 5.0)
        self.assertEqual(r2.flow, 5.0)

        # Nivel procesado
        self.assertAlmostEqual(float(r1.nivel), 4.75, places=2)
        self.assertAlmostEqual(float(r1.water_table), 0.25, places=2)

        # Diffs recalculados
        self.assertEqual(r1.total_diff, 10)
        self.assertEqual(r2.total_diff, 15)

        # Resultados deben indicar actualizaciones
        self.assertGreater(results["totals_updated"], 0)
        self.assertGreater(results["flow_updated"], 0)
        self.assertGreater(results["nivel_updated"], 0)
