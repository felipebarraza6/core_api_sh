"""
Tests del envío DGA seguro (auditoría 2026-10-02).

Ítem 1: no enviar is_error=True; no borrar is_error al aceptar.
"""
from django.test import TestCase
from django.utils import timezone
from datetime import timedelta
from unittest.mock import patch, MagicMock
import pytz

from api.core.models import (
    InteractionDetail,
    CatchmentPoint,
    DgaDataConfigCatchment,
    ProfileDataConfigCatchment,
    User,
    Client,
    ProjectCatchments,
)
from api.cronjobs.dga.cron_dga import _validate_register, _prepare_response_data
from api.cronjobs.dga.send_data_dga import send


class DgaSafeSendTests(TestCase):
    """Registros con is_error no se envían; aceptación no limpia is_error."""

    def setUp(self):
        self.chile_tz = pytz.timezone("America/Santiago")
        self.user = User.objects.create(username="dga_safe", email="dga@test.com")
        self.client_obj = Client.objects.create(name="Client Safe")
        self.project = ProjectCatchments.objects.create(
            name="Project Safe", client=self.client_obj
        )
        self.point = CatchmentPoint.objects.create(
            title="Point Safe", owner_user=self.user, project=self.project
        )
        # El signal create_related_profiles ya crea Profile + Dga configs
        self.profile = ProfileDataConfigCatchment.objects.get(point_catchment=self.point)
        self.profile.is_telemetry = True
        self.profile.addition = 100
        self.profile.d6 = 5000
        self.profile.save()
        self.dga_config = DgaDataConfigCatchment.objects.get(point_catchment=self.point)
        self.dga_config.standard = "MAYOR"
        self.dga_config.send_dga = True
        self.dga_config.code_dga = "SAFE-001"
        self.dga_config.rut_report_dga = "12345678-9"
        self.dga_config.password_dga_software = "testpass"
        self.dga_config.type_dga = "SUBTERRANEO"
        self.dga_config.save()

    def test_validate_register_rejects_is_error(self):
        """_validate_register debe rechazar registros con is_error=True."""
        register = InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=timezone.now(),
            total="1000",
            send_dga=True,
            is_error=True,
        )
        self.assertFalse(_validate_register(register))

    def test_queue_queryset_excludes_is_error(self):
        """La cola DGA base excluye is_error=True (mismo filtro que cron_dga.run)."""
        good = InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=timezone.now(),
            total="1000",
            send_dga=True,
            is_error=False,
        )
        bad = InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=timezone.now() - timedelta(hours=1),
            total="0",
            send_dga=True,
            is_error=True,
        )
        puntos = DgaDataConfigCatchment.objects.filter(
            send_dga=True
        ).values_list("point_catchment_id", flat=True)
        qs = InteractionDetail.objects.filter(
            send_dga=True,
            catchment_point_id__in=puntos,
            is_error=False,
        )
        ids = list(qs.values_list("id", flat=True))
        self.assertIn(good.id, ids)
        self.assertNotIn(bad.id, ids)

    @patch("api.cronjobs.dga.send_data_dga.requests.post")
    def test_dga_acceptance_does_not_clear_is_error(self, mock_post):
        """Cuando la DGA acepta, is_error de ingesta NO se borra."""
        register = InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=timezone.now(),
            total="1000",
            flow=1.5,
            water_table=5.0,
            send_dga=True,
            is_error=True,  # marca de ingesta previa
        )
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "00",
            "message": "OK",
            "data": {"numeroComprobante": "ABC123"},
        }
        mock_post.return_value = mock_response

        payload = {
            "catchment_point": self.point.title,
            "code_dga": "SAFE-001",
            "date_time_medition": "2026-09-28T22:00:00",
            "total": "1000",
            "flow": 1.5,
            "rut": "12345678-9",
            "password": "testpass",
            "id_data": register.id,
            "type_dga": "SUBTERRANEO",
            "water_table": 5.0,
            "dga_config": {},
        }
        result = send(payload)
        self.assertTrue(result)
        register.refresh_from_db()
        self.assertFalse(register.send_dga)
        self.assertEqual(register.n_voucher, "ABC123")
        self.assertTrue(
            register.is_error,
            "Aceptación DGA no debe borrar is_error de ingesta",
        )

    @patch("api.cronjobs.dga.send_data_dga.requests.post")
    def test_dga_duplicate_does_not_clear_is_error(self, mock_post):
        """Duplicado aceptado tampoco limpia is_error."""
        register = InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=timezone.now(),
            total="1000",
            flow=1.5,
            water_table=5.0,
            send_dga=True,
            is_error=True,
        )
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "message": "Ya existe un registro. Comprobante: DUP999",
            "data": {},
        }
        mock_post.return_value = mock_response

        payload = {
            "catchment_point": self.point.title,
            "code_dga": "SAFE-001",
            "date_time_medition": "2026-09-28T22:00:00",
            "total": "1000",
            "flow": 1.5,
            "rut": "12345678-9",
            "password": "testpass",
            "id_data": register.id,
            "type_dga": "SUBTERRANEO",
            "water_table": 5.0,
            "dga_config": {},
        }
        result = send(payload)
        self.assertTrue(result)
        register.refresh_from_db()
        self.assertTrue(register.is_error)

    def test_prepare_response_uses_totalizer_views(self):
        """DGA recibe stored - addition vía resolve_totalizer_views."""
        register = InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=timezone.now().astimezone(self.chile_tz),
            total="1100",  # stored = raw + addition(100)
            total_diff=10,
            flow=2.0,
            water_table=5.0,
        )
        result = _prepare_response_data(register, self.dga_config)
        self.assertIsNotNone(result)
        # 1100 - 100 = 1000
        self.assertEqual(str(result["total"]), "1000")
