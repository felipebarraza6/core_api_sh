"""
Regresión auditoría 30-09-2026: runner unificado y corrección retroactiva.
"""
from datetime import datetime
from io import StringIO
from unittest.mock import patch

import pytz
from django.core.management import call_command
from django.test import TestCase

from api.core.models import (
    CatchmentPoint, Client, InteractionDetail, ProfileDataConfigCatchment, ProjectCatchments, User,
)
from api.cronjobs.telemetry import telemetry_unified

CL = pytz.timezone("America/Santiago")

VARS = [
    {"id": 1, "str_variable": "TOT", "type_variable": "TOTALIZADO", "pulses_factor": 1000},
    {"id": 2, "str_variable": "CAU", "type_variable": "CAUDAL", "convert_to_lt": False},
    {"id": 3, "str_variable": "NIV", "type_variable": "NIVEL"},
]


class RunnerConnectionTests(TestCase):
    def setUp(self):
        user = User.objects.create(username="u", email="u@x.cl")
        client = Client.objects.create(name="C")
        project = ProjectCatchments.objects.create(name="P", client=client)
        self.point = CatchmentPoint.objects.create(title="Pozo", owner_user=user, project=project)
        ProfileDataConfigCatchment.objects.create(point_catchment=self.point, is_telemetry=True)
        self.pc = {
            "id": self.point.id,
            "frecuency": "60",
            "profile_data_config": {"d3": 10.0, "nivel_offset": 0, "scheme": {"variables": VARS}},
        }
        self.now = CL.localize(datetime(2026, 9, 30, 13, 10))

    def _run(self, responses):
        def fake(getter, provider, token, str_variable):
            return responses[str_variable]
        with patch.object(telemetry_unified, "get_data_with_retry", side_effect=fake), \
             patch.object(telemetry_unified, "DgaDataConfigCatchment") as dga:
            dga.DoesNotExist = Exception
            dga.objects.get.side_effect = Exception("sin config")
            telemetry_unified._process_point(self.pc, self.now, "60", False)
        return InteractionDetail.objects.filter(catchment_point=self.point).order_by("-date_time_medition").first()

    def test_totalizador_caido_logger_vivo(self):
        rec = self._run({
            "TOT": {"value": 0, "date_time": "2026-04-23T13:00:00"},
            "CAU": {"value": 4.0, "date_time": "2026-09-30T13:06:32"},
            "NIV": {"value": 33.1, "date_time": "2026-09-30T13:05:00"},
        })
        self.assertEqual(rec.days_not_conection, 0)
        self.assertEqual(rec.date_time_last_logger.astimezone(CL).strftime("%Y-%m-%dT%H:%M:%S"), "2026-09-30T13:06:32")
        stale = [d["str_variable"] for d in rec.variable_details if d.get("stale")]
        self.assertEqual(stale, ["TOT"])

    def test_sin_datos_no_simula_conexion(self):
        InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=CL.localize(datetime(2026, 9, 16, 9, 0)),
            date_time_last_logger=CL.localize(datetime(2026, 9, 16, 8, 44)),
            total="100", pulses=100,
        )
        self._run({
            "TOT": {"value": 0, "date_time": None},
            "CAU": {"value": 0.0, "date_time": None},
            "NIV": {"value": 0.0, "date_time": None},
        })
        rec = InteractionDetail.objects.filter(catchment_point=self.point).order_by("-date_time_medition").first()
        self.assertEqual(rec.days_not_conection, 14)
        self.assertNotEqual(rec.date_time_last_logger, rec.date_time_medition)


class FixConnectionHistoryTests(TestCase):
    def setUp(self):
        user = User.objects.create(username="u2", email="u2@x.cl")
        client = Client.objects.create(name="C2")
        project = ProjectCatchments.objects.create(name="P2", client=client)
        self.point = CatchmentPoint.objects.create(title="Dren", owner_user=user, project=project)
        mk = lambda h, logger, total, pulses, ok=True, voucher=None: InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=CL.localize(datetime(2026, 9, 29, h, 0)),
            date_time_last_logger=logger,
            total=total, pulses=pulses, days_not_conection=0 if logger == CL.localize(datetime(2026, 9, 29, h, 0)) else 13,
            variable_details=[{"str_variable": "TOT", "type_variable": "TOTALIZADO", "success": ok}],
            n_voucher=voucher,
        )
        real = CL.localize(datetime(2026, 9, 16, 8, 44))
        self.r0 = mk(0, real, "15634640", 3629030)
        self.r1 = mk(1, CL.localize(datetime(2026, 9, 29, 1, 0)), "12005610", 0, ok=False)
        self.r2 = mk(2, CL.localize(datetime(2026, 9, 29, 2, 0)), "12005610", 0, ok=False, voucher="V1")
        self.r3 = mk(3, real, "15634640", 3629030)

    def _cmd(self, *extra):
        out = StringIO()
        call_command("fix_connection_history", "--since", "2026-09-28", "--phases", "A,C", *extra, stdout=out)
        return out.getvalue()

    def test_simulacion_no_escribe(self):
        self._cmd()
        self.r1.refresh_from_db()
        self.assertEqual(self.r1.total, "12005610")

    def test_apply_corrige_y_respeta_dga(self):
        self._cmd("--apply")
        for r in (self.r1, self.r2, self.r3):
            r.refresh_from_db()
        self.assertEqual(self.r1.total, "15634640")
        self.assertTrue(self.r1.is_error)
        self.assertEqual(self.r1.days_not_conection, 12)
        self.assertEqual(self.r2.total, "12005610")  # enviado a DGA: no se toca
        self.assertEqual(self.r3.total_diff, 0)
