"""Tests for void compliance module."""
from datetime import datetime
from decimal import Decimal
from unittest.mock import Mock, patch

from django.test import TestCase
from django.utils import timezone

from void.models import (
    ComplianceAuthority,
    ComplianceStandard,
    ComplianceSubmission,
    Device,
    Point,
    PointComplianceProfile,
    ProcessedReading,
)
from void.services import ComplianceService
from void.services.compliance import ComplianceAdapterRegistry, DGAComplianceAdapter, SMAComplianceAdapter
from void.services.compliance.base import ComplianceResult


class ComplianceStandardTests(TestCase):
    def setUp(self):
        self.mayor = ComplianceStandard.objects.create(
            code="TEST_MAYOR",
            name="Mayor",
            send_minute=0,
        )
        self.medio = ComplianceStandard.objects.create(
            code="TEST_MEDIO",
            name="Medio",
            send_minute=0,
            send_hour=0,
        )
        self.menor = ComplianceStandard.objects.create(
            code="TEST_MENOR",
            name="Menor",
            send_minute=0,
            send_hour=0,
            send_day=1,
        )
        self.sma = ComplianceStandard.objects.create(
            code="TEST_SMA_5",
            name="SMA cada 5 min",
            minute_interval=5,
        )

    def test_mayor_matches_hourly(self):
        self.assertTrue(self.mayor.matches_timestamp(datetime(2026, 1, 1, 12, 0, 0)))
        self.assertFalse(self.mayor.matches_timestamp(datetime(2026, 1, 1, 12, 7, 0)))

    def test_medio_matches_daily(self):
        self.assertTrue(self.medio.matches_timestamp(datetime(2026, 1, 1, 0, 0, 0)))
        self.assertFalse(self.medio.matches_timestamp(datetime(2026, 1, 1, 12, 0, 0)))

    def test_menor_matches_monthly(self):
        self.assertTrue(self.menor.matches_timestamp(datetime(2026, 1, 1, 0, 0, 0)))
        self.assertFalse(self.menor.matches_timestamp(datetime(2026, 1, 15, 0, 0, 0)))

    def test_minute_interval(self):
        self.assertTrue(self.sma.matches_timestamp(datetime(2026, 1, 1, 12, 10, 0)))
        self.assertFalse(self.sma.matches_timestamp(datetime(2026, 1, 1, 12, 7, 0)))


class ComplianceAuthorityTests(TestCase):
    def test_create_dga_authority(self):
        auth = ComplianceAuthority.objects.create(
            code="dga",
            name="DGA",
            protocol="HTTP_REST",
            auth_type="JSON_BODY",
            base_url="https://apimee.mop.gob.cl/api/v1",
            auth_username="user",
            auth_password="pass",
            protocol_config={
                "subterraneo_endpoint": "/mediciones/subterraneas",
                "superficial_endpoint": "/mediciones/superficiales/flujometro",
                "default_rut_empresa": "76944359-2",
            },
        )
        self.assertEqual(auth.code, "dga")
        self.assertEqual(auth.get_auth_payload(), {"usuario": "user", "password": "pass"})

    def test_bearer_headers(self):
        auth = ComplianceAuthority.objects.create(
            code="sma",
            name="SMA",
            auth_type="BEARER",
            auth_token="abc123",
        )
        self.assertEqual(auth.get_auth_headers(), {"Authorization": "Bearer abc123"})


