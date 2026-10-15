"""
Tests: lectores sin errores falsos (auditoría 02-10-2026)
========================================================

Cubre los 5 hallazgos:
1. Fallo de getter → missing/failed, nunca value=0
2. Saltos falsos (Venecia #25): baseline no envenenado por pulses=0 inventados
3. Códigos negativos del logger (-2) → WARNING, no se guardan como pulses
4. Deduplicación de alertas "Pulsos cero" (una abierta por punto/condición)
5. UTC → America/Santiago en Tago y TheThings (utc_iso_to_chile_str)
"""

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytz
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from api.core.models import (
    CatchmentPoint,
    Client,
    InteractionDetail,
    ProfileDataConfigCatchment,
    ProjectCatchments,
    SchemesCatchment,
    Variable,
)
from api.core.models.alerts import SystemEvent
from api.cronjobs.telemetry.controllers.total import total_m3
from api.cronjobs.telemetry.controllers.unified_processing import (
    get_data_with_retry,
    process_totalizado_variable,
)
from api.cronjobs.telemetry.getters.tago import get_data_tago
from api.cronjobs.telemetry.getters.thingsio import get_data_thethings
from api.cronjobs.telemetry.telemetry_unified import _process_point
from api.cronjobs.telemetry.utils.audit import emit_system_event, resolve_system_events
from api.cronjobs.telemetry.utils.connection import utc_iso_to_chile_str
from api.cronjobs.telemetry.utils.getter_result import (
    STATUS_NO_DATA,
    STATUS_REQUEST_FAILED,
    is_getter_success,
    no_data_result,
    ok_result,
    request_failed_result,
)

User = get_user_model()


class GetterResultContractTests(SimpleTestCase):
    """Item 1 — contrato de respuesta del getter."""

    def test_ok_vs_no_data_vs_request_failed(self):
        self.assertTrue(is_getter_success(ok_result(10, "2026-09-30T14:00:00")))
        self.assertFalse(is_getter_success(no_data_result()))
        self.assertFalse(is_getter_success(request_failed_result(error="timeout")))
        self.assertEqual(no_data_result()["status"], STATUS_NO_DATA)
        self.assertEqual(request_failed_result()["status"], STATUS_REQUEST_FAILED)
        self.assertIsNone(request_failed_result()["value"])

    def test_get_data_with_retry_no_data_does_not_retry(self):
        calls = {"n": 0}

        def getter():
            calls["n"] += 1
            return no_data_result()

        result = get_data_with_retry(getter, max_retries=3)
        self.assertEqual(result["status"], STATUS_NO_DATA)
        self.assertEqual(calls["n"], 1)

    def test_get_data_with_retry_request_failed_retries_then_returns_failure(self):
        calls = {"n": 0}

        def getter():
            calls["n"] += 1
            return request_failed_result(error="HTTP 503", http_status=503)

        with patch("api.cronjobs.telemetry.controllers.unified_processing.time.sleep"):
            result = get_data_with_retry(getter, max_retries=3)

        self.assertEqual(result["status"], STATUS_REQUEST_FAILED)
        self.assertEqual(calls["n"], 3)
        self.assertIsNone(result["value"])
        self.assertEqual(result.get("http_status"), 503)


