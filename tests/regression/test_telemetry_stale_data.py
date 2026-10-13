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

    def _details(self, provider_dt):
        return [{
            "str_variable": "nivel",
            "type_variable": "NIVEL",
            "value": 10.0,
            "success": True,
            "provider_datetime": provider_dt,
        }]

    def _fresh_utc(self, hours=0.0):
        return (timezone.now() - timedelta(hours=hours)).astimezone(timezone.utc)

    def test_fresh_data_is_not_marked(self):
        register = {}
        _mark_stale_data(
            self.point.id, [self._fresh_utc()], self._details("x"), register
        )
        self.assertFalse(register["variable_details"][0]["stale"])
        self.assertEqual(
            SystemEvent.objects.filter(point_catchment_id=self.point.id).count(), 0
        )

    def test_old_data_is_marked_and_emits_event(self):
        register = {}
        _mark_stale_data(
            self.point.id,
            [self._fresh_utc(hours=STALE_THRESHOLD_HOURS + 5)],
            self._details("x"),
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

        _mark_stale_data(
            self.point.id,
            [self._fresh_utc(hours=99)],
            self._details("x"),
            {},
        )
        evento = SystemEvent.objects.get(point_catchment_id=self.point.id)
        self.assertEqual(
            SupportTicket.objects.filter(system_event=evento).count(), 0
        )

    def test_cooldown_prevents_event_spam(self):
        """El cron corre cada minuto: no puede emitir 1 evento por hora."""
        dt = [self._fresh_utc(hours=99)]
        _mark_stale_data(self.point.id, dt, self._details("x"), {})
        _mark_stale_data(self.point.id, dt, self._details("x"), {})
        _mark_stale_data(self.point.id, dt, self._details("x"), {})
        self.assertEqual(
            SystemEvent.objects.filter(point_catchment_id=self.point.id).count(), 1
        )

    def test_no_provider_datetimes_means_not_stale(self):
        register = {}
        _mark_stale_data(self.point.id, [], self._details(None), register)
        self.assertFalse(register["variable_details"][0]["stale"])
        self.assertEqual(
            SystemEvent.objects.filter(point_catchment_id=self.point.id).count(), 0
        )

    def test_uses_newest_variable(self):
        """Si al menos una variable es fresca, el registro no es obsoleto."""
        register = {}
        _mark_stale_data(
            self.point.id,
            [self._fresh_utc(hours=99), self._fresh_utc(hours=0)],
            self._details("x"),
            register,
        )
        self.assertFalse(register["variable_details"][0]["stale"])

    def test_keeps_provider_datetime_in_details(self):
        register = {}
        _mark_stale_data(
            self.point.id,
            [self._fresh_utc(hours=99)],
            self._details("2026-10-12T10:00:00"),
            register,
        )
        self.assertEqual(
            register["variable_details"][0]["provider_datetime"], "2026-10-12T10:00:00"
        )
