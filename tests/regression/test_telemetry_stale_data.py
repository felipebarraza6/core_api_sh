"""
Detección de dato obsoleto del proveedor (`_mark_stale_data`).

Cubre la normalización de zona horaria entre getters y el marcado de
frescura, que evita que la API muestre como "de hoy" datos de hace días.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from api.core.models import CatchmentPoint, ProjectCatchments, Client, SystemEvent
from api.cronjobs.telemetry.telemetry_unified import (
    STALE_THRESHOLD_HOURS,
    _as_aware_utc,
    _mark_stale_data,
)

User = get_user_model()


class AsAwareUtcTests(TestCase):
    """Los getters NO devuelven la misma zona horaria."""

    def test_tdata_is_server_local_not_utc(self):
        """
        `tdata` usa `datetime.fromtimestamp`, que con TIME_ZONE de Django
        devuelve hora local (America/Santiago). Tratarla como UTC sumaba
        +3 h de antigüedad y marcaba como obsoletos puntos vivos.
        """
        now_local = timezone.localtime().strftime("%Y-%m-%dT%H:%M:%S")
        dt = _as_aware_utc(now_local, "tdata")
        self.assertIsNotNone(dt)
        age_h = (timezone.now() - dt).total_seconds() / 3600.0
        self.assertLess(age_h, 0.1)

    def test_thethings_is_utc(self):
        """`thethings` parsea cadenas con sufijo 'Z' -> UTC naive."""
        now_utc = timezone.now().strftime("%Y-%m-%dT%H:%M:%S")
        dt = _as_aware_utc(now_utc, "thethings")
        self.assertIsNotNone(dt)
        age_h = (timezone.now() - dt).total_seconds() / 3600.0
        self.assertLess(age_h, 0.1)

    def test_tago_is_utc(self):
        now_utc = timezone.now().strftime("%Y-%m-%dT%H:%M:%S")
        self.assertIsNotNone(_as_aware_utc(now_utc, "tago"))

    def test_fresh_tdata_is_not_misread_as_three_hours_old(self):
        """Regresión del falso positivo de 2026-10-13 (~3 h inventadas)."""
        now_local = timezone.localtime().strftime("%Y-%m-%dT%H:%M:%S")
        dt = _as_aware_utc(now_local, "tdata")
        age_h = (timezone.now() - dt).total_seconds() / 3600.0
        self.assertLess(age_h, STALE_THRESHOLD_HOURS)

    def test_invalid_inputs_return_none(self):
        self.assertIsNone(_as_aware_utc(None, "tdata"))
        self.assertIsNone(_as_aware_utc("", "thethings"))
        self.assertIsNone(_as_aware_utc("no-es-fecha", "tdata"))
        self.assertIsNone(_as_aware_utc("2026-10-13T12:00:00.000Z", "tdata"))


class MarkStaleDataTests(TestCase):

    def setUp(self):
        self.client_obj = Client.objects.create(name="Cliente Stale")
        self.project = ProjectCatchments.objects.create(
            name="Proyecto Stale", client=self.client_obj
        )
        self.owner = User.objects.create_user(
            email="stale@smarthydro.cl", password="pass", username="staleowner"
        )
        self.point = CatchmentPoint.objects.create(
            title="Punto Stale", project=self.project, owner_user=self.owner
        )

    def _iso(self, hours=0.0):
        return (timezone.now() - timedelta(hours=hours)).isoformat()

    def _details(self, **por_variable):
        """Detalles con provider_datetime real por variable (nombre -> horas)."""
        return [
            {
                "str_variable": nombre,
                "type_variable": "NIVEL",
                "value": 10.0,
                "success": True,
                "provider_datetime": (
                    None if horas is None else self._iso(horas)
                ),
            }
            for nombre, horas in por_variable.items()
        ]

    def test_fresh_data_is_not_marked(self):
        register = {}
        _mark_stale_data(self.point.id, self._details(nivel=0), register)
        self.assertFalse(register["variable_details"][0]["stale"])
        self.assertEqual(
            SystemEvent.objects.filter(point_catchment_id=self.point.id).count(), 0
        )

    def test_old_data_is_marked_and_emits_event(self):
        register = {}
        _mark_stale_data(
            self.point.id,
            self._details(nivel=STALE_THRESHOLD_HOURS + 5),
            register,
        )
        self.assertTrue(register["variable_details"][0]["stale"])
        evento = SystemEvent.objects.filter(point_catchment_id=self.point.id).first()
        self.assertIsNotNone(evento)
        self.assertEqual(evento.event_type, "API_ERROR")
        self.assertEqual(evento.severity, "WARNING")

    def test_warning_event_does_not_create_a_ticket(self):
        """Los CRITICAL crean ticket automático; un WARNING no debe hacerlo."""
        from api.core.models import SupportTicket

        _mark_stale_data(self.point.id, self._details(nivel=99), {})
        evento = SystemEvent.objects.get(point_catchment_id=self.point.id)
        self.assertEqual(
            SupportTicket.objects.filter(system_event=evento).count(), 0
        )

    def test_cooldown_prevents_event_spam(self):
        """El cron corre cada minuto: no puede emitir 1 evento por hora."""
        for _ in range(3):
            _mark_stale_data(self.point.id, self._details(nivel=99), {})
        self.assertEqual(
            SystemEvent.objects.filter(point_catchment_id=self.point.id).count(), 1
        )

    def test_no_provider_datetime_means_not_stale(self):
        """Sin fecha del proveedor no hay antigüedad que reportar."""
        register = {}
        _mark_stale_data(self.point.id, self._details(nivel=None), register)
        self.assertFalse(register["variable_details"][0]["stale"])
        self.assertEqual(
            SystemEvent.objects.filter(point_catchment_id=self.point.id).count(), 0
        )

    def test_mixed_freshness_marks_only_the_old_variable(self):
        """
        Regresión: antes se usaba max(provider_datetimes), así que un punto con
        `nivel` al día y `caudal` de hace 2 años quedaba entero SIN marcar y la
        API mostraba el dato viejo como recién actualizado.
        """
        register = {}
        _mark_stale_data(
            self.point.id,
            self._details(nivel=0, caudal=STALE_THRESHOLD_HOURS + 5),
            register,
        )
        por_nombre = {d["str_variable"]: d for d in register["variable_details"]}
        self.assertFalse(por_nombre["nivel"]["stale"])
        self.assertNotIn("stale_hours", por_nombre["nivel"])
        self.assertTrue(por_nombre["caudal"]["stale"])
        self.assertIn("stale_hours", por_nombre["caudal"])

    def test_event_lists_only_the_stale_variables(self):
        """El SystemEvent debe nombrar solo las variables afectadas."""
        _mark_stale_data(
            self.point.id,
            self._details(nivel=0, caudal=STALE_THRESHOLD_HOURS + 5),
            {},
        )
        evento = SystemEvent.objects.get(point_catchment_id=self.point.id)
        afectadas = [v["variable"] for v in evento.extra_data["variables"]]
        self.assertEqual(afectadas, ["caudal"])

    def test_keeps_provider_datetime_in_details(self):
        detalles = self._details(nivel=99)
        register = {}
        _mark_stale_data(self.point.id, detalles, register)
        self.assertEqual(
            register["variable_details"][0]["provider_datetime"],
            detalles[0]["provider_datetime"],
        )
