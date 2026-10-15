"""
Regresión auditoría 30-09-2026: días sin conexión y fecha del logger.
Tests puros (sin base de datos).
"""
from datetime import datetime

import pytz
from django.test import SimpleTestCase

from api.cronjobs.telemetry.utils.connection import (
    days_since,
    freshest_logger_ts,
    parse_logger_ts,
    stale_variables,
    utc_iso_to_chile_str,
)

CL = pytz.timezone("America/Santiago")


class ConnectionDaysTests(SimpleTestCase):
    def test_totalizador_caido_no_marca_desconexion(self):
        # CPP Pozo 4: totalizado sin actualizar hace 160 días, caudal y nivel frescos.
        ts = {
            "TOTALIZADO": parse_logger_ts("2026-04-23T13:00:00"),
            "CAUDAL": parse_logger_ts("2026-09-30T13:06:32"),
            "NIVEL": parse_logger_ts("2026-09-30T13:05:10"),
        }
        now = CL.localize(datetime(2026, 9, 30, 13, 10))
        best = freshest_logger_ts(ts.values())
        self.assertEqual(days_since(best, now), 0)
        self.assertEqual(stale_variables(ts, best), ["TOTALIZADO"])

    def test_sin_fecha_no_simula_conexion(self):
        # Ninguna variable trajo fecha: no hay fecha "fresca" que usar.
        self.assertIsNone(freshest_logger_ts([None, None]))
        self.assertEqual(days_since(None, datetime(2026, 9, 30)), 0)

    def test_desconexion_real(self):
        now = CL.localize(datetime(2026, 9, 30, 15, 0))
        best = freshest_logger_ts(["2026-09-16T09:00:00", None])
        self.assertEqual(days_since(best, now), 14)

    def test_thethings_utc_a_chile(self):
        # Horario de verano (UTC-3)
        self.assertEqual(utc_iso_to_chile_str("2026-09-30T17:44:00.000Z"), "2026-09-30T14:44:00")
        # Horario de invierno (UTC-4)
        self.assertEqual(utc_iso_to_chile_str("2026-07-01T16:00:00.000Z"), "2026-07-01T12:00:00")
        self.assertEqual(utc_iso_to_chile_str("2026-09-30T17:44:00Z"), "2026-09-30T14:44:00")
        self.assertIsNone(utc_iso_to_chile_str(None))

    def test_parse_aware_datetime(self):
        aware = pytz.utc.localize(datetime(2026, 9, 30, 18, 0))
        self.assertEqual(parse_logger_ts(aware), datetime(2026, 9, 30, 15, 0))
