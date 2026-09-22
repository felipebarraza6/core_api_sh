"""
Benchmark de queries para GET /api/ik/compliance/.
===================================================

Mide que el endpoint no genere N+1 con múltiples puntos.
Patrón: CaptureQueriesContext (igual que test_management_api.py).
"""
from datetime import date, datetime, timedelta

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from api.core.models import (
    CatchmentPoint, Client, ProjectCatchments,
    InteractionDetail, DgaDataConfigCatchment,
    ProfileDataConfigCatchment,
)

User = get_user_model()


class ComplianceQueriesBenchmarkTests(TestCase):
    """Mide queries de /api/ik/compliance/ con varios puntos."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='benchuser',
            password='testpass123',
            email='bench@example.com'
        )
        self.client.force_authenticate(user=self.user)

        self.client_obj = Client.objects.create(name="Bench Client")
        self.project = ProjectCatchments.objects.create(
            name="Bench Project", client=self.client_obj
        )

        # Crear 6 puntos con compliance + interacciones
        # para que el N+1 sea evidente (6 * 2 counts + 6 * 2 last = 24+ queries extra)
        self.points = []
        for i in range(6):
            point = CatchmentPoint.objects.create(
                title=f"Bench Point {i}",
                owner_user=self.user,
                project=self.project,
                frecuency="60",
                is_tdata=True,
            )
            ProfileDataConfigCatchment.objects.create(
                point_catchment=point,
                is_telemetry=True,
            )
            DgaDataConfigCatchment.objects.create(
                point_catchment=point,
                send_dga=True,
                code_dga=f"OB-BENCH-{i:04d}-DGA",
                standard="MAYOR",
                type_dga="SUPERFICIAL",
                flow_granted_dga=10.0,
                total_granted_dga=1000.0,
            )
            # Varias interacciones por punto (excedencias, near limit, voucher)
            now = timezone.now()
            InteractionDetail.objects.create(
                catchment_point=point,
                date_time_medition=now - timedelta(days=30),
                total_diff=0,
                total="100",
                flow=15.0,  # excede 10
            )
            InteractionDetail.objects.create(
                catchment_point=point,
                date_time_medition=now - timedelta(days=15),
                total_diff=100,
                total="200",
                flow=9.5,  # near limit (90-100%)
                n_voucher=f"VCH-{i}",
            )
            InteractionDetail.objects.create(
                catchment_point=point,
                date_time_medition=now,
                total_diff=50,
                total="250",
                flow=5.0,
                n_voucher=f"VCH-LATEST-{i}",
            )
            self.points.append(point)

    def test_compliance_no_n1_queries(self):
        """GET /api/ik/compliance/ no debe generar N+1 con 6 puntos."""
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get('/api/ik/compliance/')
            self.assertEqual(response.status_code, 200)
            queries = len(ctx.captured_queries)

        data = response.json()
        self.assertEqual(data['count'], 6)

        # Con N+1 (2 counts/punto + 2 last/punto = 24+ queries solo para eso)
        # más las queries base (~10-15), estaríamos en 27+ queries.
        # Con batch (DISTINCT ON + OR-agregado): 12 queries fijas.
        self.assertLess(
            queries, 15,
            f"Demasiadas queries ({queries}), posible N+1 en compliance"
        )

    def test_compliance_no_n1_with_order_by_exceedances(self):
        """order_by=exceedances_desc no debe amplificar N+1."""
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(
                '/api/ik/compliance/?order_by=exceedances_desc'
            )
            self.assertEqual(response.status_code, 200)
            queries = len(ctx.captured_queries)

        self.assertLess(
            queries, 15,
            f"Demasiadas queries ({queries}) con order_by=exceedances_desc"
        )

    def test_compliance_no_n1_with_pagination(self):
        """Paginación no debe disparar N+1 en last_map."""
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(
                '/api/ik/compliance/?page_size=3&page=1'
            )
            self.assertEqual(response.status_code, 200)
            queries = len(ctx.captured_queries)

        data = response.json()
        self.assertEqual(data['count'], 6)
        self.assertEqual(len(data['points']), 3)

        self.assertLess(
            queries, 15,
            f"Demasiadas queries ({queries}) con paginación"
        )