class PointComplianceProfileTests(TestCase):
    def setUp(self):
        self.point = Point.objects.create(name="P-Compliance")
        self.authority = ComplianceAuthority.objects.create(code="dga", name="DGA")

    def test_profile_unique_per_point_authority(self):
        PointComplianceProfile.objects.create(
            point=self.point,
            authority=self.authority,
            external_code="OBRA-123",
        )
        with self.assertRaises(Exception):
            PointComplianceProfile.objects.create(
                point=self.point,
                authority=self.authority,
                external_code="OBRA-999",
            )

    def test_resolve_value_with_mapping(self):
        device = Device.objects.create(point=self.point, configuration={})
        reading = ProcessedReading.objects.create(
            device=device,
            variable="pulses",
            timestamp=timezone.now(),
            total=Decimal("150.000"),
            extra_values={"ph": 7.2},
        )
        profile = PointComplianceProfile.objects.create(
            point=self.point,
            authority=self.authority,
            variable_mapping={"total": "total", "custom": "extra_values.ph"},
        )
        self.assertEqual(profile.resolve_value(reading, "total"), Decimal("150.000"))
        self.assertEqual(profile.resolve_value(reading, "custom"), 7.2)


class DGAAdapterTests(TestCase):
    def setUp(self):
        self.point = Point.objects.create(name="P-DGA")
        self.device = Device.objects.create(point=self.point, configuration={})
        self.authority = ComplianceAuthority.objects.create(
            code="dga",
            name="DGA",
            base_url="https://apimee.mop.gob.cl/api/v1",
            auth_type="JSON_BODY",
            auth_username="17352192-8",
            auth_password="secret",
            protocol_config={
                "subterraneo_endpoint": "/mediciones/subterraneas",
                "superficial_endpoint": "/mediciones/superficiales/flujometro",
                "default_rut_empresa": "76944359-2",
            },
        )
        self.profile = PointComplianceProfile.objects.create(
            point=self.point,
            authority=self.authority,
            external_code="OBRA-123",
            type_key="SUBTERRANEO",
            variable_mapping={"total": "total", "flow": "flow", "water_table": "water_table"},
        )
        self.reading = ProcessedReading.objects.create(
            device=self.device,
            variable="pulses",
            timestamp=timezone.make_aware(datetime(2026, 1, 1, 12, 0, 0)),
            total=Decimal("1000.000"),
            flow=Decimal("12.340"),
            water_table=Decimal("5.500"),
        )

    def test_build_payload_subterraneo(self):
        adapter = DGAComplianceAdapter(self.authority)
        payload = adapter.build_payload(self.profile, self.reading)

        self.assertIn("autenticacion", payload)
        self.assertIn("medicionSubterranea", payload)
        self.assertEqual(payload["autenticacion"]["rutUsuario"], "17352192-8")
        self.assertEqual(payload["autenticacion"]["rutEmpresa"], "76944359-2")
        self.assertEqual(payload["medicionSubterranea"]["totalizador"], "1000")
        self.assertEqual(payload["medicionSubterranea"]["caudal"], "12.34")
        self.assertEqual(payload["medicionSubterranea"]["nivelFreaticoDelPozo"], "5.5")

    def test_build_payload_superficial(self):
        self.profile.type_key = "SUPERFICIAL"
        self.profile.save()
        adapter = DGAComplianceAdapter(self.authority)
        payload = adapter.build_payload(self.profile, self.reading)

        self.assertIn("medicionSuperficialFlujometro", payload)
        self.assertNotIn("nivelFreaticoDelPozo", payload["medicionSuperficialFlujometro"])

    def test_handle_response_200(self):
        adapter = DGAComplianceAdapter(self.authority)
        result = adapter.handle_response(200, '{"comprobante": "CMP-1"}')
        self.assertTrue(result.success)
        self.assertEqual(result.status, "confirmed")
        self.assertEqual(result.voucher, "CMP-1")

    def test_handle_response_duplicate(self):
        adapter = DGAComplianceAdapter(self.authority)
        body = '{"message": "Ya existe un registro. Comprobante: ABC123"}'
        result = adapter.handle_response(400, body)
        self.assertTrue(result.success)
        self.assertEqual(result.status, "duplicate")
        self.assertEqual(result.voucher, "ABC123")

    def test_handle_response_unrecoverable(self):
        adapter = DGAComplianceAdapter(self.authority)
        body = '{"message": "Usuario no es el informante registrado en la Obra"}'
        result = adapter.handle_response(400, body)
        self.assertFalse(result.success)
        self.assertEqual(result.status, "unrecoverable")

    @patch("void.services.compliance.dga.requests.post")
    def test_send_success(self, mock_post):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '{"comprobante": "CMP-99"}'
        mock_post.return_value = mock_response

        adapter = DGAComplianceAdapter(self.authority)
        payload = adapter.build_payload(self.profile, self.reading)
        result = adapter.send(payload)

        self.assertTrue(result.success)
        self.assertEqual(result.status, "confirmed")
        self.assertEqual(result.voucher, "CMP-99")
        mock_post.assert_called()


