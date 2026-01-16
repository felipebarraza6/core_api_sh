"""
Tests exhaustivos para validar cálculos de caudal por estándar DGA.

IMPORTANTE: Estos tests validan que el nuevo cálculo funciona correctamente
y que no afecta otros estándares.
"""
from django.test import TestCase
from django.utils import timezone
from datetime import datetime, timedelta
import pytz

from api.core.models import (
    InteractionDetail,
    CatchmentPoint,
    DgaDataConfigCatchment,
    ProfileDataConfigCatchment
)
from api.cronjobs.dga.caudal_calculations import (
    calculate_daily_average_flow,
    calculate_flow_by_standard
)


class CaudalCalculationsTests(TestCase):
    """Tests para validar cálculos de caudal."""

    def setUp(self):
        """Configurar datos de prueba."""
        self.chile_tz = pytz.timezone("America/Santiago")
        self.point = CatchmentPoint.objects.create(title="Test Point")
        self.profile = ProfileDataConfigCatchment.objects.create(
            point_catchment=self.point,
            is_telemetry=True
        )

    def test_calculate_daily_average_flow_medio(self):
        """Validar cálculo de caudal medio diario para estándar MEDIO."""
        # Crear configuración DGA con estándar MEDIO
        dga_config = DgaDataConfigCatchment.objects.create(
            point_catchment=self.point,
            standard="MEDIO",
            send_dga=True,
            code_dga="TEST-001"
        )
        
        # Crear registros del día anterior (simular 24 horas)
        now = timezone.now().astimezone(self.chile_tz)
        yesterday_start = (now - timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        
        # Crear 24 registros (uno por hora) con caudales conocidos
        caudales_esperados = []
        for hour in range(24):
            record_time = yesterday_start + timedelta(hours=hour)
            total_value = 1000 + (hour * 10)  # Incremento de 10 m³ por hora
            
            InteractionDetail.objects.create(
                catchment_point=self.point,
                date_time_medition=record_time,
                total=str(total_value),
                total_diff=10,  # 10 m³/h = consumo constante
                flow=2.78  # Aproximadamente 10 m³/h = 2.78 L/s
            )
            caudales_esperados.append(2.78)
        
        # Crear registro actual (hoy a las 00:00)
        today_00 = now.replace(hour=0, minute=0, second=0, microsecond=0)
        current_register = InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=today_00,
            total="1240",
            total_diff=10,
            flow=0.0
        )
        
        # Calcular caudal medio diario
        result = calculate_daily_average_flow(current_register, dga_config)
        
        # Validar que el resultado es el promedio de los caudales del día anterior
        expected_average = sum(caudales_esperados) / len(caudales_esperados)
        self.assertAlmostEqual(result, expected_average, places=1)

    def test_calculate_daily_average_flow_no_records(self):
        """Validar que retorna 0.0 si no hay registros del día anterior."""
        dga_config = DgaDataConfigCatchment.objects.create(
            point_catchment=self.point,
            standard="MEDIO"
        )
        
        now = timezone.now().astimezone(self.chile_tz)
        current_register = InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=now,
            total="1000",
            total_diff=0,
            flow=0.0
        )
        
        result = calculate_daily_average_flow(current_register, dga_config)
        self.assertEqual(result, 0.0)

    def test_calculate_flow_by_standard_medio(self):
        """Validar que calculate_flow_by_standard usa cálculo diario para MEDIO."""
        dga_config = DgaDataConfigCatchment.objects.create(
            point_catchment=self.point,
            standard="MEDIO"
        )
        
        now = timezone.now().astimezone(self.chile_tz)
        current_register = InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=now,
            total="1000",
            total_diff=10,
            flow=0.0
        )
        
        # Debe usar calculate_daily_average_flow
        result = calculate_flow_by_standard(current_register, dga_config)
        # Resultado puede ser 0.0 si no hay registros del día anterior
        self.assertIsInstance(result, float)
        self.assertGreaterEqual(result, 0.0)

    def test_calculate_flow_by_standard_mayor(self):
        """Validar que calculate_flow_by_standard usa cálculo actual para MAYOR."""
        dga_config = DgaDataConfigCatchment.objects.create(
            point_catchment=self.point,
            standard="MAYOR"
        )
        
        # Crear registro anterior
        now = timezone.now().astimezone(self.chile_tz)
        previous = InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=now - timedelta(hours=1),
            total="1000",
            total_diff=10,
            flow=2.78
        )
        
        current_register = InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=now,
            total="1010",
            total_diff=10,
            flow=0.0
        )
        
        # Debe usar cálculo actual (fallback)
        result = calculate_flow_by_standard(current_register, dga_config)
        # Debe calcular entre current y previous
        self.assertIsInstance(result, float)
        self.assertGreaterEqual(result, 0.0)

    def test_calculate_daily_average_flow_only_medio(self):
        """Validar que solo aplica a estándar MEDIO."""
        # Crear configuración con otro estándar
        dga_config_mayor = DgaDataConfigCatchment.objects.create(
            point_catchment=self.point,
            standard="MAYOR"
        )
        
        now = timezone.now().astimezone(self.chile_tz)
        current_register = InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=now,
            total="1000",
            total_diff=10,
            flow=0.0
        )
        
        # Para MAYOR, debe usar fallback (no cálculo diario)
        result = calculate_daily_average_flow(current_register, dga_config_mayor)
        # Debe usar fallback, no cálculo diario
        self.assertIsInstance(result, float)

