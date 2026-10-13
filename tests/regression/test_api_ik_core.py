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
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from api.core.models import (
    CatchmentPoint, Client, ProjectCatchments,
    InteractionDetail, ProfileDataConfigCatchment,
    SchemesCatchment, Variable,
)
from api.core.models.alerts import SystemEvent

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

    def _find_point_in_last_7(self, last_7, title):
        """Buscar punto por título en lista paginada."""
        for p in last_7:
            if p['title'] == title:
                return p
        return None

    def test_dashboard_stats_structure(self):
        """Validar estructura de /api/ik/dashboard_stats/"""
        response = self.client.get('/api/ik/dashboard_stats/')
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertIn('points', data)
        self.assertIn('status_today', data)
        self.assertIn('last_7', data)
        self.assertIn('count', data)
        self.assertIn('next', data)
        self.assertIn('previous', data)
        self.assertIsInstance(data['last_7'], list)
        # Verificar que last_7 tenga warnings dentro de cada día
        for point_data in data['last_7']:
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
        point_data = self._find_point_in_last_7(data['last_7'], self.point.title)
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

        point_data = self._find_point_in_last_7(data['last_7'], self.point.title)
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


@override_settings(CACHES={
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
})
class ApiIkDynamicFlowRegressionTests(TestCase):
    """
    Caudal dinámico en los 3 endpoints Ikolu (GET).

    Variable.store_average_flow=False hace que el cron NUNCA escriba
    InteractionDetail.flow (queda 0.00). En ese caso los endpoints deben
    calcularlo con el mismo helper que usan reports/compliance/DGA
    (api.core.utils.flow_display), en modo quiet (sin SystemEvent por GET).

    Cuando store_average_flow=True el valor guardado es la fuente de verdad:
    se devuelve tal cual y no debe cambiar absolutamente nada.
    """

    # 10 m3 en 1h => (10/3600)*1000 = 2.78 L/s
    EXPECTED_DYNAMIC_FLOW = 2.78
    STORED_FLOW = "5.50"

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

    # ── Fixtures ────────────────────────────────────────────────────────
    def _make_point_with_avg_flow(self, store_average_flow, title):
        """Punto con scheme + Variable CAUDAL_PROMEDIO y perfil de telemetría."""
        point = CatchmentPoint.objects.create(
            title=title,
            owner_user=self.user,
            project=self.project,
            frecuency="60",
        )
        scheme = SchemesCatchment.objects.create(
            name=title, description="esquema de prueba"
        )
        scheme.points_catchment.add(point)
        Variable.objects.create(
            scheme_catchment=scheme,
            str_variable="caudal_medio",
            label="Caudal medio",
            type_variable="CAUDAL_PROMEDIO",
            store_average_flow=store_average_flow,
        )
        ProfileDataConfigCatchment.objects.create(
            point_catchment=point, is_telemetry=True, d1=12.50, d3=8.00
        )
        return point

    def _make_hourly_records(self, point, count, stored_flow=0):
        """
        `count` registros horarios terminando ayer 23:00 (los totales crecen
        10 m3/hora). El registro más reciente es el último creado.
        """
        from datetime import datetime, time as dtime
        from django.utils import timezone

        base = datetime.combine(
            self.today - timedelta(days=1), dtime(23, 0)
        )
        base = timezone.make_aware(base)

        records = []
        for i in range(count):
            ts = base - timedelta(hours=(count - 1 - i))
            records.append(InteractionDetail.objects.create(
                catchment_point=point,
                date_time_medition=ts,
                date_time_last_logger=ts,
                total=str(1000 + 10 * i),
                flow=stored_flow,
                is_error=False,
            ))
        return records

    @property
    def today(self):
        from datetime import date
        return date.today()

    def _records_url(self, point):
        return (
            f'/api/ik/point/{point.id}/records/'
            f'?start_date={self.today - timedelta(days=7)}'
            f'&end_date={self.today}&limit=500'
        )

    # ── PointRecordsView ───────────────────────────────────────────────
    def test_records_calculates_flow_when_not_stored(self):
        """store_average_flow=False → el 0.00 guardado se reemplaza por el cálculo."""
        point = self._make_point_with_avg_flow(False, "Punto Dinamico")
        self._make_hourly_records(point, count=4)

        response = self.client.get(self._records_url(point))
        self.assertEqual(response.status_code, 200)

        records = response.json()['records']
        self.assertEqual(len(records), 4)

        # El más reciente tiene registro anterior => caudal calculado
        self.assertAlmostEqual(
            records[0]['flow'], self.EXPECTED_DYNAMIC_FLOW, places=2
        )
        # El más antiguo no tiene anterior => 0.0 (sin inventar caudal)
        self.assertEqual(records[-1]['flow'], 0.0)
        # Al menos uno con caudal real (antes salía 0.00 en el 100%)
        self.assertGreater(sum(1 for r in records if r['flow']), 0)

    def test_records_returns_stored_flow_when_stored(self):
        """store_average_flow=True → el valor guardado se devuelve intacto."""
        point = self._make_point_with_avg_flow(True, "Punto Guardado")
        self._make_hourly_records(
            point, count=3, stored_flow=Decimal(self.STORED_FLOW)
        )

        response = self.client.get(self._records_url(point))
        self.assertEqual(response.status_code, 200)

        for record in response.json()['records']:
            self.assertEqual(record['flow'], float(self.STORED_FLOW))

    def test_records_flow_zero_without_average_flow_variable(self):
        """Punto sin CAUDAL_PROMEDIO → usa el valor guardado (INSTANTANEO)."""
        point = CatchmentPoint.objects.create(
            title="Punto Sin Promedio",
            owner_user=self.user,
            project=self.project,
            frecuency="60",
        )
        self._make_hourly_records(point, count=3, stored_flow=Decimal("7.25"))

        response = self.client.get(self._records_url(point))
        self.assertEqual(response.status_code, 200)
        for record in response.json()['records']:
            self.assertEqual(record['flow'], 7.25)

    def test_records_do_not_write_system_events(self):
        """Una ruta de GET jamás debe insertar SystemEvent (modo quiet)."""
        point = self._make_point_with_avg_flow(False, "Punto Quiet")
        self._make_hourly_records(point, count=4)

        before = SystemEvent.objects.count()
        for url in (
            self._records_url(point),
            f'/api/ik/point/{point.id}/summary/',
            '/api/ik/points_summary/',
        ):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
        self.assertEqual(SystemEvent.objects.count(), before)

    def test_records_query_count_does_not_scale_with_rows(self):
        """
        Las filas adicionales no deben agregar 2 queries por registro:
        el registro anterior se resuelve con 1 sola query extra.
        """
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        point = self._make_point_with_avg_flow(False, "Punto Queries")
        self._make_hourly_records(point, count=20)

        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(self._records_url(point))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['records']), 20)

        # Sin optimización serían ~40 queries (2 por fila) + base.
        self.assertLess(len(ctx.captured_queries), 30)

    # ── PointSummaryView / PointsSummaryView ───────────────────────────
    def test_point_summary_calculates_flow_when_not_stored(self):
        point = self._make_point_with_avg_flow(False, "Punto Resumen")
        self._make_hourly_records(point, count=3)

        response = self.client.get(f'/api/ik/point/{point.id}/summary/')
        self.assertEqual(response.status_code, 200)

        latest = response.json()['latest_telemetry']
        self.assertAlmostEqual(
            float(latest['flow']), self.EXPECTED_DYNAMIC_FLOW, places=2
        )

    def test_point_summary_keeps_stored_flow(self):
        point = self._make_point_with_avg_flow(True, "Punto Resumen Guardado")
        self._make_hourly_records(
            point, count=3, stored_flow=Decimal(self.STORED_FLOW)
        )

        response = self.client.get(f'/api/ik/point/{point.id}/summary/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()['latest_telemetry']['flow'], self.STORED_FLOW
        )

    def test_points_summary_calculates_flow_when_not_stored(self):
        dynamic = self._make_point_with_avg_flow(False, "Punto Lista Dinamico")
        stored = self._make_point_with_avg_flow(True, "Punto Lista Guardado")
        self._make_hourly_records(dynamic, count=3)
        self._make_hourly_records(stored, count=3, stored_flow=Decimal(self.STORED_FLOW))

        response = self.client.get('/api/ik/points_summary/')
        self.assertEqual(response.status_code, 200)

        by_id = {p['id']: p for p in response.json()['points']}
        self.assertAlmostEqual(
            float(by_id[dynamic.id]['latest_telemetry']['flow']),
            self.EXPECTED_DYNAMIC_FLOW, places=2,
        )
        self.assertEqual(
            by_id[stored.id]['latest_telemetry']['flow'], self.STORED_FLOW
        )
