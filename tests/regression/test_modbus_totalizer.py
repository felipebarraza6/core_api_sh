"""
Tests para totalizador Modbus de dos registros (HI + LO).
=========================================================

Cubre:
- Combinación HI*65536 + LO
- Wrap 65535→0 y LO==65536
- Mid-rollover desfasado (LO ahead / HI ahead) sin negativos ni spikes
- Integración con process_variable_safely → pulses/total/total_diff
"""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from api.core.models import (
    CatchmentPoint,
    Client,
    InteractionDetail,
    ProfileDataConfigCatchment,
    ProjectCatchments,
    User,
)
from api.cronjobs.telemetry.controllers.modbus_totalizer import (
    MODBUS_UINT16_MODULUS,
    combine_modbus_registers,
    combine_raw,
    is_modbus_hi_type,
    is_modbus_lo_type,
    is_totalizado_primary_type,
    normalize_lo_register,
)
from api.cronjobs.telemetry.controllers.unified_processing import process_variable_safely


class ModbusCombineUnitTests(TestCase):
    """Unit tests puros de la aritmética Modbus (sin BD)."""

    def test_combine_raw_basic(self):
        self.assertEqual(combine_raw(0, 100), 100)
        self.assertEqual(combine_raw(1, 0), MODBUS_UINT16_MODULUS)
        self.assertEqual(combine_raw(2, 500), 2 * MODBUS_UINT16_MODULUS + 500)

    def test_normalize_lo_uint16_range(self):
        lo, extra = normalize_lo_register(65535)
        self.assertEqual(lo, 65535)
        self.assertEqual(extra, 0)

    def test_normalize_lo_inclusive_65536(self):
        """Algunos equipos cuentan hasta 65536 inclusive antes de wrap."""
        lo, extra = normalize_lo_register(65536)
        self.assertEqual(lo, 0)
        self.assertEqual(extra, 1)
        self.assertEqual(combine_raw(5, 65536), 6 * MODBUS_UINT16_MODULUS)

    def test_normal_progress(self):
        prev = 2 * MODBUS_UINT16_MODULUS + 65000
        combined, status = combine_modbus_registers(2, 65020, prev_combined=prev)
        self.assertEqual(status, "OK")
        self.assertEqual(combined, prev + 20)

    def test_synced_rollover(self):
        """HI y LO llegan coherentes tras el wrap."""
        prev = 2 * MODBUS_UINT16_MODULUS + 65500
        combined, status = combine_modbus_registers(3, 10, prev_combined=prev)
        self.assertEqual(status, "OK")
        self.assertEqual(combined, 3 * MODBUS_UINT16_MODULUS + 10)
        self.assertGreater(combined, prev)
        self.assertLess(combined - prev, MODBUS_UINT16_MODULUS)

    def test_mid_rollover_lo_ahead(self):
        """LO ya wrapeó a 10, HI todavía en 2 → no debe producir caída."""
        prev = 2 * MODBUS_UINT16_MODULUS + 65500
        combined, status = combine_modbus_registers(2, 10, prev_combined=prev)
        self.assertEqual(status, "MID_ROLLOVER_LO_AHEAD")
        self.assertEqual(combined, 3 * MODBUS_UINT16_MODULUS + 10)
        self.assertGreaterEqual(combined, prev)
        self.assertLessEqual(combined - prev, MODBUS_UINT16_MODULUS)

    def test_mid_rollover_hi_ahead(self):
        """HI ya subió a 3, LO todavía alto → no debe producir spike de ~65536."""
        prev = 2 * MODBUS_UINT16_MODULUS + 65500
        combined, status = combine_modbus_registers(3, 65500, prev_combined=prev)
        self.assertEqual(status, "MID_ROLLOVER_HI_AHEAD")
        self.assertEqual(combined, prev)  # sin progreso real aún
        self.assertLess(combined - prev, 100)

    def test_mid_rollover_hi_ahead_with_lo_creep(self):
        """HI ahead pero LO avanzó un poco antes del wrap → corregir sin spike."""
        prev = 2 * MODBUS_UINT16_MODULUS + 65500
        combined, status = combine_modbus_registers(3, 65510, prev_combined=prev)
        self.assertEqual(status, "MID_ROLLOVER_HI_AHEAD")
        self.assertEqual(combined, prev + 10)

    def test_unexplained_negative_held(self):
        prev = 5 * MODBUS_UINT16_MODULUS + 1000
        # Caída grande que no cabe en un solo modulus → hold
        combined, status = combine_modbus_registers(1, 0, prev_combined=prev)
        self.assertEqual(status, "HELD_NEGATIVE")
        self.assertEqual(combined, prev)

    def test_huge_spike_held(self):
        prev = 100
        combined, status = combine_modbus_registers(10, 0, prev_combined=prev)
        self.assertEqual(status, "HELD_SPIKE")
        self.assertEqual(combined, prev)

    def test_first_reading_no_prev(self):
        combined, status = combine_modbus_registers(4, 123, prev_combined=None)
        self.assertEqual(status, "OK")
        self.assertEqual(combined, 4 * MODBUS_UINT16_MODULUS + 123)

    def test_type_helpers(self):
        self.assertTrue(is_modbus_lo_type("TOTALIZADO_MODBUS_LO"))
        self.assertTrue(is_modbus_lo_type("totalizado_modbus"))
        self.assertTrue(is_modbus_hi_type("TOTALIZADO_MODBUS_HI"))
        self.assertTrue(is_totalizado_primary_type("TOTALIZADO"))
        self.assertTrue(is_totalizado_primary_type("TOTALIZADO_MODBUS_LO"))
        self.assertFalse(is_totalizado_primary_type("TOTALIZADO_MODBUS_HI"))
        self.assertFalse(is_modbus_lo_type("CAUDAL"))


