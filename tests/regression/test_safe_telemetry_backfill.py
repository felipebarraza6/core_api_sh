"""
Tests del backfill seguro de telemetría (Tago / late readings).
===============================================================

Cubre:
- dry-run no escribe
- filas con voucher DGA intactas
- horas faltantes se insertan
- réplicas congeladas se actualizan solo bajo el criterio
- conversión UTC → Chile en hora del logger
- idempotencia (segunda corrida no cambia nada)
- send_dga no se toca
"""

from datetime import datetime, timedelta
from unittest.mock import patch

import pytz
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from api.core.models import (
    CatchmentPoint,
    Client,
    InteractionDetail,
    ProfileDataConfigCatchment,
    ProjectCatchments,
    SchemesCatchment,
    Variable,
)
from api.core.services.telemetry_backfill import (
    REASON_INSERT,
    REASON_SKIP_DGA,
    REASON_SKIP_MATCHES,
    REASON_UPDATE_FROZEN_PULSES,
    backfill_point_from_providers,
    decide_bucket_action,
    has_dga_voucher,
)
from api.cronjobs.telemetry.utils.connection import utc_iso_to_chile_str

User = get_user_model()
CHILE = pytz.timezone("America/Santiago")


class UtcHelperTests(TestCase):
    def test_utc_iso_to_chile_summer(self):
        """2026-10-02T18:51:24Z → 15:51:24 hora Chile (UTC-3 verano)."""
        self.assertEqual(
            utc_iso_to_chile_str("2026-10-02T18:51:24.000Z"),
            "2026-10-02T15:51:24",
        )

    def test_utc_iso_to_chile_winter(self):
        """2026-07-24T10:27:14Z → 06:27:14 hora Chile (UTC-4 invierno)."""
        self.assertEqual(
            utc_iso_to_chile_str("2026-07-24T10:27:14.000Z"),
            "2026-07-24T06:27:14",
        )


class DecideBucketActionTests(TestCase):
    def test_insert_when_missing(self):
        action, reason = decide_bucket_action(None, None, 100, "2026-09-20T10:05:00", True)
        self.assertEqual(action, "insert")
        self.assertEqual(reason, REASON_INSERT)

    def test_skip_dga_voucher(self):
        existing = InteractionDetail(pulses=50, is_error=False, n_voucher="ABC-123")
        action, reason = decide_bucket_action(existing, None, 200, "2026-09-20T10:05:00", True)
        self.assertEqual(action, "skip")
        self.assertEqual(reason, REASON_SKIP_DGA)
        self.assertTrue(has_dga_voucher(existing))