class SMAAdapterTests(TestCase):
    def setUp(self):
        self.point = Point.objects.create(name="P-SMA")
        self.device = Device.objects.create(point=self.point, configuration={})
        self.authority = ComplianceAuthority.objects.create(
            code="sma",
            name="SMA",
            base_url="https://conexiones.sma.gob.cl/api/v1",
            auth_type="JSON_BODY",
            auth_username="user",
            auth_password="pass",
            protocol_config={"token_prefix": "Bearer"},
        )
        self.profile = PointComplianceProfile.objects.create(
            point=self.point,
            authority=self.authority,
            external_code="DEV-1",
            variable_mapping={"total": "total", "flow": "flow"},
        )
        self.reading = ProcessedReading.objects.create(
            device=self.device,
            variable="pulses",
            timestamp=timezone.make_aware(datetime(2026, 1, 1, 12, 0, 0)),
            total=Decimal("500.000"),
            flow=Decimal("8.500"),
        )

    def test_build_payload(self):
        adapter = SMAComplianceAdapter(self.authority)
        payload = adapter.build_payload(self.profile, self.reading)
        self.assertEqual(payload["device_id"], "DEV-1")
        self.assertEqual(payload["flow"], 8.5)

    @patch("void.services.compliance.sma.requests.post")
    def test_send_success(self, mock_post):
        # Primer post -> auth, segundo post -> medición
        mock_auth = Mock()
        mock_auth.status_code = 200
        mock_auth.json.return_value = {"token": "tok-sma"}

        mock_send = Mock()
        mock_send.status_code = 201
        mock_send.text = '{"id_verificacion": "VER-1"}'

        mock_post.side_effect = [mock_auth, mock_send]

        adapter = SMAComplianceAdapter(self.authority)
        payload = adapter.build_payload(self.profile, self.reading)
        result = adapter.send(payload)

        self.assertTrue(result.success)
        self.assertEqual(result.status, "confirmed")
        self.assertEqual(result.tracking_id, "VER-1")