class ModbusProcessIntegrationTests(TestCase):
    """Integración: process_variable_safely con el par HI/LO."""

    def setUp(self):
        self.user = User.objects.create(username="modbus_user", email="m@example.com")
        self.client_obj = Client.objects.create(name="Modbus Client")
        self.project = ProjectCatchments.objects.create(
            name="Modbus Project", client=self.client_obj
        )
        self.point = CatchmentPoint.objects.create(
            title="IANSA Chillan P2 test", owner_user=self.user, project=self.project
        )
        self.profile = ProfileDataConfigCatchment.objects.get(point_catchment=self.point)
        self.profile.is_telemetry = True
        self.profile.max_diff_m3_per_hour = 5000
        self.profile.save()
        self.point_dict = {
            "id": self.point.id,
            "profile_data_config": {
                "addition": 0,
                "max_diff_m3_per_hour": 5000,
                "reconnection_threshold_hours": 2,
            },
        }
        self.hi_var = {
            "id": 1,
            "type_variable": "TOTALIZADO_MODBUS_HI",
            "str_variable": "5002",
            "pulses_factor": 1000,
        }
        self.lo_var = {
            "id": 2,
            "type_variable": "TOTALIZADO_MODBUS_LO",
            "str_variable": "5001",
            "pulses_factor": 1000,  # como punto 152: factor 1000 → m³ = combined
        }

    def _run_pair(self, hi, lo, medition, created_register=None, order=("hi", "lo")):
        created_register = created_register or {"date_time_medition": medition}
        dt_last = None
        steps = {
            "hi": (self.hi_var, {"value": hi, "date_time": medition}),
            "lo": (self.lo_var, {"value": lo, "date_time": medition}),
        }
        for key in order:
            var, data = steps[key]
            dt_last, created_register = process_variable_safely(
                variable=var,
                data=data,
                point_catchment=self.point_dict,
                created_register=created_register,
                date_time_last_logger_total=dt_last,
                medition_str=medition,
            )
        return created_register

    def test_pair_writes_pulses_and_total(self):
        medition = "2026-03-01T10:00:00"
        reg = self._run_pair(hi=2, lo=1000, medition=medition)
        expected_pulses = 2 * MODBUS_UINT16_MODULUS + 1000
        self.assertEqual(reg["pulses"], expected_pulses)
        self.assertEqual(int(reg["total"]), expected_pulses)  # factor 1000
        self.assertEqual(reg["_modbus_combine_status"], "OK")

    def test_consumption_diff_after_progress(self):
        t0 = timezone.now().replace(minute=0, second=0, microsecond=0)
        prev_pulses = 2 * MODBUS_UINT16_MODULUS + 1000
        InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=t0 - timedelta(hours=1),
            total=str(prev_pulses),
            pulses=prev_pulses,
            total_diff=0,
            flow=0.0,
        )
        medition = (t0).strftime("%Y-%m-%dT%H:00:00")
        # +50 en LO
        reg = self._run_pair(hi=2, lo=1050, medition=medition)
        self.assertEqual(reg["pulses"], prev_pulses + 50)
        self.assertEqual(reg["total_diff"], 50)

    def test_rollover_edge_lo_ahead_no_negative_diff(self):
        t0 = timezone.now().replace(minute=0, second=0, microsecond=0)
        prev_pulses = 2 * MODBUS_UINT16_MODULUS + 65500
        InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=t0 - timedelta(hours=1),
            total=str(prev_pulses),
            pulses=prev_pulses,
            total_diff=0,
            flow=0.0,
        )
        medition = t0.strftime("%Y-%m-%dT%H:00:00")
        # LO wrapeó, HI aún no
        reg = self._run_pair(hi=2, lo=20, medition=medition)
        self.assertEqual(reg["_modbus_combine_status"], "MID_ROLLOVER_LO_AHEAD")
        self.assertGreaterEqual(reg["pulses"], prev_pulses)
        self.assertGreaterEqual(reg["total_diff"], 0)
        self.assertLess(reg["total_diff"], MODBUS_UINT16_MODULUS)

    def test_rollover_edge_hi_ahead_no_spike(self):
        t0 = timezone.now().replace(minute=0, second=0, microsecond=0)
        prev_pulses = 2 * MODBUS_UINT16_MODULUS + 65500
        InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=t0 - timedelta(hours=1),
            total=str(prev_pulses),
            pulses=prev_pulses,
            total_diff=0,
            flow=0.0,
        )
        medition = t0.strftime("%Y-%m-%dT%H:00:00")
        reg = self._run_pair(hi=3, lo=65500, medition=medition)
        self.assertEqual(reg["_modbus_combine_status"], "MID_ROLLOVER_HI_AHEAD")
        self.assertEqual(reg["pulses"], prev_pulses)
        self.assertEqual(reg["total_diff"], 0)

    def test_order_lo_then_hi_still_combines(self):
        medition = "2026-03-01T11:00:00"
        reg = self._run_pair(hi=1, lo=50, medition=medition, order=("lo", "hi"))
        self.assertEqual(reg["pulses"], MODBUS_UINT16_MODULUS + 50)

    def test_alias_totalizado_modbus_as_lo(self):
        medition = "2026-03-01T12:00:00"
        created = {"date_time_medition": medition}
        alias_lo = {
            "id": 3,
            "type_variable": "TOTALIZADO_MODBUS",
            "str_variable": "5001",
            "pulses_factor": 1000,
        }
        _, created = process_variable_safely(
            variable=self.hi_var,
            data={"value": 0, "date_time": medition},
            point_catchment=self.point_dict,
            created_register=created,
            medition_str=medition,
        )
        _, created = process_variable_safely(
            variable=alias_lo,
            data={"value": 77, "date_time": medition},
            point_catchment=self.point_dict,
            created_register=created,
            medition_str=medition,
        )
        self.assertEqual(created["pulses"], 77)

    def test_missing_hi_does_not_write_total(self):
        medition = "2026-03-01T13:00:00"
        created = {"date_time_medition": medition}
        _, created = process_variable_safely(
            variable=self.lo_var,
            data={"value": 100, "date_time": medition},
            point_catchment=self.point_dict,
            created_register=created,
            medition_str=medition,
        )
        self.assertNotIn("total", created)
        self.assertNotIn("pulses", created)
        self.assertEqual(created.get("_modbus_lo"), 100)
