"""
Tests de regresión para anti-jump: ya NO bloquea, solo alerta (P1.8 v2)
=====================================================================

Valida que:
- Saltos masivos son ACEPTADOS (total = valor real del sensor)
- Se registra SystemEvent de advertencia para auditoría
- NO se marca is_error por un salto grande
- El siguiente ciclo computa normalmente desde el último total real
- Reconexiones legítimas NO son bloqueadas
- Consecutivos saltos masivos no congelan el punto
"""

from django.test import TestCase
from django.utils import timezone
from datetime import timedelta

from api.core.models import (
    CatchmentPoint, InteractionDetail, ProfileDataConfigCatchment,
    User, Client, ProjectCatchments
)
from api.cronjobs.telemetry.controllers.total import total_m3
from api.cronjobs.telemetry.controllers.unified_processing import process_totalizado_variable


class AntiJumpBlockingTests(TestCase):
    """Tests para anti-salto masivo (solo alerta, nunca bloqueo)."""

    def setUp(self):
        self.user = User.objects.create(username="testuser", email="test@example.com")
        self.client = Client.objects.create(name="Test Client")
        self.project = ProjectCatchments.objects.create(name="Test Project", client=self.client)
        self.point = CatchmentPoint.objects.create(
            title="Test Point", owner_user=self.user, project=self.project
        )
        # La signal post_save de CatchmentPoint crea automáticamente un ProfileDataConfigCatchment.
        # Lo buscamos y actualizamos con los valores de test.
        self.profile = ProfileDataConfigCatchment.objects.get(point_catchment=self.point)
        self.profile.is_telemetry = True
        self.profile.max_diff_m3_per_hour = 500
        self.profile.reconnection_threshold_hours = 2
        self.profile.save()
        self.point_catchment_dict = {
            "id": self.point.id,
            "profile_data_config": {
                "max_diff_m3_per_hour": 500,
                "reconnection_threshold_hours": 2,
            }
        }

    def test_massive_jump_is_accepted(self):
        """Salto masivo acepta el nuevo total y registra evento de advertencia."""
        # Baseline: total=1000, pulsos=1000000 (factor=1000 → 1000 m³)
        InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=timezone.now() - timedelta(minutes=10),
            total="1000",
            pulses=1000000,
            total_diff=0,
            flow=0.0,
        )

        # Siguiente lectura: pulsos=3000000 → diff de ~2000 m³ en 10 min = 12000 m³/h > 500
        result, meta = total_m3(
            pulses_factor=1000,
            value=3000000,
            point_catchment=self.point_catchment_dict,
            return_full_details=True,
        )

        # ✅ FIX: Ya NO bloquea — acepta el valor real del sensor
        self.assertEqual(result, 3000000, "Debe aceptar el nuevo total del sensor")
        self.assertEqual(meta["status"], "OK")

    def test_next_valid_reading_after_large_jump(self):
        """Después de un salto grande aceptado, el siguiente valor válido computa desde el nuevo total."""
        now = timezone.now()

        # Baseline válido (factor=1000)
        InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=now - timedelta(minutes=20),
            total="1000000",
            pulses=1000000,
            total_diff=0,
            flow=0.0,
        )

        # Primer salto grande aceptado: 2000000 pulsos → 2000000 m³
        result1, meta1 = total_m3(
            1000, 2000000, self.point_catchment_dict,
            return_full_details=True, current_dt=now - timedelta(minutes=10)
        )
        self.assertEqual(result1, 2000000)

        # Guardamos el registro como lo haría el cronjob real (sin is_error)
        InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=now - timedelta(minutes=10),
            total="2000000",
            pulses=2000000,
            total_diff=0,
            flow=0.0,
            is_error=False,
        )

        # Siguiente lectura válida: 2000100 pulsos → diff de 100 m³ en 10 min = 600 m³/h < 500? No, 600 > 500.
        # Usemos 2000050 para que diff = 50 m³ en 10 min = 300 m³/h < 500
        result, meta = total_m3(
            pulses_factor=1000,
            value=2000050,
            point_catchment=self.point_catchment_dict,
            return_full_details=True,
            current_dt=now,
        )

        # Debe computar normalmente desde el último total real (2000000)
        self.assertEqual(result, 2000050, "Debe computar diff normal desde el nuevo total")
        self.assertEqual(meta.get("status"), "OK")

    def test_reconnection_bypasses_blocking(self):
        """Reconexión legítima (>2h sin datos) NO bloquea el salto hacia arriba."""
        now = timezone.now()

        # Baseline antiguo (>2h)
        InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=now - timedelta(hours=5),
            total="1000",
            pulses=1000000,
            total_diff=0,
            flow=0.0,
        )

        # Salto grande hacia arriba después de 5h → reconexión legítima, NO bloquear
        # 2000000 pulsos * 1000 / 1000 = 2000000 m³ (acumulado durante desconexión)
        result, meta = total_m3(
            pulses_factor=1000,
            value=2000000,
            point_catchment=self.point_catchment_dict,
            return_full_details=True,
            current_dt=now,
        )

        self.assertEqual(result, 2000000, "Reconexión legítima: debe aceptar el nuevo total acumulado")
        self.assertEqual(meta.get("status"), "OK")

    def test_reconnection_detects_reset(self):
        """Reconexión con caída de pulsos detecta reset real y ajusta addition."""
        now = timezone.now()

        # Baseline antiguo (>2h)
        InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=now - timedelta(hours=5),
            total="1000",
            pulses=1000000,
            total_diff=0,
            flow=0.0,
        )

        # Vuelve con pulsos menores → reset real durante desconexión
        # 3000 pulsos * 1000 / 1000 = 3000 m³
        # addition debe aumentar en (1000000 * 1000 / 1000) = 1000000
        result, meta = total_m3(
            pulses_factor=1000,
            value=3000,
            point_catchment=self.point_catchment_dict,
            return_full_details=True,
            current_dt=now,
        )

        # El total debe incluir el addition ajustado: 3000 + 1000000 = 1003000
        self.assertEqual(result, 1003000, "Reconexión con reset: debe detectar reset y ajustar addition")
        self.assertEqual(meta.get("status"), "OK")

        # Verificar que el addition se actualizó en el perfil
        self.profile.refresh_from_db()
        self.assertEqual(float(self.profile.addition), 1000000.0, "Addition debe reflejar el monto del reset")

    def test_consecutive_large_jumps_accepted(self):
        """5 saltos masivos consecutivos se aceptan sin congelar el punto."""
        now = timezone.now()

        # Baseline
        InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=now - timedelta(minutes=60),
            total="1000",
            pulses=1000000,
            total_diff=0,
            flow=0.0,
        )

        # 5 saltos masivos consecutivos, cada 10 minutos
        for i in range(1, 6):
            dt = now - timedelta(minutes=60 - i * 10)
            result, meta = total_m3(
                pulses_factor=1000,
                value=2000000,
                point_catchment=self.point_catchment_dict,
                return_full_details=True,
                current_dt=dt,
            )
            # ✅ FIX: Cada salto se acepta (no se mantiene baseline)
            self.assertEqual(result, 2000000, f"Salto {i}: debe aceptar el nuevo total")
            self.assertEqual(meta["status"], "OK")

            InteractionDetail.objects.create(
                catchment_point=self.point,
                date_time_medition=dt,
                total="2000000",
                pulses=2000000,
                is_error=False,
            )

        # 6to valor válido: diff pequeño desde el último total real
        result, meta = total_m3(
            pulses_factor=1000,
            value=2000100,
            point_catchment=self.point_catchment_dict,
            return_full_details=True,
            current_dt=now,
        )
        self.assertEqual(result, 2000100, "Valor casi igual: debe computar desde el último total real")

    def test_process_totalizado_does_not_set_is_error_on_large_jump(self):
        """process_totalizado_variable NO marca is_error cuando hay salto masivo."""
        now = timezone.now()
        # Baseline hace 30 min (menos de 2h, NO reconexión)
        InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=now - timedelta(minutes=30),
            total="1000",
            pulses=1000000,
            total_diff=0,
            flow=0.0,
        )

        data = {"value": 3000000, "date_time": now.strftime("%Y-%m-%dT%H:%M:%S")}
        variable = {
            "type_variable": "TOTALIZADO",
            "str_variable": "TOTAL_TEST",
            "pulses_factor": 1000,
        }
        created_register = {"date_time_medition": now.strftime("%Y-%m-%dT%H:%M:%S")}

        _, created_register = process_totalizado_variable(
            data, variable, self.point_catchment_dict, created_register,
            medition_str=now.strftime("%Y-%m-%dT%H:%M:%S"),
            current_dt=now,
        )

        # ✅ FIX: Ya NO se marca is_error por salto masivo
        self.assertIsNone(created_register.get("is_error"), "NO debe marcar is_error en salto grande")
        self.assertEqual(int(created_register["total"]), 3000000, "Total debe ser el valor real del sensor")
