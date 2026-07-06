"""Tests for migration of legacy providers into void."""
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from api.core.models import TelemetryProvider
from void.models import Provider, ProviderEndpoint


class MigrateProvidersTests(TestCase):
    def test_migrate_tdata_creates_provider_and_endpoints(self):
        legacy = TelemetryProvider.objects.create(
            name="TwinDimension TDATA",
            handler_name="tdata",
            protocol="HTTP_REST",
            base_url="https://api.twindimension.com/tdata/v1",
            auth_type="BASIC",
            auth_username="user@example.com",
            auth_password="secret",
        )

        call_command("void_migrate_providers", stdout=StringIO())

        provider = Provider.objects.get(name=legacy.name)
        self.assertEqual(provider.protocol, "HTTP_REST")
        self.assertEqual(provider.auth_type, "CUSTOM")
        self.assertEqual(provider.auth_config["username"], "user@example.com")
        self.assertEqual(provider.auth_config["password"], "secret")
        self.assertEqual(provider.metadata["handler_name"], "tdata")

        endpoints = list(provider.endpoints.all())
        types = {e.endpoint_type for e in endpoints}
        self.assertIn("AUTH", types)
        self.assertIn("INGEST", types)

        ingest = provider.get_endpoint("INGEST")
        self.assertIn("keys", ingest.query_params)
        self.assertIn("startTs", ingest.query_params)

    def test_migrate_thethings_creates_ingest_endpoint(self):
        TelemetryProvider.objects.create(
            name="TheThings.io",
            handler_name="thethings",
            protocol="HTTP_REST",
            base_url="https://api.thethings.io/v2",
            auth_type="NONE",
        )

        call_command("void_migrate_providers", stdout=StringIO())

        provider = Provider.objects.get(name="TheThings.io")
        self.assertEqual(provider.auth_type, "NONE")
        self.assertEqual(provider.metadata["handler_name"], "dynamic_http")

        ingest = provider.get_endpoint("INGEST")
        self.assertIn("{external_id}", ingest.path_template)
        self.assertIn("{variable}", ingest.path_template)

    def test_migrate_tago_uses_device_token_in_auth(self):
        TelemetryProvider.objects.create(
            name="Tago.io",
            handler_name="tago",
            protocol="HTTP_REST",
            base_url="https://api.tago.io",
            auth_type="BEARER",
            auth_header_name="authorization",
        )

        call_command("void_migrate_providers", stdout=StringIO())

        provider = Provider.objects.get(name="Tago.io")
        self.assertEqual(provider.auth_type, "API_KEY_HEADER")
        self.assertEqual(provider.auth_config["api_key"], "{external_id}")

        ingest = provider.get_endpoint("INGEST")
        self.assertEqual(ingest.path_template, "/data/")
        self.assertEqual(ingest.query_params.get("query"), "last_item")

    def test_migrate_is_idempotent(self):
        TelemetryProvider.objects.create(
            name="TheThings.io",
            handler_name="thethings",
            protocol="HTTP_REST",
            base_url="https://api.thethings.io/v2",
            auth_type="NONE",
        )

        call_command("void_migrate_providers", stdout=StringIO())
        first_count = ProviderEndpoint.objects.count()

        call_command("void_migrate_providers", stdout=StringIO())
        second_count = ProviderEndpoint.objects.count()

        self.assertEqual(first_count, second_count)
