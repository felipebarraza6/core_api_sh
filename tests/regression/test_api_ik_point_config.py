"""
Tests de regresión para /api/ik/point/<id>/config/
=================================================
GET  -> ver config del punto
PATCH -> editar config (solo owner o staff)
"""

from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from api.core.models import (
    CatchmentPoint, Client, ProjectCatchments,
    ProfileDataConfigCatchment,
)

User = get_user_model()


class PointConfigViewTests(TestCase):
    """Tests para GET/PATCH /api/ik/point/<id>/config/"""

    def setUp(self):
        self.client = APIClient()
        self.owner = User.objects.create_user(
            username='owner', password='testpass123', email='owner@example.com'
        )
        self.viewer = User.objects.create_user(
            username='viewer', password='testpass123', email='viewer@example.com'
        )
        self.staff = User.objects.create_user(
            username='staff', password='testpass123', email='staff@example.com',
            is_staff=True
        )
        self.other = User.objects.create_user(
            username='other', password='testpass123', email='other@example.com'
        )

        self.client_obj = Client.objects.create(name="Test Client")
        self.project = ProjectCatchments.objects.create(
            name="Test Project", client=self.client_obj
        )
        self.point = CatchmentPoint.objects.create(
            title="Test Point",
            owner_user=self.owner,
            project=self.project,
            frecuency="60",
            is_tdata=True,
        )
        self.point.users_viewers.add(self.viewer)
        self.profile = ProfileDataConfigCatchment.objects.get(point_catchment=self.point)
        self.profile.d1 = "1.00"
        self.profile.d2 = "2.00"
        self.profile.d3 = "3.00"
        self.profile.d4 = "4.00"
        self.profile.d5 = "5.00"
        self.profile.d6 = 10
        self.profile.addition = "100.000"
        self.profile.is_telemetry = True
        self.profile.nivel_offset = "-17.000"
        self.profile.max_diff_m3_per_hour = "600.00"
        self.profile.max_flow_ls = "200.00"
        self.profile.max_time_gap_hours = "3.00"
        self.profile.reconnection_threshold_hours = "2.50"
        self.profile.replicate_on_missing = True
        self.profile.use_transaction_atomic = False
        self.profile.save()

    def test_get_config_by_owner(self):
        """Owner puede ver la config completa."""
        self.client.force_authenticate(user=self.owner)
        response = self.client.get(f'/api/ik/point/{self.point.id}/config/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['d1'], '1.00')
        self.assertEqual(data['d6'], 10)
        self.assertEqual(data['addition'], '100.000')
        self.assertTrue(data['is_telemetry'])
        self.assertEqual(data['nivel_offset'], '-17.000')
        self.assertEqual(data['max_flow_ls'], '200.00')
        self.assertTrue(data['replicate_on_missing'])
        self.assertFalse(data['use_transaction_atomic'])

    def test_get_config_by_viewer(self):
        """Viewer puede ver la config."""
        self.client.force_authenticate(user=self.viewer)
        response = self.client.get(f'/api/ik/point/{self.point.id}/config/')
        self.assertEqual(response.status_code, 200)

    def test_get_config_by_staff(self):
        """Staff puede ver la config de cualquier punto."""
        self.client.force_authenticate(user=self.staff)
        response = self.client.get(f'/api/ik/point/{self.point.id}/config/')
        self.assertEqual(response.status_code, 200)

    def test_get_config_unauthorized(self):
        """Usuario sin acceso recibe 404."""
        self.client.force_authenticate(user=self.other)
        response = self.client.get(f'/api/ik/point/{self.point.id}/config/')
        self.assertEqual(response.status_code, 404)

    def test_get_config_creates_profile_if_missing(self):
        """Si no hay profile, se crea uno vacío."""
        point2 = CatchmentPoint.objects.create(
            title="No Profile",
            owner_user=self.owner,
            project=self.project,
            frecuency="60",
        )
        self.client.force_authenticate(user=self.owner)
        response = self.client.get(f'/api/ik/point/{point2.id}/config/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            ProfileDataConfigCatchment.objects.filter(point_catchment=point2).exists()
        )

    def test_patch_config_by_owner(self):
        """Owner puede editar la config."""
        self.client.force_authenticate(user=self.owner)
        response = self.client.patch(
            f'/api/ik/point/{self.point.id}/config/',
            data={
                'd1': '9.50',
                'd6': 42,
                'addition': '55.500',
                'is_telemetry': False,
                'max_flow_ls': '99.99',
                'replicate_on_missing': False,
            },
            format='json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['d1'], '9.50')
        self.assertEqual(data['d6'], 42)
        self.assertEqual(data['addition'], '55.500')
        self.assertFalse(data['is_telemetry'])
        self.assertEqual(data['max_flow_ls'], '99.99')
        self.assertFalse(data['replicate_on_missing'])

        # Persistió
        self.profile.refresh_from_db()
        self.assertEqual(str(self.profile.d1), '9.50')
        self.assertEqual(self.profile.d6, 42)

    def test_patch_config_by_staff(self):
        """Staff puede editar la config de cualquier punto."""
        self.client.force_authenticate(user=self.staff)
        response = self.client.patch(
            f'/api/ik/point/{self.point.id}/config/',
            data={'d2': '7.77'},
            format='json'
        )
        self.assertEqual(response.status_code, 200)
        self.profile.refresh_from_db()
        self.assertEqual(str(self.profile.d2), '7.77')

    def test_patch_config_viewer_forbidden(self):
        """Viewer NO puede editar la config."""
        self.client.force_authenticate(user=self.viewer)
        response = self.client.patch(
            f'/api/ik/point/{self.point.id}/config/',
            data={'d1': '99.99'},
            format='json'
        )
        self.assertEqual(response.status_code, 404)

    def test_patch_config_unauthorized(self):
        """Usuario ajeno no puede editar."""
        self.client.force_authenticate(user=self.other)
        response = self.client.patch(
            f'/api/ik/point/{self.point.id}/config/',
            data={'d1': '99.99'},
            format='json'
        )
        self.assertEqual(response.status_code, 404)

    def test_patch_invalid_fields_return_400(self):
        """Campos desconocidos retornan 400."""
        self.client.force_authenticate(user=self.owner)
        response = self.client.patch(
            f'/api/ik/point/{self.point.id}/config/',
            data={'token_service': 'abc', 'd1': '1.00'},
            format='json'
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('token_service', response.json()['error'])

    def test_patch_invalid_decimal_returns_400(self):
        """Valor decimal inválido retorna 400 con detalle por campo."""
        self.client.force_authenticate(user=self.owner)
        response = self.client.patch(
            f'/api/ik/point/{self.point.id}/config/',
            data={'d1': 'no es numero'},
            format='json'
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('d1', response.json()['error'])

    def test_patch_empty_body_returns_400(self):
        """Body vacío retorna 400."""
        self.client.force_authenticate(user=self.owner)
        response = self.client.patch(
            f'/api/ik/point/{self.point.id}/config/',
            data={},
            format='json'
        )
        self.assertEqual(response.status_code, 400)