class GetterNeverInventZeroTests(TestCase):
    """Item 1 — el runner no inventa total/pulsos=0 ante fallo de getter."""

    def setUp(self):
        self.user = User.objects.create_user(username="g1", password="x")
        self.client_obj = Client.objects.create(name="C")
        self.project = ProjectCatchments.objects.create(name="P", client=self.client_obj)
        self.point = CatchmentPoint.objects.create(
            title="Venecia-like", owner_user=self.user, project=self.project, frecuency="60"
        )
        ProfileDataConfigCatchment.objects.filter(point_catchment=self.point).update(
            is_telemetry=True
        )
        now = timezone.now()
        InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=now - timedelta(hours=1),
            total="19213",
            pulses=36533,
            total_diff=0,
            flow=0.0,
            is_error=False,
            date_time_last_logger=now - timedelta(hours=1),
        )

    @patch("api.cronjobs.telemetry.telemetry_unified.get_data_with_retry")
    def test_failed_getter_keeps_last_pulses_not_zero(self, mock_get):
        mock_get.return_value = request_failed_result(error="timeout", http_status=None)

        scheme = SchemesCatchment.objects.create(name="S", description="t")
        scheme.points_catchment.add(self.point)
        Variable.objects.create(
            scheme_catchment=scheme,
            str_variable="totalizador",
            label="Total",
            type_variable="TOTALIZADO",
            token_service="tok",
            service="NETTRA",
            pulses_factor=1000,
        )

        now = timezone.now()
        chile = pytz.timezone("America/Santiago")
        now = chile.localize(now.replace(tzinfo=None)) if now.tzinfo is None else now.astimezone(chile)

        point_data = {
            "id": self.point.id,
            "profile_data_config": {
                "token_service": "",
                "scheme": {
                    "name": "S",
                    "variables": [
                        {
                            "id": 1,
                            "str_variable": "totalizador",
                            "type_variable": "TOTALIZADO",
                            "token_service": "tok",
                            "service": "NETTRA",
                            "pulses_factor": 1000,
                            "convert_to_lt": False,
                            "calculate_nivel": None,
                            "store_average_flow": False,
                            "min_value": None,
                            "max_value": None,
                            "display_key": None,
                            "provider": {"handler_name": "thethings"},
                        }
                    ],
                },
                "replicate_on_missing": False,
                "use_transaction_atomic": True,
            },
        }

        _process_point(point_data, now, "60", dry_run=False)

        record = InteractionDetail.objects.filter(
            catchment_point=self.point,
            date_time_medition=now.strftime("%Y-%m-%dT%H:00:00"),
        ).first()
        self.assertIsNotNone(record)
        self.assertTrue(record.is_error)
        # No inventó pulses=0: conservó el último válido
        self.assertEqual(record.pulses, 36533)
        self.assertEqual(str(record.total), "19213")
        self.assertEqual(record.total_diff, 0)

        event = SystemEvent.objects.filter(
            point_catchment=self.point, event_type="API_ERROR"
        ).first()
        self.assertIsNotNone(event)
        self.assertIn("sin respuesta", event.title.lower())
        self.assertNotEqual(event.extra_data.get("value"), 0)

    @patch("api.cronjobs.telemetry.telemetry_unified.get_data_with_retry")
    def test_no_data_status_distinct_from_request_failed(self, mock_get):
        mock_get.return_value = no_data_result()

        scheme = SchemesCatchment.objects.create(name="S2", description="t")
        scheme.points_catchment.add(self.point)
        Variable.objects.create(
            scheme_catchment=scheme,
            str_variable="totalizador",
            label="Total",
            type_variable="TOTALIZADO",
            token_service="tok",
            service="NETTRA",
            pulses_factor=1000,
        )

        now = timezone.now()
        chile = pytz.timezone("America/Santiago")
        now = chile.localize(now.replace(tzinfo=None)) if now.tzinfo is None else now.astimezone(chile)

        point_data = {
            "id": self.point.id,
            "profile_data_config": {
                "token_service": "",
                "scheme": {
                    "name": "S2",
                    "variables": [
                        {
                            "id": 2,
                            "str_variable": "totalizador",
                            "type_variable": "TOTALIZADO",
                            "token_service": "tok",
                            "pulses_factor": 1000,
                            "provider": {"handler_name": "thethings"},
                        }
                    ],
                },
                "replicate_on_missing": False,
                "use_transaction_atomic": True,
            },
        }

        _process_point(point_data, now, "60", dry_run=False)

        event = SystemEvent.objects.filter(
            point_catchment=self.point, event_type="API_ERROR"
        ).first()
        self.assertIsNotNone(event)
        self.assertIn("sin datos", event.title.lower())
        self.assertEqual(event.extra_data.get("status"), STATUS_NO_DATA)


class VeneciaFalseJumpTests(TestCase):
    """Item 2 — recuperación tras fallo no genera salto falso."""

    def setUp(self):
        self.user = User.objects.create_user(username="v25", password="x")
        self.client_obj = Client.objects.create(name="C")
        self.project = ProjectCatchments.objects.create(name="P", client=self.client_obj)
        self.point = CatchmentPoint.objects.create(
            title="Venecia 1", owner_user=self.user, project=self.project
        )
        self.profile = ProfileDataConfigCatchment.objects.get(point_catchment=self.point)
        self.profile.max_diff_m3_per_hour = 500
        self.profile.addition = -17320  # como en auditoría: total≈19213 con pulses=36533
        self.profile.save()
        self.point_data = {
            "id": self.point.id,
            "profile_data_config": {
                "max_diff_m3_per_hour": 500,
                "reconnection_threshold_hours": 2,
                "addition": -17320,
            },
        }

    def test_error_record_excluded_from_baseline_no_false_jump(self):
        now = timezone.now()
        # Lectura válida
        InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=now - timedelta(hours=2),
            total="19213",
            pulses=36533,
            total_diff=0,
            flow=0.0,
            is_error=False,
        )
        # Registro de fallo envenenado (comportamiento viejo: pulses=0)
        InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=now - timedelta(hours=1),
            total="0",
            pulses=0,
            total_diff=0,
            flow=0.0,
            is_error=True,
        )

        # Vuelve el dato real del proveedor (fijo 36533)
        result, meta = total_m3(
            pulses_factor=1000,
            value=36533,
            point_catchment=self.point_data,
            current_dt=now,
            return_full_details=True,
        )

        # Baseline debe ser el válido (19213), no el error con total=0
        # total = 36533 + (-17320) = 19213 → sin salto
        self.assertEqual(result, 19213)
        self.assertEqual(meta["status"], "OK")
        # No debe emitir MASSIVE_JUMP por recuperar desde el 0 falso
        self.assertFalse(
            SystemEvent.objects.filter(
                point_catchment=self.point,
                event_type="MASSIVE_JUMP_BLOCKED",
            ).exists()
        )


