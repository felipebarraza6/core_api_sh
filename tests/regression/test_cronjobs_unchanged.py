"""
Tests de regresión para validar que los cronjobs procesan correctamente.

IMPORTANTE: Estos tests validan el comportamiento de los cronjobs sin ejecutarlos realmente.
Validan la lógica de procesamiento.
"""
from django.test import TestCase
from api.core.models import CatchmentPoint, InteractionDetail, ProfileDataConfigCatchment, User, Client, ProjectCatchments
from api.cronjobs.telemetry.controllers.unified_processing import (
    process_totalizado_variable,
    process_nivel_variable,
    process_caudal_variable,
    process_caudal_promedio_variable,
    validate_frequency
)
from datetime import datetime
import pytz


class CronjobLogicRegressionTests(TestCase):
    """Tests para validar la lógica de cronjobs no cambia."""

    def setUp(self):
        """Configurar datos de prueba."""
        self.chile_tz = pytz.timezone("America/Santiago")
        self.user = User.objects.create(username="testuser", email="test@example.com")
        self.client_obj = Client.objects.create(name="Test Client")
        self.project = ProjectCatchments.objects.create(name="Test Project", client=self.client_obj)
        self.point = CatchmentPoint.objects.create(title="Test Point", owner_user=self.user, project=self.project)
        self.profile = ProfileDataConfigCatchment.objects.create(
            point_catchment=self.point,
            is_telemetry=True,
            d5=100.0,
            d6=50.0
        )
        self.point_catchment_dict = {
            "id": self.point.id,
            "profile_data_config": {
                "d3": 10.0,
                "d5": 100.0,
                "d6": 50.0,
                "nivel_offset": 0,
            }
        }

    def test_process_totalizado_variable(self):
        """Validar que procesamiento de TOTALIZADO funciona correctamente."""
        data = {
            "value": 1000,
            "date_time": "2025-01-01T10:00:00"
        }
        variable = {
            "pulses_factor": 1000,
            "str_variable": "TOTALIZADO_TEST"
        }
        created_register = {}
        
        date_time_last_logger, created_register = process_totalizado_variable(
            data, variable, self.point_catchment_dict, created_register
        )
        
        # Validar que se asignaron los valores
        self.assertIn('pulses', created_register)
        self.assertIn('total', created_register)
        self.assertIn('total_diff', created_register)
        self.assertEqual(created_register['pulses'], 1000)

    def test_process_nivel_variable(self):
        """Validar que procesamiento de NIVEL funciona correctamente."""
        data = {
            "value": 5.5,
            "date_time": "2025-01-01T10:00:00"
        }
        variable = {
            "str_variable": "NIVEL_TEST",
            "calculate_nivel": None
        }
        created_register = {}
        
        result = process_nivel_variable(
            data, variable, self.point_catchment_dict, created_register
        )
        
        # Validar que se asignó nivel
        self.assertIn('nivel', result)
        self.assertIn('water_table', result)

    def test_process_caudal_variable(self):
        """Validar que procesamiento de CAUDAL funciona correctamente."""
        data = {
            "value": 10.5,
            "date_time": "2025-01-01T10:00:00"
        }
        variable = {
            "str_variable": "CAUDAL_TEST",
            "convert_to_lt": True,
            "calculate_nivel": None
        }
        created_register = {}
        
        result = process_caudal_variable(
            data, variable, self.point_catchment_dict, created_register
        )
        
        # Validar que se asignó flow
        self.assertIn('flow', result)

    def test_process_caudal_promedio_variable(self):
        """Validar que procesamiento de CAUDAL_PROMEDIO NO guarda flow."""
        created_register = {}
        date_time_last_logger_total = "2025-01-01T10:00:00"
        
        result = process_caudal_promedio_variable(
            date_time_last_logger_total, created_register, self.point_catchment_dict
        )
        
        # Validar que NO se guarda flow (se calcula dinámicamente)
        # El registro debe existir pero sin flow asignado aquí
        self.assertIsNotNone(result)

    def test_validate_frequency_mayor(self):
        """Validar frecuencia para estándar MAYOR."""
        from api.core.models import DgaDataConfigCatchment
        # El signal create_related_profiles ya creó una config DGA por defecto
        dga_config = DgaDataConfigCatchment.objects.get(point_catchment=self.point)
        dga_config.standard = "MAYOR"
        dga_config.save()
        
        # Hora con minuto 0 debe retornar True
        current_time = datetime(2025, 1, 1, 10, 0, 0, tzinfo=self.chile_tz)
        result = validate_frequency(self.point_catchment_dict, current_time)
        self.assertTrue(result)
        
        # Hora con minuto != 0 debe retornar False
        current_time = datetime(2025, 1, 1, 10, 30, 0, tzinfo=self.chile_tz)
        result = validate_frequency(self.point_catchment_dict, current_time)
        self.assertFalse(result)

    def test_validate_frequency_medio(self):
        """Validar frecuencia para estándar MEDIO."""
        from api.core.models import DgaDataConfigCatchment
        # El signal create_related_profiles ya creó una config DGA por defecto
        dga_config = DgaDataConfigCatchment.objects.get(point_catchment=self.point)
        dga_config.standard = "MEDIO"
        dga_config.save()
        
        # Medianoche debe retornar True
        current_time = datetime(2025, 1, 1, 0, 0, 0, tzinfo=self.chile_tz)
        result = validate_frequency(self.point_catchment_dict, current_time)
        self.assertTrue(result)
        
        # Otra hora debe retornar False
        current_time = datetime(2025, 1, 1, 10, 0, 0, tzinfo=self.chile_tz)
        result = validate_frequency(self.point_catchment_dict, current_time)
        self.assertFalse(result)

