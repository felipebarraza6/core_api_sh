"""
Tests de regresión: tolerancia a configs DGA duplicadas.

Causa raíz (auditoría 2026-10-07, puntos 241/242): DgaDataConfigCatchment.objects.get()
lanzaba MultipleObjectsReturned cuando un punto tenía 2 configs, lo que rompía:
- validate_frequency / determine_dga_send -> send_dga=False silencioso
- telemetry_unified -> point sin envío DGA
- cron_sma -> registro marcado en error
"""
from datetime import datetime
from unittest.mock import patch

import pytz
from django.test import TestCase
from django.utils import timezone

from api.core.models import (
    CatchmentPoint,
    Client,
    DgaDataConfigCatchment,
    InteractionDetail,
    ProfileDataConfigCatchment,
    ProjectCatchments,
    User,
)
from api.cronjobs.dga.cron_dga import _get_dga_config
from api.cronjobs.telemetry.controllers import unified_processing
from api.cronjobs.telemetry.controllers.unified_processing import (
    determine_dga_send,
    validate_frequency,
)


class DgaConfigDuplicatesTests(TestCase):
    """El lookup de config DGA debe tolerar duplicados (preferir la activa)."""

    def setUp(self):
        self.chile_tz = pytz.timezone("America/Santiago")
        user = User.objects.create(username="dupuser", email="dup@example.com")
        client_obj = Client.objects.create(name="Dup Client")
        project = ProjectCatchments.objects.create(name="Dup Project", client=client_obj)
        self.point = CatchmentPoint.objects.create(
            title="Dup Point", owner_user=user, project=project
        )
        ProfileDataConfigCatchment.objects.create(
            point_catchment=self.point, is_telemetry=True
        )
        # El signal create_related_profiles ya creó una config por defecto
        self.cfg_default = DgaDataConfigCatchment.objects.get(
            point_catchment=self.point
        )
        self.cfg_default.standard = "SIN_ESTANDAR"
        self.cfg_default.send_dga = False
        self.cfg_default.save()
        # Config duplicada y activa (misma situación de producción: pts 241/242)
        self.cfg_active = DgaDataConfigCatchment.objects.create(
            point_catchment=self.point,
            standard="MAYOR",
            send_dga=True,
            code_dga="DUP-001",
            rut_report_dga="12345678-9",
            password_dga_software="testpass",
            type_dga="SUPERFICIAL",
        )
        self.point_dict = {"id": self.point.id}

    def test_validate_frequency_tolerates_duplicated_configs(self):
        """Con configs duplicadas, validate_frequency debe usar la activa (MAYOR)."""
        hora = datetime(2026, 1, 1, 10, 0, 0, tzinfo=self.chile_tz)
        self.assertTrue(validate_frequency(self.point_dict, hora, "60"))
        self.assertFalse(
            validate_frequency(self.point_dict, hora.replace(minute=30), "60")
        )

    def test_validate_frequency_without_config_returns_false(self):
        """Punto sin config DGA: no lanza, retorna False."""
        point2 = CatchmentPoint.objects.create(
            title="Sin Config",
            owner_user=self.cfg_default.point_catchment.owner_user,
            project=self.cfg_default.point_catchment.project,
        )
        DgaDataConfigCatchment.objects.filter(point_catchment=point2).delete()
        hora = datetime(2026, 1, 1, 10, 0, 0, tzinfo=self.chile_tz)
        self.assertFalse(validate_frequency({"id": point2.id}, hora, "60"))

    def test_determine_dga_send_tolerates_duplicated_configs(self):
        """determine_dga_send con duplicados debe resolver con la config activa."""
        fixed = datetime(2026, 1, 1, 10, 0, 0, tzinfo=self.chile_tz)
        with patch.object(unified_processing, "datetime") as mock_dt:
            mock_dt.now.return_value = fixed
            self.assertTrue(determine_dga_send(self.point_dict, self.chile_tz))

    def test_determine_dga_send_without_config_returns_false(self):
        point2 = CatchmentPoint.objects.create(
            title="Sin Config 2",
            owner_user=self.cfg_default.point_catchment.owner_user,
            project=self.cfg_default.point_catchment.project,
        )
        DgaDataConfigCatchment.objects.filter(point_catchment=point2).delete()
        fixed = datetime(2026, 1, 1, 10, 0, 0, tzinfo=self.chile_tz)
        with patch.object(unified_processing, "datetime") as mock_dt:
            mock_dt.now.return_value = fixed
            self.assertFalse(determine_dga_send({"id": point2.id}, self.chile_tz))

    def test_get_dga_config_prefers_active_config(self):
        """cron_dga._get_dga_config debe preferir la config con send_dga=True."""
        now = timezone.now()
        register = InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=now,
            total="1000",
            total_diff=10,
            flow=2.78,
            water_table=5.0,
        )
        cfg = _get_dga_config(register)
        self.assertIsNotNone(cfg)
        self.assertEqual(cfg.id, self.cfg_active.id)
        self.assertTrue(cfg.send_dga)
        self.assertEqual(cfg.code_dga, "DUP-001")

    def test_single_config_lookup_unchanged(self):
        """Con una sola config, el comportamiento no cambia."""
        DgaDataConfigCatchment.objects.filter(id=self.cfg_active.id).delete()
        hora = datetime(2026, 1, 1, 10, 0, 0, tzinfo=self.chile_tz)
        # La única config quedó SIN_ESTANDAR (minute < 60 -> True en hora en punto)
        self.assertTrue(validate_frequency(self.point_dict, hora, "60"))
