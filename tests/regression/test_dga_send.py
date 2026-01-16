"""
Tests de regresión para validar envío DGA no se rompe.

IMPORTANTE: Estos tests validan que el envío DGA funciona correctamente
tanto con el cálculo actual como con el nuevo cálculo (si flag activo).
"""
from django.test import TestCase
from django.utils import timezone
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
import pytz

from api.core.models import (
    InteractionDetail,
    CatchmentPoint,
    DgaDataConfigCatchment,
    ProfileDataConfigCatchment
)
from api.cronjobs.dga.cron_dga import _prepare_response_data


class DgaSendRegressionTests(TestCase):
    """Tests para validar que el envío DGA no se rompe."""

    def setUp(self):
        """Configurar datos de prueba."""
        self.chile_tz = pytz.timezone("America/Santiago")
        self.point = CatchmentPoint.objects.create(title="Test Point")
        self.profile = ProfileDataConfigCatchment.objects.create(
            point_catchment=self.point,
            is_telemetry=True
        )

    def test_prepare_response_data_standard_flow(self):
        """Validar que _prepare_response_data funciona con cálculo actual."""
        dga_config = DgaDataConfigCatchment.objects.create(
            point_catchment=self.point,
            standard="MAYOR",
            send_dga=True,
            code_dga="TEST-001",
            rut_report_dga="12345678-9",
            password_dga_software="testpass",
            type_dga="SUPERFICIAL"
        )
        
        now = timezone.now().astimezone(self.chile_tz)
        register = InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=now,
            total="1000",
            total_diff=10,
            flow=2.78,
            water_table=5.0
        )
        
        # Preparar datos (con flag desactivado por defecto)
        result = _prepare_response_data(register, dga_config)
        
        # Validar estructura
        self.assertIsNotNone(result)
        self.assertIn('flow', result)
        self.assertIn('code_dga', result)
        self.assertIn('date_time_medition', result)
        self.assertEqual(result['code_dga'], 'TEST-001')

    def test_prepare_response_data_total_diff_zero(self):
        """Validar que si total_diff=0, flow=0.0."""
        dga_config = DgaDataConfigCatchment.objects.create(
            point_catchment=self.point,
            standard="MAYOR",
            send_dga=True,
            code_dga="TEST-001",
            rut_report_dga="12345678-9",
            password_dga_software="testpass",
            type_dga="SUPERFICIAL"
        )
        
        now = timezone.now().astimezone(self.chile_tz)
        register = InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=now,
            total="1000",
            total_diff=0,  # Sin consumo
            flow=5.0,  # Valor que debe ser forzado a 0
            water_table=5.0
        )
        
        result = _prepare_response_data(register, dga_config)
        
        # Validar que flow es 0.0 cuando total_diff=0
        self.assertIsNotNone(result)
        self.assertEqual(result['flow'], 0.0)

    @patch('api.cronjobs.dga.cron_dga.settings')
    def test_prepare_response_data_with_new_calculation_flag(self, mock_settings):
        """Validar que funciona con flag de nuevo cálculo activo."""
        # Simular flag activo
        mock_settings.USE_NEW_CAUDAL_CALCULATION_MEDIO = True
        
        dga_config = DgaDataConfigCatchment.objects.create(
            point_catchment=self.point,
            standard="MEDIO",  # Estándar MEDIO
            send_dga=True,
            code_dga="TEST-001",
            rut_report_dga="12345678-9",
            password_dga_software="testpass",
            type_dga="SUPERFICIAL"
        )
        
        now = timezone.now().astimezone(self.chile_tz)
        register = InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=now,
            total="1000",
            total_diff=10,
            flow=2.78,
            water_table=5.0
        )
        
        # Preparar datos (debe usar nuevo cálculo para MEDIO)
        result = _prepare_response_data(register, dga_config)
        
        # Validar que retorna estructura correcta
        self.assertIsNotNone(result)
        self.assertIn('flow', result)
        # Flow puede ser 0.0 si no hay registros del día anterior (comportamiento esperado)

    def test_prepare_response_data_incomplete_config(self):
        """Validar que retorna None si configuración DGA incompleta."""
        dga_config = DgaDataConfigCatchment.objects.create(
            point_catchment=self.point,
            standard="MAYOR",
            send_dga=True,
            code_dga="",  # Código vacío
            rut_report_dga="",
            password_dga_software="",
            type_dga="SUPERFICIAL"
        )
        
        now = timezone.now().astimezone(self.chile_tz)
        register = InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=now,
            total="1000",
            total_diff=10,
            flow=2.78
        )
        
        result = _prepare_response_data(register, dga_config)
        
        # Debe retornar None si configuración incompleta
        self.assertIsNone(result)