class ComplianceServiceTests(TestCase):
    def setUp(self):
        self.point = Point.objects.create(name="P-Service")
        self.device = Device.objects.create(point=self.point, configuration={})
        self.authority = ComplianceAuthority.objects.create(
            code="dga",
            name="DGA",
            base_url="https://apimee.mop.gob.cl/api/v1",
            auth_type="JSON_BODY",
            auth_username="17352192-8",
            auth_password="secret",
            retry_attempts=3,
            protocol_config={"default_rut_empresa": "76944359-2"},
        )
        self.profile = PointComplianceProfile.objects.create(
            point=self.point,
            authority=self.authority,
            external_code="OBRA-123",
            type_key="SUBTERRANEO",
            variable_mapping={"total": "total", "flow": "flow"},
        )
        self.reading = ProcessedReading.objects.create(
            device=self.device,
            variable="pulses",
            timestamp=timezone.make_aware(datetime(2026, 1, 1, 12, 0, 0)),
            total=Decimal("1000.000"),
            flow=Decimal("10.000"),
        )

    @patch("void.services.compliance.dga.requests.post")
    def test_submit_reading_creates_submission(self, mock_post):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '{"comprobante": "CMP-1"}'
        mock_post.return_value = mock_response

        service = ComplianceService()
        submission = service.submit_reading(self.profile, self.reading)

        self.assertEqual(submission.status, "confirmed")
        self.assertEqual(submission.voucher, "CMP-1")
        self.assertEqual(submission.attempt_number, 1)
        self.assertIsNotNone(submission.sent_at)

    @patch("void.services.compliance.dga.requests.post")
    def test_submit_reading_duplicate(self, mock_post):
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.text = '{"message": "Ya existe un registro. Comprobante: DUP-1"}'
        mock_post.return_value = mock_response

        service = ComplianceService()
        submission = service.submit_reading(self.profile, self.reading)

        self.assertEqual(submission.status, "duplicate")
        self.assertEqual(submission.voucher, "DUP-1")

    def test_sma_minute_filter(self):
        sma_standard = ComplianceStandard.objects.create(
            code="SMA_MINUTE",
            name="SMA cada 5 minutos",
            minute_interval=5,
        )
        sma_auth = ComplianceAuthority.objects.create(
            code="sma",
            name="SMA",
            base_url="https://conexiones.sma.gob.cl/api/v1",
            auth_type="JSON_BODY",
            auth_username="user",
            auth_password="pass",
        )
        sma_profile = PointComplianceProfile.objects.create(
            point=self.point,
            authority=sma_auth,
            standard=sma_standard,
            external_code="DEV-1",
            variable_mapping={"total": "total", "flow": "flow"},
        )
        reading = ProcessedReading.objects.create(
            device=self.device,
            variable="pulses",
            timestamp=timezone.make_aware(datetime(2026, 1, 1, 12, 7, 0)),
            total=Decimal("100.000"),
        )

        service = ComplianceService()
        submission = service.submit_reading(sma_profile, reading)

        self.assertEqual(submission.status, "unrecoverable")
        self.assertIn("minuto", submission.error_message)

    def test_submit_reading_rejected_by_standard(self):
        standard = ComplianceStandard.objects.create(
            code="HOURLY",
            name="Horario en punto",
            send_minute=0,
        )
        self.profile.standard = standard
        self.profile.save()

        # Lectura con minuto 7 no califica para estándar horario
        reading = ProcessedReading.objects.create(
            device=self.device,
            variable="pulses",
            timestamp=timezone.make_aware(datetime(2026, 1, 1, 12, 7, 0)),
            total=Decimal("100.000"),
            flow=Decimal("1.000"),
        )

        service = ComplianceService()
        submission = service.submit_reading(self.profile, reading)

        self.assertEqual(submission.status, "unrecoverable")
        self.assertIn("no califica", submission.error_message)

    @patch("void.services.compliance.dga.requests.post")
    def test_process_queue(self, mock_post):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '{"comprobante": "CMP-Q"}'
        mock_post.return_value = mock_response

        # Crear submission pendiente manualmente
        submission = ComplianceSubmission.objects.create(
            profile=self.profile,
            processed_reading=self.reading,
            payload={},
            status="pending",
        )

        service = ComplianceService()
        summary = service.process_queue(max_submissions=10)

        self.assertEqual(summary["processed"], 1)
        self.assertEqual(summary["confirmed"], 1)
        submission.refresh_from_db()
        self.assertEqual(submission.status, "confirmed")


class ComplianceAdapterRegistryTests(TestCase):
    def test_registered_adapters(self):
        self.assertIn("dga", ComplianceAdapterRegistry.registered_codes())
        self.assertIn("sma", ComplianceAdapterRegistry.registered_codes())

    def test_get_adapter(self):
        authority = ComplianceAuthority.objects.create(code="dga", name="DGA")
        adapter = ComplianceAdapterRegistry.get_adapter(authority)
        self.assertIsInstance(adapter, DGAComplianceAdapter)