class SafeBackfillServiceTests(TestCase):
    """Tests del servicio backfill_point_from_providers en modo seguro."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="bfuser", password="pass", email="bf@example.com"
        )
        self.client_obj = Client.objects.create(name="BF Client")
        self.project = ProjectCatchments.objects.create(
            name="BF Project", client=self.client_obj
        )
        self.point = CatchmentPoint.objects.create(
            title="Pelarco-like",
            owner_user=self.user,
            project=self.project,
            frecuency="60",
            is_novus=True,
        )
        ProfileDataConfigCatchment.objects.create(
            point_catchment=self.point,
            is_telemetry=True,
            token_service="TAGO_TOKEN",
            addition=0.0,
        )
        self.scheme = SchemesCatchment.objects.create(name="BF Scheme", description="t")
        self.scheme.points_catchment.add(self.point)
        self.var_total = Variable.objects.create(
            scheme_catchment=self.scheme,
            str_variable="total_var",
            label="Acumulado",
            type_variable="TOTALIZADO",
            pulses_factor=1000,
        )
        self.var_flow = Variable.objects.create(
            scheme_catchment=self.scheme,
            str_variable="flow_var",
            label="Caudal",
            type_variable="CAUDAL",
            convert_to_lt=False,
            calculate_nivel=1,
        )

        # Ventana: 20-sep 10:00 → 20-sep 14:00 (Chile)
        self.start = CHILE.localize(datetime(2026, 9, 20, 10, 0, 0))
        self.end = CHILE.localize(datetime(2026, 9, 20, 14, 0, 0))

    def _make_history(self, readings):
        """
        readings: list of (chile_naive_dt, pulses, flow)
        Simula histórico Tago: ts_ms en epoch UTC, date_time ya en Chile
        (como get_data_tago_history post-fix).
        """
        out = []
        for chile_naive, pulses, flow in readings:
            aware = CHILE.localize(chile_naive)
            out.append({
                "ts_ms": int(aware.timestamp() * 1000),
                "value": pulses,
                "date_time": chile_naive.strftime("%Y-%m-%dT%H:%M:%S"),
                "_flow": flow,
            })
        return out

    def _history_side_effect(self, readings_by_var):
        def _side_effect(provider, token_service, str_variable, start_dt, end_dt, limit=10000):
            return list(readings_by_var.get(str_variable, []))
        return _side_effect

    def _seed_frozen_and_dga(self):
        """
        10:00 real (pulses=1000)
        11:00 congelada (pulses=1000, sin voucher) — proveedor traerá 1100
        12:00 congelada CON voucher DGA (pulses=1000) — no tocar
        13:00 ausente — proveedor traerá 1300
        """
        base_logger = CHILE.localize(datetime(2026, 9, 20, 10, 5, 0))
        r10 = InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=self.start,
            date_time_last_logger=base_logger,
            pulses=1000,
            total="1000",
            flow=1.5,
            is_error=False,
            send_dga=False,
        )
        r11 = InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=self.start + timedelta(hours=1),
            date_time_last_logger=base_logger,  # misma marca → réplica
            pulses=1000,  # mismo valor → frozen
            total="1000",
            flow=1.5,
            is_error=False,
            send_dga=False,
        )
        r12 = InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=self.start + timedelta(hours=2),
            date_time_last_logger=base_logger,
            pulses=1000,
            total="1000",
            flow=1.5,
            is_error=False,
            send_dga=True,
            n_voucher="DGA-VOUCHER-12",
        )
        return r10, r11, r12

    def _provider_readings(self):
        """Histórico real del proveedor para 10–13h."""
        totals = self._make_history([
            (datetime(2026, 9, 20, 10, 5, 0), 1000, 1.5),
            (datetime(2026, 9, 20, 11, 5, 0), 1100, 2.0),
            (datetime(2026, 9, 20, 12, 5, 0), 1200, 2.2),
            (datetime(2026, 9, 20, 13, 5, 0), 1300, 2.5),
        ])
        flows = []
        for item in totals:
            flows.append({
                "ts_ms": item["ts_ms"],
                "value": item["_flow"],
                "date_time": item["date_time"],
            })
        # limpiar campo auxiliar
        for item in totals:
            item.pop("_flow", None)
        return {"total_var": totals, "flow_var": flows}

    @patch("api.core.services.telemetry_backfill.get_data_tago_history")
    def test_dry_run_writes_nothing(self, mock_hist):
        self._seed_frozen_and_dga()
        mock_hist.side_effect = self._history_side_effect(self._provider_readings())
        before = list(
            InteractionDetail.objects.filter(catchment_point=self.point)
            .order_by("date_time_medition")
            .values_list("id", "pulses", "n_voucher", "send_dga", "total", "is_error")
        )

        result = backfill_point_from_providers(
            self.point, self.start, self.end, dry_run=True, safe=True
        )

        self.assertTrue(result["success"])
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["mode"], "dry-run")
        self.assertGreater(result["records_created"], 0)  # 13:00 missing
        self.assertGreater(result["records_updated"], 0)  # 11:00 frozen
        self.assertGreater(result["records_skipped"], 0)  # 12:00 DGA + maybe 10:00

        after = list(
            InteractionDetail.objects.filter(catchment_point=self.point)
            .order_by("date_time_medition")
            .values_list("id", "pulses", "n_voucher", "send_dga", "total", "is_error")
        )
        self.assertEqual(before, after)
        self.assertEqual(
            InteractionDetail.objects.filter(catchment_point=self.point).count(), 3
        )

    @patch("api.core.services.telemetry_backfill.get_data_tago_history")
    def test_dga_accepted_rows_untouched(self, mock_hist):
        _, _, r12 = self._seed_frozen_and_dga()
        mock_hist.side_effect = self._history_side_effect(self._provider_readings())

        result = backfill_point_from_providers(
            self.point, self.start, self.end, dry_run=False, safe=True
        )

        r12.refresh_from_db()
        self.assertEqual(r12.pulses, 1000)
        self.assertEqual(r12.n_voucher, "DGA-VOUCHER-12")
        self.assertTrue(r12.send_dga)
        self.assertEqual(r12.total, "1000")
        self.assertEqual(result["by_reason"].get(REASON_SKIP_DGA), 1)

        # Verificar en hours report
        dga_hours = [h for h in result["hours"] if h["reason"] == REASON_SKIP_DGA]
        self.assertEqual(len(dga_hours), 1)
        self.assertEqual(dga_hours[0]["bucket"], "2026-09-20T12:00:00")

    @patch("api.core.services.telemetry_backfill.get_data_tago_history")
    def test_missing_hours_inserted(self, mock_hist):
        self._seed_frozen_and_dga()
        mock_hist.side_effect = self._history_side_effect(self._provider_readings())

        result = backfill_point_from_providers(
            self.point, self.start, self.end, dry_run=False, safe=True
        )

        self.assertGreaterEqual(result["records_created"], 1)
        r13 = InteractionDetail.objects.get(
            catchment_point=self.point,
            date_time_medition=self.start + timedelta(hours=3),
        )
        self.assertEqual(r13.pulses, 1300)
        self.assertFalse(r13.send_dga)
        self.assertFalse(r13.n_voucher)
        # Logger en hora Chile (13:05), no UTC
        self.assertEqual(
            r13.date_time_last_logger.astimezone(CHILE).strftime("%Y-%m-%dT%H:%M:%S"),
            "2026-09-20T13:05:00",
        )

    @patch("api.core.services.telemetry_backfill.get_data_tago_history")
    def test_frozen_rows_updated_under_criterion(self, mock_hist):
        _, r11, _ = self._seed_frozen_and_dga()
        mock_hist.side_effect = self._history_side_effect(self._provider_readings())

        result = backfill_point_from_providers(
            self.point, self.start, self.end, dry_run=False, safe=True
        )

        r11.refresh_from_db()
        self.assertEqual(r11.pulses, 1100)
        self.assertEqual(
            r11.date_time_last_logger.astimezone(CHILE).strftime("%Y-%m-%dT%H:%M:%S"),
            "2026-09-20T11:05:00",
        )
        self.assertFalse(r11.is_error)
        self.assertIn(
            result["by_reason"].get(REASON_UPDATE_FROZEN_PULSES, 0)
            + result["by_reason"].get("frozen_replica_logger_ts", 0),
            (1, 2),
        )
        # send_dga intacto
        self.assertFalse(r11.send_dga)

    @patch("api.core.services.telemetry_backfill.get_data_tago_history")
    def test_valid_non_frozen_row_skipped(self, mock_hist):
        """10:00 ya tiene el valor correcto del proveedor → skip already_matches."""
        self._seed_frozen_and_dga()
        mock_hist.side_effect = self._history_side_effect(self._provider_readings())

        result = backfill_point_from_providers(
            self.point, self.start, self.end, dry_run=False, safe=True
        )
        r10 = InteractionDetail.objects.get(
            catchment_point=self.point, date_time_medition=self.start
        )
        self.assertEqual(r10.pulses, 1000)
        self.assertGreaterEqual(
            result["by_reason"].get(REASON_SKIP_MATCHES, 0)
            + result["by_reason"].get("existing_valid", 0),
            1,
        )

    @patch("api.core.services.telemetry_backfill.get_data_tago_history")
    def test_utc_logger_conversion_from_raw_tago(self, mock_hist):
        """
        Si el getter devolviera date_time UTC crudo + ts_ms, el logger
        guardado debe quedar en hora Chile vía ts_ms.
        """
        # 18:05 UTC = 15:05 Chile (verano)
        utc_dt = datetime(2026, 9, 20, 18, 5, 0, tzinfo=pytz.utc)
        chile_bucket = CHILE.localize(datetime(2026, 9, 20, 15, 0, 0))

        def side_effect(provider, token_service, str_variable, start_dt, end_dt, limit=10000):
            if str_variable == "total_var":
                return [{
                    "ts_ms": int(utc_dt.timestamp() * 1000),
                    "value": 5000,
                    "date_time": "2026-09-20T18:05:00",  # crudo UTC sin Z
                }]
            return [{
                "ts_ms": int(utc_dt.timestamp() * 1000),
                "value": 3.0,
                "date_time": "2026-09-20T18:05:00",
            }]

        mock_hist.side_effect = side_effect
        start = chile_bucket
        end = chile_bucket + timedelta(hours=1)

        result = backfill_point_from_providers(
            self.point, start, end, dry_run=False, safe=True
        )
        self.assertEqual(result["records_created"], 1)
        rec = InteractionDetail.objects.get(catchment_point=self.point)
        self.assertEqual(
            rec.date_time_last_logger.astimezone(CHILE).strftime("%Y-%m-%dT%H:%M:%S"),
            "2026-09-20T15:05:00",
        )
        self.assertEqual(
            rec.date_time_medition.astimezone(CHILE).strftime("%Y-%m-%dT%H:%M:%S"),
            "2026-09-20T15:00:00",
        )

    @patch("api.core.services.telemetry_backfill.get_data_tago_history")
    def test_idempotency_second_run_no_changes(self, mock_hist):
        self._seed_frozen_and_dga()
        mock_hist.side_effect = self._history_side_effect(self._provider_readings())

        first = backfill_point_from_providers(
            self.point, self.start, self.end, dry_run=False, safe=True
        )
        self.assertGreater(first["records_created"] + first["records_updated"], 0)

        snapshot = list(
            InteractionDetail.objects.filter(catchment_point=self.point)
            .order_by("date_time_medition")
            .values_list(
                "date_time_medition", "pulses", "flow", "total",
                "n_voucher", "send_dga", "is_error",
                "date_time_last_logger",
            )
        )

        second = backfill_point_from_providers(
            self.point, self.start, self.end, dry_run=False, safe=True
        )
        self.assertEqual(second["records_created"], 0)
        self.assertEqual(second["records_updated"], 0)
        self.assertGreater(second["records_skipped"], 0)

        snapshot2 = list(
            InteractionDetail.objects.filter(catchment_point=self.point)
            .order_by("date_time_medition")
            .values_list(
                "date_time_medition", "pulses", "flow", "total",
                "n_voucher", "send_dga", "is_error",
                "date_time_last_logger",
            )
        )
        self.assertEqual(snapshot, snapshot2)

    @patch("api.core.services.telemetry_backfill.get_data_tago_history")
    def test_is_error_row_updated_without_forcing_others(self, mock_hist):
        """Fila is_error sin voucher se actualiza; is_error pasa a False solo ahí."""
        err = InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=self.start,
            date_time_last_logger=self.start,
            pulses=0,
            total="0",
            is_error=True,
            send_dga=False,
        )
        readings = self._make_history([(datetime(2026, 9, 20, 10, 5, 0), 42, 1.0)])
        for item in readings:
            item.pop("_flow", None)
        mock_hist.side_effect = self._history_side_effect({
            "total_var": readings,
            "flow_var": [{
                "ts_ms": readings[0]["ts_ms"],
                "value": 1.0,
                "date_time": readings[0]["date_time"],
            }],
        })

        result = backfill_point_from_providers(
            self.point, self.start, self.end, dry_run=False, safe=True
        )
        err.refresh_from_db()
        self.assertEqual(err.pulses, 42)
        self.assertFalse(err.is_error)
        self.assertEqual(result["by_reason"].get("is_error"), 1)

    @patch("api.core.services.telemetry_backfill.get_data_tago_history")
    def test_send_dga_never_modified(self, mock_hist):
        r10, r11, r12 = self._seed_frozen_and_dga()
        # Marcar 11:00 en cola DGA sin voucher aún
        r11.send_dga = True
        r11.save(update_fields=["send_dga"])
        mock_hist.side_effect = self._history_side_effect(self._provider_readings())

        backfill_point_from_providers(
            self.point, self.start, self.end, dry_run=False, safe=True
        )
        r11.refresh_from_db()
        r12.refresh_from_db()
        # 11:00 se actualizó (frozen) pero send_dga sigue True
        self.assertEqual(r11.pulses, 1100)
        self.assertTrue(r11.send_dga)
        self.assertTrue(r12.send_dga)
        self.assertEqual(r12.n_voucher, "DGA-VOUCHER-12")


class SafeBackfillEndpointTests(TestCase):
    """POST /api/ik/telemetry/backfill/ — dry_run default ON."""

    def setUp(self):
        self.api = APIClient()
        self.user = User.objects.create_user(
            username="apiuser", password="pass", email="api@example.com", is_staff=True
        )
        self.api.force_authenticate(user=self.user)
        self.client_obj = Client.objects.create(name="API Client")
        self.project = ProjectCatchments.objects.create(
            name="API Project", client=self.client_obj
        )
        self.point = CatchmentPoint.objects.create(
            title="Norte-like",
            owner_user=self.user,
            project=self.project,
            frecuency="60",
            is_novus=True,
        )
        ProfileDataConfigCatchment.objects.create(
            point_catchment=self.point,
            is_telemetry=True,
            token_service="TOK",
        )
        scheme = SchemesCatchment.objects.create(name="S", description="d")
        scheme.points_catchment.add(self.point)
        Variable.objects.create(
            scheme_catchment=scheme,
            str_variable="tv",
            label="T",
            type_variable="TOTALIZADO",
            pulses_factor=1000,
        )

    @patch("api.core.services.telemetry_backfill.get_data_tago_history")
    def test_endpoint_defaults_to_dry_run(self, mock_hist):
        chile = CHILE.localize(datetime(2026, 9, 20, 10, 5, 0))
        mock_hist.return_value = [{
            "ts_ms": int(chile.timestamp() * 1000),
            "value": 99,
            "date_time": "2026-09-20T10:05:00",
        }]
        response = self.api.post(
            "/api/ik/telemetry/backfill/",
            {
                "point_id": self.point.id,
                "start": "2026-09-20T10:00:00",
                "end": "2026-09-20T11:00:00",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertTrue(data["dry_run"])
        self.assertEqual(data["mode"], "dry-run")
        self.assertEqual(
            InteractionDetail.objects.filter(catchment_point=self.point).count(), 0
        )
        self.assertIn("by_reason", data)
        self.assertIn("hours", data)

    @patch("api.core.services.telemetry_backfill.get_data_tago_history")
    def test_endpoint_apply_writes(self, mock_hist):
        chile = CHILE.localize(datetime(2026, 9, 20, 10, 5, 0))
        mock_hist.return_value = [{
            "ts_ms": int(chile.timestamp() * 1000),
            "value": 99,
            "date_time": "2026-09-20T10:05:00",
        }]
        response = self.api.post(
            "/api/ik/telemetry/backfill/",
            {
                "point_id": self.point.id,
                "start": "2026-09-20T10:00:00",
                "end": "2026-09-20T11:00:00",
                "apply": True,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["dry_run"])
        self.assertEqual(data["mode"], "applied")
        self.assertEqual(data["records_created"], 1)
        self.assertEqual(
            InteractionDetail.objects.filter(catchment_point=self.point).count(), 1
        )
