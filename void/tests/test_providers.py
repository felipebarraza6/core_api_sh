"""Tests for void provider configuration."""
from datetime import datetime

from django.test import TestCase
from django.utils import timezone

from void.models import Device, Point, Provider, ProviderEndpoint
from void.services.providers.base import DynamicHttpProvider
from void.services.providers.registry import registry


class ProviderTests(TestCase):
    def test_create_provider_with_endpoints(self):
        provider = Provider.objects.create(
            name="API Externa Test",
            protocol="HTTP_REST",
            base_url="https://api.example.com",
            auth_type="BEARER",
            auth_config={"token": "abc123"},
        )
        endpoint = ProviderEndpoint.objects.create(
            provider=provider,
            endpoint_type="INGEST",
            http_method="GET",
            path_template="/devices/{external_id}/readings/{variable}",
            response_parser={
                "response_is_array": True,
                "value_field": "value",
                "timestamp_field": "ts",
                "timestamp_format": "iso",
            },
        )
        self.assertEqual(str(provider), "API Externa Test (HTTP_REST)")
        self.assertEqual(provider.get_endpoint("INGEST"), endpoint)
        self.assertIsNone(provider.get_endpoint("AUTH"))

    def test_dynamic_http_provider_builds_url(self):
        provider = Provider.objects.create(
            name="Dynamic Test",
            protocol="HTTP_REST",
            base_url="https://api.example.com/v1",
        )
        ProviderEndpoint.objects.create(
            provider=provider,
            endpoint_type="INGEST",
            http_method="GET",
            path_template="/devices/{external_id}/{variable}",
            response_parser={"response_is_array": True},
        )
        point = Point.objects.create(name="P1")
        device = Device.objects.create(
            point=point,
            external_id="dev-123",
            provider=provider,
        )

        dyn = registry.build(provider)
        self.assertIsInstance(dyn, DynamicHttpProvider)

        url = dyn._build_url(
            provider.get_endpoint("INGEST"),
            device,
            "pulses",
            None,
            None,
        )
        self.assertEqual(url, "https://api.example.com/v1/devices/dev-123/pulses")

    def test_dynamic_http_provider_parses_payload(self):
        provider = Provider.objects.create(name="Parser Test", protocol="HTTP_REST")
        dyn = DynamicHttpProvider(provider)
        payload = [
            {"value": 10, "ts": "2026-01-01T00:00:00Z", "u": "pulses"},
        ]
        results = dyn._parse_payload(payload, {
            "response_is_array": True,
            "value_field": "value",
            "timestamp_field": "ts",
            "unit_field": "u",
            "timestamp_format": "iso",
        })
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["value"], 10)
        self.assertEqual(results[0]["unit"], "pulses")
        self.assertIsInstance(results[0]["timestamp"], datetime)

    def test_registry_fallback_to_dynamic_http(self):
        provider = Provider.objects.create(name="Fallback", protocol="HTTP_GET")
        handler = registry.build(provider)
        self.assertIsInstance(handler, DynamicHttpProvider)


class TheThingsProviderMappingTests(TestCase):
    """Valida que TheThings.io se puede configurar solo con ProviderEndpoint."""

    def test_thetthings_url_and_parser(self):
        provider = Provider.objects.create(
            name="TheThings.io",
            protocol="HTTP_REST",
            base_url="https://api.thethings.io/v2",
            auth_type="NONE",
            metadata={"handler_name": "dynamic_http"},
        )
        ProviderEndpoint.objects.create(
            provider=provider,
            endpoint_type="INGEST",
            http_method="GET",
            path_template="/things/{external_id}/resources/{variable}",
            response_parser={
                "response_is_array": True,
                "value_field": "value",
                "timestamp_field": "datetime",
                "timestamp_format": "iso",
            },
        )
        point = Point.objects.create(name="P1")
        device = Device.objects.create(
            point=point,
            external_id="thethings-token-123",
            provider=provider,
        )

        dyn = registry.build(provider)
        url = dyn._build_url(
            provider.get_endpoint("INGEST"),
            device,
            "pulses",
            None,
            None,
        )
        self.assertEqual(
            url,
            "https://api.thethings.io/v2/things/thethings-token-123/resources/pulses",
        )

        payload = [{"datetime": "2026-01-01T00:00:00.000Z", "value": 42}]
        results = dyn._parse_payload(payload, provider.get_endpoint("INGEST").response_parser)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["value"], 42)
        self.assertIsInstance(results[0]["timestamp"], datetime)


class TagoProviderMappingTests(TestCase):
    """Valida que Tago.io se puede configurar solo con ProviderEndpoint."""

    def test_tago_url_and_parser(self):
        provider = Provider.objects.create(
            name="Tago.io",
            protocol="HTTP_REST",
            base_url="https://api.tago.io",
            auth_type="API_KEY_HEADER",
            auth_config={
                "api_key": "tago-device-token",
                "header_name": "authorization",
            },
            metadata={"handler_name": "dynamic_http"},
        )
        ProviderEndpoint.objects.create(
            provider=provider,
            endpoint_type="INGEST",
            http_method="GET",
            path_template="/data/",
            query_params={"variable": "{variable}", "query": "last_item"},
            response_parser={
                "response_root_key": "result",
                "response_is_array": True,
                "value_field": "value",
                "timestamp_field": "time",
                "timestamp_format": "iso",
            },
        )
        point = Point.objects.create(name="P1")
        device = Device.objects.create(
            point=point,
            external_id="tago-token-123",
            provider=provider,
        )

        dyn = registry.build(provider)
        url = dyn._build_url(
            provider.get_endpoint("INGEST"),
            device,
            "pulses",
            None,
            None,
        )
        self.assertEqual(url, "https://api.tago.io/data/")

        params = dyn._build_query_params(
            provider.get_endpoint("INGEST"),
            device,
            "pulses",
            None,
            None,
        )
        self.assertEqual(params["variable"], "pulses")
        self.assertEqual(params["query"], "last_item")

        payload = {"result": [{"time": "2026-01-01T00:00:00.000Z", "value": 7.5}]}
        results = dyn._parse_payload(payload, provider.get_endpoint("INGEST").response_parser)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["value"], 7.5)

    def test_per_device_auth_with_external_id_placeholder(self):
        """Tago.io usa el token del dispositivo (external_id) como API key."""
        provider = Provider.objects.create(
            name="Tago Per-Device",
            protocol="HTTP_REST",
            base_url="https://api.tago.io",
            auth_type="API_KEY_HEADER",
            auth_config={
                "api_key": "{external_id}",
                "header_name": "authorization",
            },
            metadata={"handler_name": "dynamic_http"},
        )
        ProviderEndpoint.objects.create(
            provider=provider,
            endpoint_type="INGEST",
            http_method="GET",
            path_template="/data/",
            query_params={"variable": "{variable}", "query": "last_item"},
            response_parser={"response_is_array": True},
        )
        point = Point.objects.create(name="P1")
        device = Device.objects.create(
            point=point,
            external_id="device-token-xyz",
            provider=provider,
        )

        dyn = registry.build(provider)
        headers = dyn._build_auth_headers(device)
        self.assertEqual(headers["authorization"], "device-token-xyz")
