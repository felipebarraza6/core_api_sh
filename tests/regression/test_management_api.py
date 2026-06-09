"""
Tests de regresión para el endpoint /api/management/points_status/.

Valida estructura de respuesta y ausencia de N+1 queries.
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from django.db import connection
from django.utils import timezone
from django.test.utils import CaptureQueriesContext
from datetime import timedelta

from api.core.models import (
    Client, ProjectCatchments, CatchmentPoint,
    InteractionDetail, ProfileDataConfigCatchment
)

User = get_user_model()


class ManagementPointsStatusRegressionTests(TestCase):
    """Tests para validar que points_status no cambia su contrato ni genera N+1."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            email='test@example.com'
        )
        self.client.force_authenticate(user=self.user)

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

    def test_points_status_structure(self):
        """Validar estructura JSON de /api/management/points_status/."""
        response = self.client.get('/api/management/points_status/')
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertIn('points', data)
        self.assertIn('total', data)
        self.assertIn('timestamp', data)
        self.assertIsInstance(data['points'], list)

    def test_points_status_filter_by_project(self):
        """Validar que el filtro ?project= funciona."""
        response = self.client.get(
            f'/api/management/points_status/?project={self.project.id}'
        )
        self.assertEqual(response.status_code, 200)

        data = response.json()
        point_ids = [p['id'] for p in data['points']]
        self.assertIn(self.point.id, point_ids)

    def test_points_status_no_n1_queries(self):
        """Validar que points_status no dispara N+1 queries para provider."""
        # Crear varios puntos adicionales para que el N+1 sea evidente
        for i in range(5):
            CatchmentPoint.objects.create(
                title=f"Extra Point {i}",
                owner_user=self.user,
                project=self.project,
                frecuency="60"
            )

        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get('/api/management/points_status/')
            self.assertEqual(response.status_code, 200)
            queries = len(ctx.captured_queries)

        # Con 6 puntos, un N+1 hubiera generado decenas de queries.
        # Con select_related correcto deberíamos tener menos de 10.
        self.assertLess(
            queries, 10,
            f"Demasiadas queries ({queries}), posible N+1 no resuelto"
        )

    def test_points_status_with_interaction(self):
        """Validar que un punto con InteractionDetail se serializa correctamente."""
        now = timezone.now()
        InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=now - timedelta(hours=1),
            total="1000",
            total_diff=10,
            flow=5.5,
            nivel=12.3,
            days_not_conection=0,
            is_error=False,
        )

        response = self.client.get('/api/management/points_status/')
        self.assertEqual(response.status_code, 200)

        data = response.json()
        point_data = next(
            (p for p in data['points'] if p['id'] == self.point.id), None
        )
        self.assertIsNotNone(point_data)
        self.assertIn('last_interaction', point_data)
        self.assertIsNotNone(point_data['last_interaction'])
        self.assertEqual(point_data['last_interaction']['flow'], 5.5)
        self.assertEqual(point_data['last_interaction']['total'], '1000')