class DeviceStatusCodeTests(TestCase):
    """Item 3 — códigos negativos del logger."""

    def setUp(self):
        self.user = User.objects.create_user(username="c57", password="x")
        self.client_obj = Client.objects.create(name="C")
        self.project = ProjectCatchments.objects.create(name="P", client=self.client_obj)
        self.point = CatchmentPoint.objects.create(
            title="Coca Cola P1", owner_user=self.user, project=self.project
        )
        ProfileDataConfigCatchment.objects.filter(point_catchment=self.point).update(addition=0)
        now = timezone.now()
        InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=now - timedelta(hours=1),
            total="202993",
            pulses=202993,
            total_diff=10,
            flow=0.0,
        )
        self.point_data = {
            "id": self.point.id,
            "profile_data_config": {"max_diff_m3_per_hour": 500, "addition": 0},
        }
        self.now = now

    def test_code_minus_two_is_warning_not_critical(self):
        result, meta = total_m3(
            1000, -2, self.point_data, current_dt=self.now, return_full_details=True
        )
        self.assertEqual(result, 202993)
        self.assertEqual(meta["status"], "DEVICE_STATUS_CODE")

        event = SystemEvent.objects.filter(point_catchment=self.point).first()
        self.assertIsNotNone(event)
        self.assertEqual(event.severity, "WARNING")
        self.assertIn("-2", event.title)
        self.assertFalse(
            SystemEvent.objects.filter(
                point_catchment=self.point, severity="CRITICAL"
            ).exists()
        )

    def test_process_totalizado_does_not_store_status_code_as_pulses(self):
        created = {"date_time_medition": self.now.strftime("%Y-%m-%dT%H:00:00")}
        data = ok_result(-2, self.now.strftime("%Y-%m-%dT%H:%M:%S"))
        variable = {"str_variable": "5000", "type_variable": "TOTALIZADO", "pulses_factor": 1000}

        _, created = process_totalizado_variable(
            data, variable, self.point_data, created, current_dt=self.now
        )

        self.assertEqual(created["pulses"], 202993)  # último válido, no -2
        self.assertEqual(created["total"], 202993)
        self.assertTrue(created.get("is_error"))


class PulsesZeroDedupTests(TestCase):
    """Item 4 — una sola alerta abierta de pulsos cero por punto."""

    def setUp(self):
        self.user = User.objects.create_user(username="pz", password="x")
        self.client_obj = Client.objects.create(name="C")
        self.project = ProjectCatchments.objects.create(name="P", client=self.client_obj)
        self.point = CatchmentPoint.objects.create(
            title="Punto pulsos", owner_user=self.user, project=self.project
        )
        now = timezone.now()
        InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=now - timedelta(hours=1),
            total="1000",
            pulses=1000,
            total_diff=0,
            flow=0.0,
        )
        self.point_data = {
            "id": self.point.id,
            "profile_data_config": {"max_diff_m3_per_hour": 500, "addition": 0},
        }
        self.now = now

    def test_pulses_zero_deduped_until_resolved(self):
        total_m3(1000, 0, self.point_data, current_dt=self.now)
        total_m3(1000, 0, self.point_data, current_dt=self.now + timedelta(hours=1))
        total_m3(1000, 0, self.point_data, current_dt=self.now + timedelta(hours=2))

        count = SystemEvent.objects.filter(
            point_catchment=self.point,
            title="Pulsos cero con histórico previo",
        ).count()
        self.assertEqual(count, 1)

        # Se resuelve al volver un valor > 0
        total_m3(1000, 1100, self.point_data, current_dt=self.now + timedelta(hours=3))
        open_count = (
            SystemEvent.objects.filter(
                point_catchment=self.point,
                title="Pulsos cero con histórico previo",
            )
            .exclude(extra_data__resolved=True)
            .count()
        )
        self.assertEqual(open_count, 0)

        # Nueva condición puede abrir otra alerta
        InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=self.now + timedelta(hours=3),
            total="1100",
            pulses=1100,
            total_diff=100,
            flow=0.0,
            is_error=False,
        )
        total_m3(1000, 0, self.point_data, current_dt=self.now + timedelta(hours=4))
        self.assertEqual(
            SystemEvent.objects.filter(
                point_catchment=self.point,
                title="Pulsos cero con histórico previo",
            )
            .exclude(extra_data__resolved=True)
            .count(),
            1,
        )


