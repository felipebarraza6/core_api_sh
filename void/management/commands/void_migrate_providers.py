"""Migrate legacy TelemetryProvider records into void.Provider + endpoints."""
from django.core.management.base import BaseCommand

from api.core.models import TelemetryProvider
from void.models import Provider, ProviderEndpoint


class Command(BaseCommand):
    help = "Migra proveedores legacy (TelemetryProvider) a void.Provider + ProviderEndpoint"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="No crear registros, solo mostrar lo que se haría.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        migrated = 0
        created = 0
        endpoints_created = 0

        for legacy in TelemetryProvider.objects.filter(is_active=True):
            handler = legacy.handler_name
            builder = self._BUILDERS.get(handler)
            if not builder:
                self.stdout.write(
                    self.style.WARNING(
                        f"Proveedor {legacy.name} (handler={handler}) no tiene migrador. Omitido."
                    )
                )
                continue

            if dry_run:
                self.stdout.write(
                    self.style.NOTICE(
                        f"Dry-run: migraría {legacy.name} ({handler}) → void.Provider"
                    )
                )
                migrated += 1
                continue

            provider, was_created = self._get_or_create_provider(legacy)
            if was_created:
                created += 1
            else:
                migrated += 1

            # Limpiar endpoints previos para evitar duplicados al reejecutar
            provider.endpoints.all().delete()
            provider_endpoints = builder(self, provider, legacy)
            endpoints_created += provider_endpoints

            self.stdout.write(
                self.style.SUCCESS(
                    f"{'Creado' if was_created else 'Actualizado'}: {provider} con {provider_endpoints} endpoints"
                )
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Migración completa: {created} creados, {migrated} actualizados, "
                f"{endpoints_created} endpoints creados."
            )
        )

    def _get_or_create_provider(self, legacy: TelemetryProvider):
        defaults = {
            "name": legacy.name,
            "description": f"Migrado desde TelemetryProvider id={legacy.id} ({legacy.handler_name})",
            "protocol": legacy.protocol,
            "base_url": legacy.base_url or "",
            "is_active": legacy.is_active,
            "metadata": {
                "legacy_provider_id": legacy.id,
                "handler_name": self._VOID_HANDLER.get(legacy.handler_name, "dynamic_http"),
                "timeout_seconds": legacy.timeout_seconds,
                "retry_attempts": legacy.retry_attempts,
            },
        }
        return Provider.objects.update_or_create(
            name=legacy.name,
            defaults=defaults,
        )

    _VOID_HANDLER = {
        "tdata": "tdata",
        "thethings": "dynamic_http",
        "tago": "dynamic_http",
        "generic_json": "dynamic_http",
    }

    def _build_tdata(self, provider: Provider, legacy: TelemetryProvider) -> int:
        provider.auth_type = "CUSTOM"
        provider.auth_config = {
            "username": legacy.auth_username or "",
            "password": legacy.auth_password or "",
        }
        provider.save(update_fields=["auth_type", "auth_config"])

        ProviderEndpoint.objects.create(
            provider=provider,
            endpoint_type="AUTH",
            name="Login TDATA",
            http_method="POST",
            path_template="/login",
            body_template={
                "username": "{username}",
                "password": "{password}",
            },
            headers={"Content-Type": "application/json"},
            response_parser={"token_field": "token"},
        )
        ProviderEndpoint.objects.create(
            provider=provider,
            endpoint_type="INGEST",
            name="Telemetry TDATA",
            http_method="GET",
            path_template="/telemetry/DEVICE/{external_id}/values/timeseries",
            query_params={
                "keys": "{variable}",
                "startTs": "{startTs}",
                "endTs": "{endTs}",
                "limit": "{limit}",
                "asc": "true",
            },
            response_parser={
                "response_is_array": True,
                "value_field": "value",
                "timestamp_field": "ts",
                "timestamp_format": "epoch_ms",
            },
        )
        return 2

    def _build_thethings(self, provider: Provider, legacy: TelemetryProvider) -> int:
        provider.auth_type = "NONE"
        provider.auth_config = {}
        provider.save(update_fields=["auth_type", "auth_config"])

        ProviderEndpoint.objects.create(
            provider=provider,
            endpoint_type="INGEST",
            name="Resources TheThings.io",
            http_method="GET",
            path_template="/things/{external_id}/resources/{variable}",
            response_parser={
                "response_is_array": True,
                "value_field": "value",
                "timestamp_field": "datetime",
                "timestamp_format": "iso",
            },
        )
        return 1

    def _build_tago(self, provider: Provider, legacy: TelemetryProvider) -> int:
        # Tago.io usa el token por dispositivo (external_id) en el header.
        # El auth_config del proveedor define el header; el valor se resuelve
        # por dispositivo en DynamicHttpProvider con placeholders.
        provider.auth_type = "API_KEY_HEADER"
        provider.auth_config = {
            "header_name": legacy.auth_header_name or "authorization",
            "api_key": "{external_id}",
        }
        provider.save(update_fields=["auth_type", "auth_config"])

        ProviderEndpoint.objects.create(
            provider=provider,
            endpoint_type="INGEST",
            name="Último valor Tago.io",
            http_method="GET",
            path_template="/data/",
            query_params={
                "variable": "{variable}",
                "query": "last_item",
            },
            response_parser={
                "response_root_key": "result",
                "response_is_array": True,
                "value_field": "value",
                "timestamp_field": "time",
                "timestamp_format": "iso",
            },
        )
        ProviderEndpoint.objects.create(
            provider=provider,
            endpoint_type="INGEST",
            name="Histórico Tago.io",
            http_method="GET",
            path_template="/data",
            order=1,
            query_params={
                "variable": "{variable}",
                "start_date": "{start_date}",
                "end_date": "{end_date}",
                "qty": "{limit}",
            },
            response_parser={
                "response_root_key": "result",
                "response_is_array": True,
                "value_field": "value",
                "timestamp_field": "time",
                "timestamp_format": "iso",
            },
        )
        return 2

    def _build_generic_json(self, provider: Provider, legacy: TelemetryProvider) -> int:
        auth_config = {}
        auth_type = legacy.auth_type
        if auth_type == "BASIC":
            auth_config = {
                "username": legacy.auth_username or "",
                "password": legacy.auth_password or "",
            }
        elif auth_type in ("BEARER", "API_KEY_HEADER"):
            auth_config = {
                "token": legacy.auth_token or "",
                "header_name": legacy.auth_header_name or "Authorization",
            }
        elif auth_type == "QUERY_PARAM":
            auth_config = {
                "api_key": legacy.auth_token or "",
                "key_name": "api_key",
            }

        provider.auth_type = auth_type if auth_type != "QUERY_PARAM" else "API_KEY_QUERY"
        provider.auth_config = auth_config
        provider.save(update_fields=["auth_type", "auth_config"])

        path_template = legacy.endpoint_template or "/{token}/{variable}"
        ProviderEndpoint.objects.create(
            provider=provider,
            endpoint_type="INGEST",
            name="Genérico JSON",
            http_method="GET",
            path_template=path_template,
            response_parser=legacy.parser_config or {},
        )
        return 1

    _BUILDERS = {
        "tdata": _build_tdata,
        "thethings": _build_thethings,
        "tago": _build_tago,
        "generic_json": _build_generic_json,
    }
