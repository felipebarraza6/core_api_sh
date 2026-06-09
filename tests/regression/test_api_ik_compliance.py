"""
Tests de regresión para el endpoint de compliance.
==================================================

GET /api/ik/compliance/
"""

from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from api.core.models import (
    CatchmentPoint, Client, ProjectCatchments,
    InteractionDetail, DgaDataConfigCatchment,
    ProfileDataConfigCatchment,
)

User = get_user_model()


class ComplianceEndpointTests(TestCase):
    """Tests para GET /api/ik/compliance/"""

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
            frecuency="60",
            is_tdata=True,
        )
        ProfileDataConfigCatchment.objects.create(
            point_catchment=self.point,
            is_telemetry=True,
        )
        self.dga = DgaDataConfigCatchment.objects.create(
            point_catchment=self.point,
            send_dga=True,
            code_dga="12345-DGA",
            standard="MAYOR",
            type_dga="SUPERFICIAL",
            flow_granted_dga=10.0,
            total_granted_dga=1000.0,
        )

    def test_compliance_structure(self):
        """Debe retornar stats + points con flow_history y compliance_warning."""
        response = self.client.get('/api/ik/compliance/')
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertIn('stats', data)
        self.assertIn('points', data)

        stats = data['stats']
        self.assertIn('total', stats)
        self.assertIn('by_standard', stats)
        self.assertIn('by_type', stats)

        points = data['points']
        self.assertEqual(len(points), 1)

        first = points[0]
        self.assertIn('flow_history', first)
        self.assertIn('compliance_warning', first)
        self.assertEqual(first['point_id'], self.point.id)
        self.assertEqual(first['code'], "12345-DGA")

    def test_compliance_empty_for_user_without_points(self):
        """Usuario sin puntos debe ver lista vacía."""
        empty_user = User.objects.create_user(
            username='empty', password='emptypass', email='empty@example.com'
        )
        self.client.force_authenticate(user=empty_user)

        response = self.client.get('/api/ik/compliance/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['stats']['total'], 0)
        self.assertEqual(data['points'], [])

    def test_compliance_excludes_unauthorized_points(self):
        """No debe incluir puntos que no pertenecen al usuario."""
        other_user = User.objects.create_user(
            username='other', password='otherpass', email='other@example.com'
        )
        other_point = CatchmentPoint.objects.create(
            title="Other Point",
            owner_user=other_user,
            project=self.project,
            frecuency="60",
        )
        DgaDataConfigCatchment.objects.create(
            point_catchment=other_point,
            send_dga=True,
            code_dga="99999-DGA",
        )

        response = self.client.get('/api/ik/compliance/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        # Solo debe ver su propio punto
        self.assertEqual(data['stats']['total'], 1)
        self.assertEqual(data['points'][0]['point_id'], self.point.id)
