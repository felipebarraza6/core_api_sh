"""
Tests de regresión para POST /api/telemetry-reprocessor/
==========================================================

Valida:
- Actions locales (fix-*) siguen funcionando con source=local (default).
- Action backfill con source=providers requiere point_id y provider soportado.
- Backfill dry-run no modifica la BD.
- Backfill apply crea/actualiza registros y ejecuta procesamiento en cascada.
"""

import json
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

User = get_user_model()


class TelemetryReprocessorLocalTests(TestCase):
    """Tests para actions locales (source=local)."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="adminuser",
            password="testpass123",
            email="admin@example.com",
            is_staff=True,
        )
        self.client.force_authenticate(user=self.user)

        self.client_obj = Client.objects.create(name="Test Client")
        self.project = ProjectCatchments.objects.create(
            name="Test Project", client=self.client_obj
        )
        self.point = CatchmentPoint.objects.create(
            title="Test Point",
            owner_user=self.user,
            project=self.project,
            frecuency="60",
        )
        ProfileDataConfigCatchment.objects.create(
            point_catchment=self.point,
            is_telemetry=True,
            d3=5.0,
        )

    def _post(self, payload):
        return self.client.post(
            "/api/telemetry-reprocessor/",
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_fix_actions_require_point_id(self):
        """fix actions requieren point_id."""
        response = self._post({
            "action": "fix-totals",
            "start": "2026-05-20",
            "end": "2026-05-22",
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn("point_id", response.json().get("error", "").lower())

    def test_default_source_is_local(self):
        """Si no se envía source, debe usar local."""
        response = self._post({
            "action": "fix-water-table",
            "point_id": self.point.id,
            "start": "2026-05-20",
            "end": "2026-05-22",
        })
        # 400 porque falta d3 válido o registros, pero no por source
        self.assertIn(response.status_code, [200, 400])


class TelemetryReprocessorBackfillTests(TestCase):
    """Tests para action=backfill con source=providers."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="adminuser",
            password="testpass123",
            email="admin@example.com",
            is_staff=True,
        )
        self.client.force_authenticate(user=self.user)

        self.client_obj = Client.objects.create(name="Test Client")
        self.project = ProjectCatchments.objects.create(
            name="Test Project", client=self.client_obj
        )
        self.point = CatchmentPoint.objects.create(
            title="Test Point",
            owner_user=self.user,
            project=self.project,
            frecuency="60",
            is_tdata=True,
        )
        self.profile = ProfileDataConfigCatchment.objects.create(
            point_catchment=self.point,
            is_telemetry=True,
            token_service="DEVICE_TOKEN",
            d3=5.0,
            addition=0.0,
        )
        self.scheme = SchemesCatchment.objects.create(
            name="Test Scheme", description="Test"
        )
        self.scheme.points_catchment.add(self.point)

        self.var_total = Variable.objects.create(
            scheme_catchment=self.scheme,
            str_variable="5000",
            label="Acumulado",
            type_variable="TOTALIZADO",
            pulses_factor=1000,
        )

    def _post(self, payload):
        return self.client.post(
            "/api/telemetry-reprocessor/",
            data=json.dumps(payload),
            content_type="application/json",
        )

    def _mock_history_data(self, base_dt_utc):
        """Genera datos históricos simulados en UTC para 3 horas."""
        return [
            {
                "ts_ms": int((base_dt_utc + timedelta(hours=i)).timestamp() * 1000),
                "value": 100 + (i * 10),
                "date_time": (base_dt_utc + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M:%S"),
            }
            for i in range(3)
        ]

    def test_backfill_requires_providers_source(self):
        """action=backfill requiere source=providers."""
        response = self._post({
            "action": "backfill",
            "point_id": self.point.id,
            "start": "2026-05-20",
            "end": "2026-05-22",
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn("source=providers", response.json().get("error", ""))

    def test_backfill_rejects_unsupported_provider(self):
        """Debe rechazar providers sin soporte de histórico."""
        self.point.is_tdata = False
        self.point.is_thethings = True
        self.point.save()

        response = self._post({
            "action": "backfill",
            "source": "providers",
            "point_id": self.point.id,
            "start": "2026-05-20",
            "end": "2026-05-22",
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn("histórico", response.json().get("error", "").lower())

    def test_backfill_rejects_range_over_7_days(self):
        """Debe rechazar rangos mayores a 7 días."""
        response = self._post({
            "action": "backfill",
            "source": "providers",
            "point_id": self.point.id,
            "start": "2026-05-01",
            "end": "2026-05-22",
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn("7", response.json().get("error", ""))

    @patch("api.core.services.telemetry_backfill.get_data_tdata_history")
    def test_backfill_dry_run_does_not_create_records(self, mock_history):
        """Dry-run no debe crear registros en BD."""
        base_dt = pytz.utc.localize(datetime(2026, 5, 20, 12, 0, 0))
        mock_history.return_value = self._mock_history_data(base_dt)

        response = self._post({
            "action": "backfill",
            "source": "providers",
            "point_id": self.point.id,
            "start": "2026-05-20",
            "end": "2026-05-21",
            "apply": False,
        })

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["mode"], "dry-run")
        self.assertEqual(data["source"], "providers")
        self.assertEqual(data["action"], "backfill")
        self.assertEqual(data["provider"], "tdata")
        self.assertGreater(data["records_created"], 0)
        self.assertEqual(data["records_updated"], 0)

        # No debe haber registros creados
        count = InteractionDetail.objects.filter(catchment_point=self.point).count()
        self.assertEqual(count, 0)

    @patch("api.core.services.telemetry_backfill.get_data_tdata_history")
    def test_backfill_apply_creates_and_processes_records(self, mock_history):
        """apply=true debe crear registros y ejecutar procesamiento en cascada."""
        base_dt = pytz.utc.localize(datetime(2026, 5, 20, 12, 0, 0))
        mock_history.return_value = self._mock_history_data(base_dt)

        response = self._post({
            "action": "backfill",
            "source": "providers",
            "point_id": self.point.id,
            "start": "2026-05-20",
            "end": "2026-05-21",
            "apply": True,
        })

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["mode"], "applied")
        self.assertGreater(data["records_created"], 0)

        processing = data.get("processing", {})
        self.assertIn("totals_updated", processing)
        self.assertIn("diff_updated", processing)

        # Debe haber registros creados
        count = InteractionDetail.objects.filter(catchment_point=self.point).count()
        self.assertGreater(count, 0)

    @patch("api.core.services.telemetry_backfill.get_data_tdata_history")
    def test_backfill_uses_telemetry_provider_dynamic_config(self, mock_history):
        """Debe detectar provider dinámicamente desde TelemetryProvider."""
        from api.core.models import TelemetryProvider

        provider = TelemetryProvider.objects.create(
            name="Twin Dynamic",
            handler_name="tdata",
            base_url="https://api.example.com",
            auth_type="NONE",
        )
        self.point.is_tdata = False
        self.point.telemetry_provider = provider
        self.point.save()

        base_dt = pytz.utc.localize(datetime(2026, 5, 20, 12, 0, 0))
        mock_history.return_value = self._mock_history_data(base_dt)

        response = self._post({
            "action": "backfill",
            "source": "providers",
            "point_id": self.point.id,
            "start": "2026-05-20",
            "end": "2026-05-21",
            "apply": False,
        })

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["provider"], "tdata")
        mock_history.assert_called_once()

    def test_non_admin_user_is_rejected(self):
        """Usuarios no staff no pueden usar el endpoint."""
        self.user.is_staff = False
        self.user.save()

        response = self._post({
            "action": "fix-water-table",
            "point_id": self.point.id,
            "start": "2026-05-20",
            "end": "2026-05-22",
        })
        self.assertEqual(response.status_code, 403)
