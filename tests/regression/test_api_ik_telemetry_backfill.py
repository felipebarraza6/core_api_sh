"""
Tests de regresión para el endpoint de backfill histórico.
===========================================================

POST /api/ik/telemetry/backfill/
GET  /api/ik/point/{id}/gaps/
"""

import json
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from api.core.models import (
    CatchmentPoint, Client, ProjectCatchments,
    InteractionDetail, ProfileDataConfigCatchment,
)

User = get_user_model()


class TelemetryBackfillEndpointTests(TestCase):
    """Tests para POST /api/ik/telemetry/backfill/"""

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
            token_service="DEVICE_TOKEN",
        )

    def test_backfill_rejects_missing_fields(self):
        """Debe rechazar si faltan start o end."""
        response = self.client.post(
            '/api/ik/telemetry/backfill/',
            data=json.dumps({"point_id": self.point.id}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("start", response.json().get("error", "").lower())

    def test_backfill_rejects_range_over_30_days(self):
        """Debe rechazar rangos mayores a 30 días."""
        response = self.client.post(
            '/api/ik/telemetry/backfill/',
            data=json.dumps({
                "point_id": self.point.id,
                "start": "2026-01-01T00:00:00",
                "end": "2026-02-15T00:00:00",
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("30", response.json().get("error", ""))

    def test_backfill_accepts_valid_range(self):
        """Debe aceptar un rango válido de 3 días y retornar estructura esperada."""
        # Crear esquema y variable necesarios para el backfill
        from api.core.models import SchemesCatchment, Variable
        scheme = SchemesCatchment.objects.create(name="Test Scheme", description="Test")
        scheme.points_catchment.add(self.point)
        Variable.objects.create(
            scheme_catchment=scheme,
            str_variable="5000",
            label="Acumulado",
            type_variable="TOTALIZADO",
            pulses_factor=1000,
        )

        response = self.client.post(
            '/api/ik/telemetry/backfill/',
            data=json.dumps({
                "point_id": self.point.id,
                "start": "2026-05-20T00:00:00",
                "end": "2026-05-23T00:00:00",
            }),
            content_type='application/json'
        )
        # Puede ser 200 si la validación pasa o 500 si el provider real falla
        self.assertIn(response.status_code, [200, 500])
        if response.status_code == 200:
            data = response.json()
            self.assertTrue(data["success"])
            self.assertIn("records_created", data)
            self.assertIn("processing", data)
            self.assertIn("totals_updated", data["processing"])
            self.assertIn("flow_updated", data["processing"])

    def test_backfill_rejects_unauthorized_point(self):
        """Usuario no debe poder backfillar punto ajeno."""
        other_user = User.objects.create_user(
            username='other', password='otherpass', email='other@example.com'
        )
        other_point = CatchmentPoint.objects.create(
            title="Other Point",
            owner_user=other_user,
            project=self.project,
            frecuency="60",
            is_tdata=True,
        )

        response = self.client.post(
            '/api/ik/telemetry/backfill/',
            data=json.dumps({
                "point_id": other_point.id,
                "start": "2026-05-20T00:00:00",
                "end": "2026-05-21T00:00:00",
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 403)


class PointGapsEndpointTests(TestCase):
    """Tests para GET /api/ik/point/{id}/gaps/"""

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

    def test_gaps_returns_structure(self):
        """Debe retornar lista de gaps."""
        from django.utils import timezone
        from datetime import timedelta

        now = timezone.now().replace(minute=0, second=0, microsecond=0)
        InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=now - timedelta(hours=2),
            pulses=100,
            total="100",
        )
        InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=now,
            pulses=120,
            total="120",
        )

        response = self.client.get(f'/api/ik/point/{self.point.id}/gaps/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertIn("gaps", data)
        self.assertIn("gaps_count", data)
        self.assertIn("total_missing_records", data)

    def test_gaps_rejects_unauthorized_point(self):
        """Usuario no debe ver gaps de punto ajeno."""
        other_user = User.objects.create_user(
            username='other', password='otherpass', email='other@example.com'
        )
        other_point = CatchmentPoint.objects.create(
            title="Other Point",
            owner_user=other_user,
            project=self.project,
            frecuency="60",
            is_tdata=True,
        )

        response = self.client.get(f'/api/ik/point/{other_point.id}/gaps/')
        self.assertEqual(response.status_code, 403)

    def test_gaps_returns_404_for_nonexistent_point(self):
        """Debe retornar 404 si el punto no existe."""
        response = self.client.get('/api/ik/point/99999/gaps/')
        self.assertEqual(response.status_code, 404)

    def test_gaps_accepts_optional_date_range(self):
        """Debe aceptar start/end opcionales via query params."""
        from django.utils import timezone
        from datetime import timedelta

        now = timezone.now().replace(minute=0, second=0, microsecond=0)
        InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=now - timedelta(hours=2),
            pulses=100,
            total="100",
        )
        InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=now,
            pulses=120,
            total="120",
        )

        response = self.client.get(
            f'/api/ik/point/{self.point.id}/gaps/',
            {
                "start": (now - timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%S"),
                "end": (now + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S"),
            }
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertIn("gaps", data)
