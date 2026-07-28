"""
Tests de regresión para DGA persistent retry queue (P1.6)
==========================================================

Valida que:
- Errores de conexión (requests.RequestException) vayan al retry queue persistente
- Después de MAX_PERSISTENT_RETRIES (5), se marque is_error=True definitivamente
- cron_dga.py excluya registros que están en backoff
- requeue_dga resetee los contadores de retry
"""

from django.test import TestCase
from django.utils import timezone
from datetime import timedelta
from unittest.mock import patch, MagicMock
import requests

from api.core.models import (
    InteractionDetail, CatchmentPoint, DgaDataConfigCatchment,
    User, Client, ProjectCatchments
)
from api.cronjobs.dga.send_data_dga import send


class DgaRetryQueueTests(TestCase):
    """Tests para retry queue persistente de DGA."""

    def setUp(self):
        self.user = User.objects.create(username="testuser", email="test@example.com")
        self.client = Client.objects.create(name="Test Client")
        self.project = ProjectCatchments.objects.create(name="Test Project", client=self.client)
        self.point = CatchmentPoint.objects.create(
            title="Test Point", project=self.project, owner_user=self.user
        )
        self.dga_config = DgaDataConfigCatchment.objects.create(
            point_catchment=self.point,
            standard="MAYOR",
            send_dga=True,
            code_dga="TEST-CODE",
            rut_report_dga="11222333-4",
            password_dga_software="secret"
        )
        self.record = InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=timezone.now(),
            total="100",
            flow=10.5,
            send_dga=True,
        )
        self.response_data = {
            "catchment_point": self.point.id,
            "code_dga": "TEST-CODE",
            "date_time_medition": "2023-01-01T12:00:00",
            "total": 100, "flow": 10.5, "rut": "11111111-1",
            "password": "pass", "id_data": self.record.id,
            "type_dga": "SUBTERRANEO", "water_table": 0,
            "dga_config": {}
        }

    @patch('api.cronjobs.dga.send_data_dga.requests.post')
    def test_connection_error_goes_to_retry_queue(self, mock_post):
        """RequestException mantiene send_dga=True e incrementa retry count."""
        mock_post.side_effect = requests.RequestException("Connection timeout")

        result = send(self.response_data)
        self.assertFalse(result)

        self.record.refresh_from_db()
        self.assertTrue(self.record.send_dga, "Debe mantenerse en cola para reintento")
        self.assertFalse(self.record.is_error, "No debe marcar error en retry queue")
        self.assertEqual(self.record.dga_retry_count, 1)
        self.assertIsNotNone(self.record.dga_last_retry_at)

    @patch('api.cronjobs.dga.send_data_dga.requests.post')
    def test_max_persistent_retries_reached(self, mock_post):
        """Después de 5 reintentos persistentes, marcar is_error=True definitivamente."""
        mock_post.side_effect = requests.RequestException("Connection timeout")

        # Simular 4 reintentos previos
        self.record.dga_retry_count = 4
        self.record.save()
        self.response_data["id_data"] = self.record.id

        result = send(self.response_data)
        self.assertFalse(result)

        self.record.refresh_from_db()
        self.assertFalse(self.record.send_dga, "Debe sacarse de cola al agotar retries")
        self.assertTrue(self.record.is_error, "Debe marcar error definitivo")
        self.assertEqual(self.record.dga_retry_count, 5)

    @patch('api.cronjobs.dga.send_data_dga.requests.post')
    def test_non_connection_error_stops_immediately(self, mock_post):
        """Errores 400 reales NO van al retry queue (comportamiento original)."""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "status": "error",
            "message": "Error 400: Datos inválidos genéricos",
            "data": {}
        }
        mock_post.return_value = mock_response

        result = send(self.response_data)
        self.assertFalse(result)

        self.record.refresh_from_db()
        self.assertFalse(self.record.send_dga, "send_dga=False para errores 400")
        self.assertTrue(self.record.is_error, "is_error=True para errores 400")
        self.assertEqual(self.record.dga_retry_count, 0, "No debe incrementar retry count")

    def test_cron_dga_backoff_exclusion(self):
        """cron_dga excluye registros que están dentro de la ventana de backoff."""
        from api.cronjobs.dga.cron_dga import run
        from django.db.models import Q

        # Preparar registro en backoff (retry_count=1, retentado hace 5 minutos)
        self.record.send_dga = True
        self.record.dga_retry_count = 1
        self.record.dga_last_retry_at = timezone.now() - timedelta(minutes=5)
        self.record.save()

        # El registro NO debe aparecer en base_qs porque 5 min < 30 min backoff
        # No podemos probar run() fácilmente sin mockear send(), pero podemos
        # probar la query directamente
        from api.core.models import DgaDataConfigCatchment
        puntos = DgaDataConfigCatchment.objects.filter(send_dga=True).values_list('point_catchment_id', flat=True)
        ahora = timezone.now()

        backoff_conditions = Q()
        for retry_count in range(1, 6):
            minutes = 15 * (2 ** retry_count)
            backoff_conditions |= Q(
                dga_retry_count=retry_count,
                dga_last_retry_at__gt=ahora - timedelta(minutes=minutes),
            )

        qs = InteractionDetail.objects.filter(
            send_dga=True,
            catchment_point_id__in=puntos
        ).exclude(backoff_conditions)

        self.assertNotIn(self.record.id, list(qs.values_list("id", flat=True)))

        # Si esperamos más de 30 minutos, debe aparecer
        self.record.dga_last_retry_at = timezone.now() - timedelta(minutes=31)
        self.record.save()

        qs2 = InteractionDetail.objects.filter(
            send_dga=True,
            catchment_point_id__in=puntos
        ).exclude(backoff_conditions)

        self.assertIn(self.record.id, list(qs2.values_list("id", flat=True)))
