"""
Tests de reportes JSON: /api/reports/json/by-point/ y /api/reports/json/last-year/.

Reproduce y previene el HTTP 500 por NameError (timezone / timedelta no importados).
"""
from datetime import datetime, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from api.core.models import (
    CatchmentPoint,
    Client,
    InteractionDetail,
    ProjectCatchments,
)

User = get_user_model()


class ReportsJsonEndpointsTests(TestCase):
    """Validar que los endpoints JSON de reportes responden 200 con fixtures."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='reportuser',
            password='testpass123',
            email='reportuser@example.com',
        )
        self.client_obj = Client.objects.create(name='Report Client')
        self.project = ProjectCatchments.objects.create(
            name='Report Project', client=self.client_obj
        )
        self.point = CatchmentPoint.objects.create(
            title='Report Point',
            owner_user=self.user,
            project=self.project,
            frecuency='60',
        )

        # Datos del mes actual (para by-point)
        now = timezone.now()
        self.current_year = now.year
        self.current_month = now.month
        InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=now.replace(hour=10, minute=0, second=0, microsecond=0),
            flow=Decimal('1.50'),
            total='100',
            total_diff=5,
            nivel=Decimal('3.20'),
        )
        InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=now.replace(hour=11, minute=0, second=0, microsecond=0),
            flow=Decimal('2.00'),
            total='105',
            total_diff=5,
            nivel=Decimal('3.10'),
        )

        # Datos del año anterior (para last-year)
        last_year = self.current_year - 1
        for month in (3, 6, 9):
            InteractionDetail.objects.create(
                catchment_point=self.point,
                date_time_medition=timezone.make_aware(
                    datetime(last_year, month, 15, 12, 0, 0)
                ),
                flow=Decimal('4.00'),
                total=str(50 + month),
                total_diff=10,
                nivel=Decimal('2.50'),
            )

        self.client.force_authenticate(user=self.user)

    def test_json_by_point_requires_point_id(self):
        response = self.client.get('/api/reports/json/by-point/')
        self.assertEqual(response.status_code, 400)
        self.assertIn('point_id', response.json().get('error', ''))

    def test_json_by_point_not_found(self):
        response = self.client.get('/api/reports/json/by-point/', {'point_id': 999999})
        self.assertEqual(response.status_code, 404)

    def test_json_by_point_ok_with_year_month(self):
        response = self.client.get(
            '/api/reports/json/by-point/',
            {
                'point_id': self.point.id,
                'year': self.current_year,
                'month': self.current_month,
            },
        )
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertEqual(data['point_id'], self.point.id)
        self.assertEqual(data['point_title'], self.point.title)
        self.assertEqual(data['year'], self.current_year)
        self.assertEqual(data['month'], self.current_month)
        self.assertIn('daily_data', data)
        self.assertGreaterEqual(len(data['daily_data']), 1)
        day = data['daily_data'][0]
        self.assertIn('dia', day)
        self.assertIn('consumo', day)
        self.assertIn('caudal_promedio', day)
        self.assertIn('registros', day)

    def test_json_by_point_ok_without_month(self):
        """Sin month (usa timezone.now().year) — antes NameError: timezone."""
        response = self.client.get(
            '/api/reports/json/by-point/',
            {'point_id': self.point.id},
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['year'], self.current_year)

    def test_json_last_year_ok(self):
        """Antes NameError: timedelta no importado en el método."""
        response = self.client.get(
            '/api/reports/json/last-year/',
            {'project_id': self.project.id},
        )
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertGreaterEqual(len(data), 1)
        row = data[0]
        self.assertEqual(row['catchment_point_id'], self.point.id)
        self.assertIn('mes', row)
        self.assertIn('consumo', row)
        self.assertIn('registros', row)

    def test_json_last_year_by_point_ids(self):
        response = self.client.get(
            '/api/reports/json/last-year/',
            {'point_ids': str(self.point.id)},
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertGreaterEqual(len(response.json()), 1)

    def test_json_last_year_no_points_404(self):
        response = self.client.get(
            '/api/reports/json/last-year/',
            {'project_id': 999999},
        )
        self.assertEqual(response.status_code, 404)

    def test_json_by_point_last_year_route_does_not_exist(self):
        """Documentar ruta exacta: no existe /json/by-point/last-year/."""
        response = self.client.get('/api/reports/json/by-point/last-year/')
        self.assertIn(response.status_code, (404, 405))
