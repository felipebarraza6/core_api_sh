"""
Tests del management command validate_telemetry_config (solo lectura).

Ítem 5 auditoría 2026-10-02: tokens compartidos y variables mal mapeadas.
"""
from django.test import TestCase
from django.core.management import call_command
from django.contrib.auth import get_user_model
from io import StringIO
import json

from api.core.models import (
    Client,
    ProjectCatchments,
    CatchmentPoint,
    ProfileDataConfigCatchment,
    SchemesCatchment,
    Variable,
)
from api.core.management.commands.validate_telemetry_config import (
    collect_config_issues,
)

User = get_user_model()


class ValidateTelemetryConfigTests(TestCase):
    """Detecta tokens duplicados y variables NIVEL sospechosas."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="cfg_user", password="x", email="c@test.com"
        )
        self.client_obj = Client.objects.create(name="Cfg Client")
        self.project = ProjectCatchments.objects.create(
            name="Cfg Project", client=self.client_obj
        )

    def _point(self, title):
        return CatchmentPoint.objects.create(
            title=title, owner_user=self.user, project=self.project
        )

    def test_detects_shared_provider_token(self):
        """Como #14/#27: dos puntos con el mismo token_service."""
        p14 = self._point("P100 Unipapel")
        p27 = self._point("Arauco Los Cuervos")
        shared = "thethings-shared-token-abcdef123456"
        for point in (p14, p27):
            profile = ProfileDataConfigCatchment.objects.get(point_catchment=point)
            profile.is_telemetry = True
            profile.token_service = shared
            profile.save()

        report = collect_config_issues()
        self.assertTrue(report["summary"]["has_issues"])
        self.assertGreaterEqual(report["summary"]["shared_token_groups"], 1)
        point_ids = {
            p["point_id"]
            for group in report["shared_tokens"]
            for p in group["points"]
        }
        self.assertIn(p14.id, point_ids)
        self.assertIn(p27.id, point_ids)

    def test_detects_suspicious_nivel_variable_name(self):
        """Como Monte Águila #26: NIVEL mapeado a 'Nivel Freático'."""
        p26 = self._point("Monte Aguila")
        profile = ProfileDataConfigCatchment.objects.get(point_catchment=p26)
        profile.is_telemetry = True
        profile.token_service = "unique-token-26"
        profile.save()
        scheme = SchemesCatchment.objects.create(
            name="Scheme MA", description="test"
        )
        scheme.points_catchment.add(p26)
        Variable.objects.create(
            scheme_catchment=scheme,
            str_variable="Nivel Freático",
            label="Nivel",
            type_variable="NIVEL",
            token_service="unique-token-26",
        )

        report = collect_config_issues()
        self.assertGreaterEqual(report["summary"]["suspicious_nivel_count"], 1)
        found = any(
            i["point_id"] == p26.id and "Freático" in i["str_variable"]
            for i in report["suspicious_nivel_variables"]
        )
        self.assertTrue(found)

    def test_command_is_readonly_json(self):
        """El comando corre en modo --json sin modificar BD."""
        p = self._point("Solo")
        profile = ProfileDataConfigCatchment.objects.get(point_catchment=p)
        profile.is_telemetry = True
        profile.token_service = "solo-token"
        profile.save()
        before = ProfileDataConfigCatchment.objects.count()
        out = StringIO()
        call_command("validate_telemetry_config", "--json", stdout=out)
        after = ProfileDataConfigCatchment.objects.count()
        self.assertEqual(before, after)
        data = json.loads(out.getvalue())
        self.assertIn("summary", data)
        self.assertIn("shared_tokens", data)
