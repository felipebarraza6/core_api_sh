"""
Tests de regresión: totalizador en cero debe mantener el último total válido
============================================================================

Valida el fix 2026-10 de controllers/total.py.

Causa raíz: la rama ZERO_KEPT exigía "current_pulses == 0 and last_pulses > 0".
Cuando el totalizador lleva 2+ horas en cero, last_pulses ya es 0, la rama no
se activaba y el cálculo final devolvía total = 0 + offset, colapsando el
acumulado al offset.

Impacto real: el punto 110 (P3 Iansa Chillán) perdió 39 790 m³ visibles el
2026-09-16 20:00 (1 199 738 -> 1 159 948) porque su totalizador dejó de enviar
pulsos y a la segunda hora el total cayó al offset.

Límite conocido (NO cubierto aquí, fuera de alcance de este fix):
al reconectar tras una racha de ceros, el offset no incorpora los pulsos
abandonados de la última lectura válida, así que total = pulsos_nuevos +
offset subconta esa diferencia. En el punto 110 se cerró con la reparación
de datos (addition = total retenido = 728 953). Corregirlo en general
exigiría tocar el offset en la transición a cero, lo que chocaría con la
decisión explícita de tratar pulses=0 como error de ingesta y no como reset.
"""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from api.core.models import (
    CatchmentPoint, Client, InteractionDetail, ProfileDataConfigCatchment,
    ProjectCatchments, User,
)
from api.cronjobs.telemetry.controllers.total import total_m3


class ZeroKeptConsecutiveZerosTests(TestCase):
    """Un totalizador muerto debe retener el total durante TODAS las horas en cero."""

    OFFSET = 50000
    TOTAL_BASE = 51000

    def setUp(self):
        user = User.objects.create(username="zero_user", email="zero@example.com")
        client = Client.objects.create(name="Zero Client")
        project = ProjectCatchments.objects.create(name="Zero Project", client=client)
        self.point = CatchmentPoint.objects.create(
            title="Zero Point", owner_user=user, project=project
        )
        # La signal post_save crea el ProfileDataConfigCatchment automáticamente.
        self.profile = ProfileDataConfigCatchment.objects.get(point_catchment=self.point)
        self.profile.is_telemetry = True
        self.profile.addition = self.OFFSET
        self.profile.save()
        self.pc = {"id": self.point.id, "profile_data_config": {}}

    def _last(self, minutes, pulses, total):
        InteractionDetail.objects.create(
            catchment_point=self.point,
            date_time_medition=timezone.now() - timedelta(minutes=minutes),
            total=str(total),
            pulses=pulses,
            total_diff=0,
            flow=0.0,
        )

    def _total(self, value):
        result, meta = total_m3(
            pulses_factor=1000,
            value=value,
            point_catchment=self.pc,
            return_full_details=True,
        )
        return result, meta.get("status")

    def test_first_zero_keeps_last_total(self):
        """Transición a cero: mantiene el último total, no cae al offset."""
        self._last(60, 1000, self.TOTAL_BASE)
        result, status = self._total(0)
        self.assertEqual(status, "ZERO_KEPT")
        self.assertEqual(result, self.TOTAL_BASE)

    def test_second_consecutive_zero_keeps_last_total(self):
        """BUG FIX: la segunda hora en cero también debe retener el total.

        Antes del fix esta rama exigía last_pulses > 0, no se activaba, y el
        cálculo final devolvía total = 0 + offset (50000), perdiendo 1000 m³.
        """
        self._last(120, 1000, self.TOTAL_BASE)
        # Primera hora en cero (queda registrada con pulses=0, total retenido)
        self._last(60, 0, self.TOTAL_BASE)

        result, status = self._total(0)
        self.assertEqual(status, "ZERO_KEPT")
        self.assertEqual(
            result, self.TOTAL_BASE,
            "La segunda hora en cero colapsó el total al offset "
            f"({self.OFFSET}) en vez de retener {self.TOTAL_BASE}",
        )

    def test_many_consecutive_zeros_never_collapse(self):
        """N horas seguidas en cero: el total nunca cae al offset."""
        self._last(700, 1000, self.TOTAL_BASE)
        for i in range(6, 1, -1):
            self._last(i * 60, 0, self.TOTAL_BASE)

        result, status = self._total(0)
        self.assertEqual(status, "ZERO_KEPT")
        self.assertEqual(result, self.TOTAL_BASE)
