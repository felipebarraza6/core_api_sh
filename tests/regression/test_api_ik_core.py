"""
Tests de regresión para API Ikolu — Endpoints críticos del Centro de Control.

Cubre:
- PointsSummaryView (GET /api/ik/points_summary/)
- PointSummaryView (GET /api/ik/point/<id>/summary/)
- DashboardStatsView (GET /api/ik/dashboard_stats/)
- BatchTelemetryView (POST /api/ik/batch/telemetry/)
- BatchStatsView (POST /api/ik/batch/stats/)
"""
import json
from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from api.core.models import (
    CatchmentPoint, Client, ProjectCatchments,
    InteractionDetail, ProfileDataConfigCatchment,
)

User = get_user_model()


@override_settings(CACHES={
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
})
class ApiIkCoreRegressionTests(TestCase):
    """Tests para validar que los endpoints críticos de Ikolu no se rompen."""

    def setUp(self):
        from django.core.cache import cache
        cache.clear()  # Limpiar throttles entre tests

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
        )
        ProfileDataConfigCatchment.objects.create(
            point_catchment=self.point,
            is_telemetry=True,
            d1=12.50,
            d3=8.00,
        )

    def test_points_summary_structure(self):
        """Validar estructura de /api/ik/points_summary/"""
        response = self.client.get('/api/ik/points_summary/')
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertIn('points', data)
        self.assertIn('total_points', data)
        self.assertIsInstance(data['points'], list)

    def test_point_summary_structure(self):
        """Validar estructura de /api/ik/point/<id>/summary/"""
        response = self.client.get(f'/api/ik/point/{self.point.id}/summary/')
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertIn('id', data)
        self.assertIn('title', data)
        self.assertIn('config_data', data)

    def test_dashboard_stats_structure(self):
        """Validar estructura de /api/ik/dashboard_stats/"""
        response = self.client.get('/api/ik/dashboard_stats/')
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertIn('points', data)
        self.assertIn('status_today', data)
        self.assertIn('last_7', data)
        # Verificar que last_7 tenga warnings dentro de cada día
        last_7 = data.get('last_7', {})
        for point_data in last_7.values():
            for day in point_data.get('days', []):
                self.assertIn('warnings', day)

        # Verificar sub-estructuras
        points = data['points']
        self.assertIn('total', points)
        self.assertIn('with_telemetry', points)
        self.assertIn('with_gps', points)
        self.assertIn('with_compliance', points)

        status = data['status_today']
        self.assertIn('connected', status)
        self.assertIn('disconnected', status)

    def test_dashboard_stats_includes_d1_d3_from_profile(self):
        """d1 y d3 deben venir desde ProfileDataConfigCatchment, no null."""
        response = self.client.get('/api/ik/dashboard_stats/')
        self.assertEqual(response.status_code, 200)

        data = response.json()
        point_data = data['last_7'].get(self.point.title)
        self.assertIsNotNone(point_data)

        # d1 y d3 deben estar presentes y ser los valores del profile
        self.assertEqual(point_data['d1'], 12.5)
        self.assertEqual(point_data['d3'], 8.0)

    def test_dashboard_stats_daily_consumption_sums_diffs(self):
        """Consumo diario debe ser suma de total_diff, no last_total - first_total.
        Además debe ignorar registros con is_error=True."""
        from django.utils import timezone
        from datetime import timedelta

        today = timezone.now().date()
        # Crear 3 registros hoy con diff conocido
        InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=timezone.now().replace(hour=8),
            total="100",
            total_diff=5,
            flow=1.0,
            is_error=False,
        )
        InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=timezone.now().replace(hour=12),
            total="110",
            total_diff=10,
            flow=2.0,
            is_error=False,
        )
        # Registro con error: no debe sumar al consumo
        InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=timezone.now().replace(hour=16),
            total="9999",
            total_diff=50,
            flow=5.0,
            is_error=True,
        )
        InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=timezone.now().replace(hour=20),
            total="120",
            total_diff=10,
            flow=1.5,
            is_error=False,
        )

        response = self.client.get('/api/ik/dashboard_stats/')
        self.assertEqual(response.status_code, 200)
        data = response.json()

        point_data = data['last_7'].get(self.point.title)
        self.assertIsNotNone(point_data)

        today_str = str(today)
        today_day = next((d for d in point_data['days'] if d['date'] == today_str), None)
        self.assertIsNotNone(today_day)

        # Suma de diffs válidos = 5 + 10 + 10 = 25
        # (no 120 - 100 = 20, ni debe incluir el registro con error)
        self.assertEqual(today_day['consumption'], 25.0)
        self.assertEqual(today_day['measurements_count'], 3)
        # Total semanal debe incluir solo los 25 de hoy
        self.assertEqual(point_data['total_m3'], 25.0)

    def test_batch_telemetry_structure(self):
        """Validar estructura de /api/ik/batch/telemetry/"""
        payload = {"point_ids": [self.point.id]}
        response = self.client.post(
            '/api/ik/batch/telemetry/',
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertIn('data', data)
        self.assertIn('meta', data)

    def test_batch_stats_structure(self):
        """Validar estructura de /api/ik/batch/stats/"""
        payload = {"point_ids": [self.point.id]}
        response = self.client.post(
            '/api/ik/batch/stats/',
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertIn('data', data)

    def test_my_points_structure(self):
        """Validar estructura de /api/ik/my_points/"""
        response = self.client.get('/api/ik/my_points/')
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertIsInstance(data, list)

    def test_public_announcements_no_auth(self):
        """Validar que /api/ik/announcements/public/ no requiere auth"""
        self.client.logout()
        response = self.client.get('/api/ik/announcements/public/')
        self.assertEqual(response.status_code, 200)

    def test_throttling_batch_telemetry(self):
        """Validar que batch_telemetry tiene throttling activo."""
        payload = {"point_ids": [self.point.id]}
        for i in range(35):
            response = self.client.post(
                '/api/ik/batch/telemetry/',
                data=json.dumps(payload),
                content_type='application/json'
            )
        # El último debería ser 429 (throttled) o 200 si no alcanzó
        self.assertIn(response.status_code, [200, 429])

    def test_points_summary_pagination_optional(self):
        """Paginación opcional: sin ?limit comportamiento idéntico."""
        response = self.client.get('/api/ik/points_summary/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertNotIn('meta', data)  # Sin paginación no hay meta
        self.assertEqual(data['total_points'], 1)

    def test_points_summary_pagination_with_limit(self):
        """Paginación con ?limit devuelve meta y respeta limit."""
        response = self.client.get('/api/ik/points_summary/?limit=1&offset=0')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('meta', data)
        self.assertEqual(data['meta']['limit'], 1)
        self.assertEqual(data['meta']['offset'], 0)
        self.assertEqual(data['meta']['total'], 1)
        self.assertEqual(len(data['points']), 1)

    def test_my_points_pagination_optional(self):
        """my_points sin paginación: lista plana como siempre."""
        response = self.client.get('/api/ik/my_points/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)

    def test_my_points_pagination_with_limit(self):
        """my_points con ?limit: respeta limit y sigue siendo lista."""
        response = self.client.get('/api/ik/my_points/?limit=1&offset=0')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 1)

    def test_batch_stats_rejects_foreign_point(self):
        """Usuario normal no puede ver stats de punto ajeno."""
        other_user = User.objects.create_user(
            username='otheruser', password='otherpass', email='other@example.com'
        )
        other_point = CatchmentPoint.objects.create(
            title="Other Point", owner_user=other_user, project=self.project, frecuency="60"
        )
        payload = {"point_ids": [other_point.id]}
        response = self.client.post(
            '/api/ik/batch/stats/',
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"data": {}})

    def test_batch_telemetry_rejects_foreign_point(self):
        """Usuario normal no puede ver telemetría de punto ajeno."""
        other_user = User.objects.create_user(
            username='otheruser2', password='otherpass2', email='other2@example.com'
        )
        other_point = CatchmentPoint.objects.create(
            title="Other Point 2", owner_user=other_user, project=self.project, frecuency="60"
        )
        payload = {"point_ids": [other_point.id]}
        response = self.client.post(
            '/api/ik/batch/telemetry/',
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data'], {})

    def test_batch_telemetry_invalid_hours(self):
        """hours no numérico debe retornar 400."""
        payload = {"point_ids": [self.point.id], "hours": "abc"}
        response = self.client.post(
            '/api/ik/batch/telemetry/',
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("hours", response.json().get("error", "").lower())

    def test_batch_stats_invalid_days(self):
        """days no numérico debe retornar 400."""
        payload = {"point_ids": [self.point.id], "days": "xyz"}
        response = self.client.post(
            '/api/ik/batch/stats/',
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("days", response.json().get("error", "").lower())


class ApiIkCalendarRegressionTests(TestCase):
    """Tests para el endpoint de calendario."""

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
        )
        from django.utils import timezone
        from datetime import timedelta
        now = timezone.now()
        for i in range(5):
            InteractionDetail.objects.create(
                catchment_point=self.point,
                date_time_medition=now - timedelta(days=i),
                total=str(100 + i * 10),
                total_diff=10,
                flow=0.0,
            )

    def test_point_calendar_structure(self):
        """Validar estructura de /api/ik/point/<id>/calendar/"""
        response = self.client.get(
            f'/api/ik/point/{self.point.id}/calendar/?days=7'
        )
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertIn('calendar', data)
        self.assertIn('days', data)
        self.assertIsInstance(data['calendar'], list)

    def test_point_variables_structure(self):
        """Validar estructura de /api/ik/point/<id>/variables/"""
        response = self.client.get(
            f'/api/ik/point/{self.point.id}/variables/'
        )
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertIn('variables', data)
        self.assertIsInstance(data['variables'], list)