class UtcToChileTimestampTests(SimpleTestCase):
    """Item 5 — helper utc_iso_to_chile_str (misma firma que 7dfca11)."""

    def test_utc_iso_to_chile_str_signature_and_dst(self):
        # Verano (UTC-3)
        self.assertEqual(
            utc_iso_to_chile_str("2026-09-30T17:44:00.000Z"),
            "2026-09-30T14:44:00",
        )
        # Invierno (UTC-4)
        self.assertEqual(
            utc_iso_to_chile_str("2026-07-01T16:00:00.000Z"),
            "2026-07-01T12:00:00",
        )
        self.assertEqual(
            utc_iso_to_chile_str("2026-09-30T17:44:00Z"),
            "2026-09-30T14:44:00",
        )
        self.assertIsNone(utc_iso_to_chile_str(None))
        self.assertIsNone(utc_iso_to_chile_str(""))


class TagoTheThingsTimestampConversionTests(TestCase):
    """Item 5 — getters Tago/TheThings convierten UTC → Chile."""

    @patch("api.cronjobs.telemetry.getters.thingsio.requests.request")
    def test_thethings_converts_utc_to_chile(self, mock_req):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = [
            {"value": 36533.6, "datetime": "2026-09-22T17:44:00.000Z"}
        ]
        mock_req.return_value = mock_resp

        result = get_data_thethings(
            {"handler_name": "thethings"}, "TOKEN", "totalizador"
        )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["date_time"], "2026-09-22T14:44:00")
        self.assertAlmostEqual(float(result["value"]), 36533.6)

    @patch("api.cronjobs.telemetry.getters.thingsio.requests.request")
    def test_thethings_request_failed_no_fake_zero(self, mock_req):
        mock_req.side_effect = __import__("requests").Timeout("timeout")
        result = get_data_thethings({"handler_name": "thethings"}, "TOKEN", "x")
        self.assertEqual(result["status"], STATUS_REQUEST_FAILED)
        self.assertIsNone(result["value"])
        self.assertIsNone(result["date_time"])

    @patch("api.cronjobs.telemetry.getters.tago.requests.request")
    def test_tago_converts_utc_to_chile(self, mock_req):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {
            "result": [{"value": 99.5, "time": "2026-10-02T18:51:24.000Z"}]
        }
        mock_req.return_value = mock_resp

        result = get_data_tago({"handler_name": "tago"}, "TOKEN", "flow")
        self.assertEqual(result["status"], "ok")
        # 18:51 UTC → 15:51 Chile (verano UTC-3)
        self.assertEqual(result["date_time"], "2026-10-02T15:51:24")

    @patch("api.cronjobs.telemetry.getters.tago.requests.request")
    def test_tago_preserves_negative_status_codes(self, mock_req):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {
            "result": [{"value": -2, "time": "2026-10-01T14:07:26.000Z"}]
        }
        mock_req.return_value = mock_resp

        result = get_data_tago({"handler_name": "tago"}, "TOKEN", "5000")
        self.assertEqual(result["value"], -2)
        self.assertEqual(result["status"], "ok")


class EmitSystemEventDedupTests(TestCase):
    """Soporte de dedupe_until_resolved en audit helper."""

    def setUp(self):
        self.user = User.objects.create_user(username="dedup", password="x")
        self.client_obj = Client.objects.create(name="C")
        self.project = ProjectCatchments.objects.create(name="P", client=self.client_obj)
        self.point = CatchmentPoint.objects.create(
            title="Dedup", owner_user=self.user, project=self.project
        )

    def test_dedupe_until_resolved_and_resolve(self):
        emit_system_event(
            event_type="MEASUREMENT_ERROR",
            point_id=self.point.id,
            title="Pulsos cero con histórico previo",
            message="a",
            severity="WARNING",
            condition_key=f"pulses_zero:{self.point.id}",
            dedupe_until_resolved=True,
        )
        emit_system_event(
            event_type="MEASUREMENT_ERROR",
            point_id=self.point.id,
            title="Pulsos cero con histórico previo",
            message="b",
            severity="WARNING",
            condition_key=f"pulses_zero:{self.point.id}",
            dedupe_until_resolved=True,
        )
        self.assertEqual(SystemEvent.objects.filter(point_catchment=self.point).count(), 1)

        resolve_system_events(self.point.id, f"pulses_zero:{self.point.id}")
        evt = SystemEvent.objects.get(point_catchment=self.point)
        self.assertTrue(evt.extra_data.get("resolved"))
