
from django.test import TestCase, override_settings
from django.utils import timezone
from unittest.mock import patch, MagicMock
from api.core.models import InteractionDetail, CatchmentPoint, DgaDataConfigCatchment
from api.cronjobs.dga.send_data_dga import send

class DgaErrorMappingTest(TestCase):
    def setUp(self):
        # Create User
        from api.core.models import User, Client, ProjectCatchments
        self.user = User.objects.create(username="testuser", email="test@example.com")
        
        # Create Hierarchy
        self.client = Client.objects.create(name="Test Client")
        self.project = ProjectCatchments.objects.create(name="Test Project", client=self.client)
        
        # Setup basic data
        self.point = CatchmentPoint.objects.create(
            title="Test Point", 
            project=self.project,
            owner_user=self.user
        )
        
        # Setup DGA Config
        self.dga_config = DgaDataConfigCatchment.objects.create(
            point_catchment=self.point,
            standard="MAYOR",
            send_dga=True,
            code_dga="TEST-CODE",
            rut_report_dga="11222333-4",
            password_dga_software="secret"
        )
        
        # Create a record to send
        self.record = InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=timezone.now(),
            total="100",
            flow=10.5,
            send_dga=True
        )

    @patch('api.cronjobs.dga.send_data_dga.requests.post')
    def test_usuario_no_informante_error(self, mock_post):
        """Test that 'Usuario no es el informante' error stops blocking the queue."""
        
        # Mock response with the specific error
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "status": "error",
            "message": "Error: Usuario no es el informante registrado en la Obra.",
            "data": {}
        }
        mock_post.return_value = mock_response
        
        # Prepare valid payload structure (mocked partially as we just test the send logic response handling)
        response_data = {
            "catchment_point": self.point.id,
            "code_dga": "TEST-CODE",
            "date_time_medition": "2023-01-01T12:00:00",
            "total": 100,
            "flow": 10.5,
            "rut": "11111111-1",
            "password": "pass",
            "id_data": self.record.id,
            "type_dga": "SUBTERRANEO",
            "water_table": 0,
            "dga_config": {}
        }
        
        # Execute send
        result = send(response_data)
        
        # Validations
        self.record.refresh_from_db()
        
        # Should return False (failed send)
        self.assertFalse(result, "Should return False for error")
        
        # CRITICAL: send_dga should be False (stop retrying)
        self.assertFalse(self.record.send_dga, "Should set send_dga=False to stop retrying")
        
        # CRITICAL: is_error should be True
        self.assertTrue(self.record.is_error, "Should mark as error")
        
        # Check message content
        self.assertIn("Error DGA Irrecuperable", self.record.return_dga)
        self.assertIn("Usuario no es el informante", self.record.return_dga)

    @patch('api.cronjobs.dga.send_data_dga.requests.post')
    def test_other_400_error_continues_retrying(self, mock_post):
        """Test that other 400 errors do NOT stop retrying (send_dga remains True)."""
        
        # Mock generic 400 error
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "status": "error",
            "message": "Error 400: Datos inválidos genéricos",
            "data": {}
        }
        mock_post.return_value = mock_response
        
         # Prepare valid payload
        response_data = {
            "catchment_point": self.point.id, 
            "code_dga": "TEST-CODE", 
            "date_time_medition": "2023-01-01T12:00:00",
            "total": 100, "flow": 10.5, "rut": "11111111-1", "password": "pass",
            "id_data": self.record.id, "type_dga": "SUBTERRANEO", "water_table": 0,
            "dga_config": {}
        }

        # Execute send
        result = send(response_data)
        
        # Validations
        self.record.refresh_from_db()
        
        # Should return False
        self.assertFalse(result)
        
        # Should still be pending retry (send_dga=True) unless max retries logic handles it separate,
        # but our specific logic branch for unknown 400s is "continue", which eventually hits the end of function
        # and sets send_dga=True (default behavior for failures)
        
        # In the code:
        # Loop 3 times -> continue -> ... -> End loop -> Update with send_dga=True
        
        self.assertTrue(self.record.send_dga, "Should keep send_dga=True for generic errors to retry later")
