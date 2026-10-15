"""
Tests para totalizador Modbus de dos registros (HI + LO).
=========================================================

Cubre:
- Combinación HI*65536 + LO
- Wrap 65535→0 y LO==65536
- Mid-rollover solo con patrón inequívoco (LO near-top→near-zero / HI ahead)
- Regresión chica de LO → hold (no fake jump)
- Device reset (0,0) → re-baseline via addition
- Migración TOTALIZADO → Modbus (punto 152)
- Huecos largos >65536 con HI/LO coherentes
- Regresión: TOTALIZADO clásico idéntico (factor 1000, addition 830293)
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
    last_record_used_modbus,
    normalize_lo_register,
)
from api.cronjobs.telemetry.controllers.total import total_m3
from api.cronjobs.telemetry.controllers.unified_processing import (
    process_totalizado_variable,
    process_variable_safely,
)

MODBUS_DETAILS = [
    {"str_variable": "5002", "type_variable": "TOTALIZADO_MODBUS_HI", "value": 0, "success": True},
    {"str_variable": "5001", "type_variable": "TOTALIZADO_MODBUS_LO", "value": 0, "success": True},
]


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
        """LO ya wrapeó a 10 (near zero), HI todavía en 2, prev LO near top."""
        prev = 2 * MODBUS_UINT16_MODULUS + 65500
        combined, status = combine_modbus_registers(2, 10, prev_combined=prev)
        self.assertEqual(status, "MID_ROLLOVER_LO_AHEAD")
        self.assertEqual(combined, 3 * MODBUS_UINT16_MODULUS + 10)
        self.assertGreaterEqual(combined, prev)
        self.assertLessEqual(combined - prev, MODBUS_UINT16_MODULUS)

    def test_small_lo_regression_holds_no_fake_jump(self):
        """
        Bug 1: (6,5)->(6,3) no debe aplicar LO-ahead (+65534).
        LO previo no está near-top → hold.
        """
        prev = 6 * MODBUS_UINT16_MODULUS + 5
        combined, status = combine_modbus_registers(6, 3, prev_combined=prev)
        self.assertEqual(status, "HELD_NEGATIVE")
        self.assertEqual(combined, prev)
        self.assertNotEqual(combined, 7 * MODBUS_UINT16_MODULUS + 3)

    def test_mid_rollover_hi_ahead(self):
        """HI ya subió a 3, LO todavía alto → no debe producir spike de ~65536."""
        prev = 2 * MODBUS_UINT16_MODULUS + 65500
        combined, status = combine_modbus_registers(3, 65500, prev_combined=prev)
        self.assertEqual(status, "MID_ROLLOVER_HI_AHEAD")
        self.assertEqual(combined, prev)
        self.assertLess(combined - prev, 100)

    def test_mid_rollover_hi_ahead_with_lo_creep(self):
        """HI ahead pero LO avanzó un poco antes del wrap → corregir sin spike."""
        prev = 2 * MODBUS_UINT16_MODULUS + 65500
        combined, status = combine_modbus_registers(3, 65510, prev_combined=prev)
        self.assertEqual(status, "MID_ROLLOVER_HI_AHEAD")
        self.assertEqual(combined, prev + 10)

    def test_device_reset_zero_zero(self):
        """Bug 2: (0,0) tras acumulado previo → DEVICE_RESET, no hold forever."""
        prev = 5 * MODBUS_UINT16_MODULUS + 1000
        combined, status = combine_modbus_registers(0, 0, prev_combined=prev)
        self.assertEqual(status, "DEVICE_RESET")
        self.assertEqual(combined, 0)

    def test_long_gap_consistent_advance_accepted(self):
        """
        Bug 4: avance 100000 con HI/LO coherentes (hueco largo) → OK,
        sin restar 65536 ni HELD_SPIKE.
        """
        prev = 1 * MODBUS_UINT16_MODULUS + 0  # (1, 0)
        # +100000 → (2, 34464)
        combined, status = combine_modbus_registers(2, 34464, prev_combined=prev)
        self.assertEqual(status, "OK")
        self.assertEqual(combined, prev + 100000)

    def test_unexplained_negative_held(self):
        prev = 5 * MODBUS_UINT16_MODULUS + 1000
        # Caída grande que no es (0,0) ni wrap near-top→near-zero → hold
        combined, status = combine_modbus_registers(1, 0, prev_combined=prev)
        self.assertEqual(status, "HELD_NEGATIVE")
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
        self.assertTrue(last_record_used_modbus(MODBUS_DETAILS))
        self.assertFalse(
            last_record_used_modbus(
                [{"type_variable": "TOTALIZADO", "str_variable": "Acumulado"}]
            )
        )


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
        self.profile.addition = 0
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
            "pulses_factor": 1000,
        }

    def _seed_modbus_history(self, pulses, total=None, hours_ago=1):
        t0 = timezone.now().replace(minute=0, second=0, microsecond=0)
        InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=t0 - timedelta(hours=hours_ago),
            total=str(total if total is not None else pulses),
            pulses=pulses,
            total_diff=0,
            flow=0.0,
            variable_details=MODBUS_DETAILS,
        )
        return t0

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
        self.assertEqual(int(reg["total"]), expected_pulses)
        self.assertEqual(reg["_modbus_combine_status"], "OK")

    def test_consumption_diff_after_progress(self):
        t0 = self._seed_modbus_history(2 * MODBUS_UINT16_MODULUS + 1000)
        medition = t0.strftime("%Y-%m-%dT%H:00:00")
        reg = self._run_pair(hi=2, lo=1050, medition=medition)
        self.assertEqual(reg["pulses"], 2 * MODBUS_UINT16_MODULUS + 1050)
        self.assertEqual(reg["total_diff"], 50)

    def test_rollover_edge_lo_ahead_no_negative_diff(self):
        prev_pulses = 2 * MODBUS_UINT16_MODULUS + 65500
        t0 = self._seed_modbus_history(prev_pulses)
        medition = t0.strftime("%Y-%m-%dT%H:00:00")
        reg = self._run_pair(hi=2, lo=20, medition=medition)
        self.assertEqual(reg["_modbus_combine_status"], "MID_ROLLOVER_LO_AHEAD")
        self.assertGreaterEqual(reg["pulses"], prev_pulses)
        self.assertGreaterEqual(reg["total_diff"], 0)
        self.assertLess(reg["total_diff"], MODBUS_UINT16_MODULUS)

    def test_rollover_edge_hi_ahead_no_spike(self):
        prev_pulses = 2 * MODBUS_UINT16_MODULUS + 65500
        t0 = self._seed_modbus_history(prev_pulses)
        medition = t0.strftime("%Y-%m-%dT%H:00:00")
        reg = self._run_pair(hi=3, lo=65500, medition=medition)
        self.assertEqual(reg["_modbus_combine_status"], "MID_ROLLOVER_HI_AHEAD")
        self.assertEqual(reg["pulses"], prev_pulses)
        self.assertEqual(reg["total_diff"], 0)

    def test_small_lo_regression_integration_no_fake_consumption(self):
        """Bug 1 integración: (6,5)->(6,3) no suma consumo fantasma."""
        prev_pulses = 6 * MODBUS_UINT16_MODULUS + 5
        t0 = self._seed_modbus_history(prev_pulses)
        medition = t0.strftime("%Y-%m-%dT%H:00:00")
        reg = self._run_pair(hi=6, lo=3, medition=medition)
        self.assertEqual(reg["_modbus_combine_status"], "HELD_NEGATIVE")
        self.assertEqual(reg["pulses"], prev_pulses)
        self.assertEqual(reg["total_diff"], 0)

    def test_device_reset_rebaselines_addition(self):
        """Bug 2: (0,0) re-baseline; siguiente lectura no queda congelada."""
        prev_pulses = 5 * MODBUS_UINT16_MODULUS + 1000
        t0 = self._seed_modbus_history(prev_pulses, total=prev_pulses)
        medition = t0.strftime("%Y-%m-%dT%H:00:00")
        reg = self._run_pair(hi=0, lo=0, medition=medition)
        self.assertEqual(reg["_modbus_combine_status"], "DEVICE_RESET")
        self.assertEqual(reg["pulses"], 0)
        # Continuidad de total vía addition
        self.assertEqual(int(reg["total"]), prev_pulses)
        self.profile.refresh_from_db()
        self.assertEqual(float(self.profile.addition), float(prev_pulses))

        # Persistir el reset y avanzar
        InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=t0,
            total=str(reg["total"]),
            pulses=0,
            total_diff=reg["total_diff"],
            flow=0.0,
            variable_details=MODBUS_DETAILS,
        )
        self.point_dict["profile_data_config"]["addition"] = float(self.profile.addition)

        t1 = t0 + timedelta(hours=1)
        reg2 = self._run_pair(
            hi=0,
            lo=50,
            medition=t1.strftime("%Y-%m-%dT%H:00:00"),
            created_register={"date_time_medition": t1.strftime("%Y-%m-%dT%H:00:00")},
        )
        self.assertEqual(reg2["pulses"], 50)
        self.assertEqual(int(reg2["total"]), prev_pulses + 50)

    def test_type_migration_from_totalizado_no_freeze(self):
        """
        Bug 3: punto 152-like — pulses previos de TOTALIZADO (316217)
        no congelan la primera lectura Modbus (0, 1200).
        """
        old_pulses = 316217
        old_addition = 0
        t0 = timezone.now().replace(minute=0, second=0, microsecond=0)
        InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=t0 - timedelta(hours=1),
            total=str(old_pulses),
            pulses=old_pulses,
            total_diff=0,
            flow=0.0,
            # TOTALIZADO clásico — sin tipos Modbus
            variable_details=[
                {
                    "str_variable": "Acumulado",
                    "type_variable": "TOTALIZADO",
                    "value": old_pulses,
                    "success": True,
                }
            ],
        )
        medition = t0.strftime("%Y-%m-%dT%H:00:00")
        reg = self._run_pair(hi=0, lo=1200, medition=medition)
        self.assertEqual(reg["_modbus_combine_status"], "TYPE_MIGRATION")
        self.assertEqual(reg["pulses"], 1200)
        # total continuo: old_pulses ≈ new_total (absorb delta en addition)
        self.assertEqual(int(reg["total"]), old_pulses)
        self.profile.refresh_from_db()
        expected_addition = old_addition + (old_pulses - 1200)
        self.assertEqual(float(self.profile.addition), float(expected_addition))

    def test_long_gap_integration_no_subtract(self):
        """Bug 4 integración: +100000 coherente no se recorta en 65536."""
        prev = MODBUS_UINT16_MODULUS  # (1, 0)
        t0 = self._seed_modbus_history(prev, hours_ago=48)
        medition = t0.strftime("%Y-%m-%dT%H:00:00")
        reg = self._run_pair(hi=2, lo=34464, medition=medition)
        self.assertEqual(reg["_modbus_combine_status"], "OK")
        self.assertEqual(reg["pulses"], prev + 100000)
        self.assertEqual(reg["total_diff"], 100000)

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


class TotalizadoRegressionPoint152ConfigTests(TestCase):
    """
    Regresión: TOTALIZADO clásico (config tipo punto 152) no debe cambiar
    con el código Modbus. pulses_factor=1000, addition=830293.
    """

    def setUp(self):
        self.user = User.objects.create(username="tot_reg", email="t@example.com")
        self.client_obj = Client.objects.create(name="IANSA")
        self.project = ProjectCatchments.objects.create(
            name="Chillan", client=self.client_obj
        )
        self.point = CatchmentPoint.objects.create(
            title="IANSA Chillan P2", owner_user=self.user, project=self.project
        )
        self.profile = ProfileDataConfigCatchment.objects.get(point_catchment=self.point)
        self.profile.is_telemetry = True
        self.profile.addition = 830293
        self.profile.max_diff_m3_per_hour = 5000
        self.profile.save()
        self.point_dict = {
            "id": self.point.id,
            "profile_data_config": {
                "addition": 830293,
                "max_diff_m3_per_hour": 5000,
                "reconnection_threshold_hours": 2,
            },
        }
        self.variable = {
            "type_variable": "TOTALIZADO",
            "str_variable": "Acumulado",
            "pulses_factor": 1000,
        }

    def test_total_m3_formula_with_addition_830293(self):
        """total = (pulses * 1000)/1000 + 830293 — idéntico a main."""
        pulses = 316217
        result = total_m3(
            pulses_factor=1000,
            value=pulses,
            point_catchment=self.point_dict,
        )
        self.assertEqual(result, pulses + 830293)

    def test_process_totalizado_matches_main_formula(self):
        """process_totalizado_variable con config 152 produce total esperado."""
        pulses = 316217
        # Baseline previo monotónico para no disparar reset
        InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=timezone.now() - timedelta(hours=1),
            total=str(316200 + 830293),
            pulses=316200,
            total_diff=0,
            flow=0.0,
            variable_details=[
                {
                    "str_variable": "Acumulado",
                    "type_variable": "TOTALIZADO",
                    "value": 316200,
                    "success": True,
                }
            ],
        )
        medition = timezone.now().replace(minute=0, second=0, microsecond=0)
        medition_str = medition.strftime("%Y-%m-%dT%H:00:00")
        _, reg = process_totalizado_variable(
            data={"value": pulses, "date_time": medition_str},
            variable=self.variable,
            point_catchment=self.point_dict,
            created_register={"date_time_medition": medition_str},
            medition_str=medition_str,
        )
        self.assertEqual(reg["pulses"], pulses)
        self.assertEqual(int(reg["total"]), pulses + 830293)
        self.assertEqual(reg["total_diff"], 17)  # 316217 - 316200
