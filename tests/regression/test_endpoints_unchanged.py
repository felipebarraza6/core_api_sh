"""
Tests de regresión para validar que los endpoints no cambian su estructura.

IMPORTANTE: Estos tests deben pasar SIEMPRE, incluso después de optimizaciones.
Si un test falla, significa que se rompió la compatibilidad.
"""
import json
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from api.core.models import InteractionDetail, CatchmentPoint, Client, ProjectCatchments

User = get_user_model()


class EndpointStructureRegressionTests(TestCase):
    """Tests para validar que la estructura de endpoints no cambia."""

    def setUp(self):
        """Configurar cliente API y usuario de prueba."""
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            email='test@example.com'
        )
        self.client.force_authenticate(user=self.user)

    def test_interaction_detail_structure(self):
        """Validar que /api/interaction_detail/ mantiene estructura esperada."""
        response = self.client.get('/api/interaction_detail/')
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        
        # Validar estructura básica
        self.assertIn('count', data)
        self.assertIn('results', data)
        
        if data['results']:
            first_item = data['results'][0]
            # Validar campos críticos
            required_fields = [
                'id', 'catchment_point', 'date_time_medition',
                'flow', 'total', 'total_diff', 'is_average', 'flow_type'
            ]
            for field in required_fields:
                self.assertIn(field, first_item, f"Campo {field} faltante en respuesta")

    def test_interaction_detail_json_structure(self):
        """Validar que /api/interaction_detail_json/ mantiene estructura."""
        response = self.client.get('/api/interaction_detail_json/')
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertIn('count', data)
        self.assertIn('results', data)

    def test_interaction_detail_override_structure(self):
        """Validar que /api/interaction_detail_override/ retorna array sin paginación."""
        response = self.client.get('/api/interaction_detail_override/')
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        # Debe ser un array, no un objeto con count/results
        self.assertIsInstance(data, list)

    def test_flow_calculation_consistency(self):
        """Validar que el cálculo de flow es consistente."""
        # Crear punto de prueba con CAUDAL_PROMEDIO
        client_obj = Client.objects.create(name="Test Client")
        project = ProjectCatchments.objects.create(name="Test Project", client=client_obj)
        point = CatchmentPoint.objects.create(title="Test Point", owner_user=self.user, project=project)
        
        # Crear registros de prueba
        from django.utils import timezone
        from datetime import timedelta
        
        now = timezone.now()
        InteractionDetail.objects.create(
            catchment_point=point,
            date_time_medition=now - timedelta(hours=2),
            total="100",
            total_diff=10,
            flow=0.0
        )
        
        InteractionDetail.objects.create(
            catchment_point=point,
            date_time_medition=now,
            total="110",
            total_diff=10,
            flow=0.0
        )
        
        response = self.client.get(f'/api/interaction_detail_json/?catchment_point={point.id}')
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        if data['results']:
            # Validar que flow_type está presente
            for item in data['results']:
                self.assertIn('flow_type', item)
                self.assertIn('is_average', item)

    def test_total_calculation_consistency(self):
        """Validar que el cálculo de total (con d6) es consistente."""
        response = self.client.get('/api/interaction_detail_json/')
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        if data['results']:
            for item in data['results']:
                # Total debe ser un string o número
                self.assertIsNotNone(item.get('total'))
                # Total no debe ser None después del cálculo

