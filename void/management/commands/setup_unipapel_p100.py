"""Crea configuración de ejemplo: proveedor Unipapel, punto P100.

Uso:
    docker exec django_api_secure python manage.py setup_unipapel_p100
"""
from django.core.management.base import BaseCommand

from void.models import Device, Point, Provider
from void.services.handlers.stateful_rulesets import apply_totalizer_schema


class Command(BaseCommand):
    help = "Configura punto P100 de Unipapel con totalizador stateful."

    def handle(self, *args, **options):
        # Proveedor
        provider, _ = Provider.objects.update_or_create(
            name="Unipapel",
            defaults={
                "protocol": "HTTP_REST",
                "auth_type": "API_KEY_HEADER",
                "base_url": "https://ingesta.unipapel.smarthydro.cl",
                "auth_config": {"api_key": "unipapel-api-key", "header_name": "X-API-Key"},
                "metadata": {"default_format": "json"},
                "is_active": True,
            },
        )
        self.stdout.write(self.style.SUCCESS(f"Proveedor: {provider}"))

        # Punto
        point, _ = Point.objects.update_or_create(
            code_internal="UNIPAPEL-P100",
            defaults={
                "name": "P100 - Captación Río Principal",
                "client": "Unipapel",
                "project": "Planta Valdivia",
                "frequency_minutes": 60,
                "constants": {"d1": "0", "d2": "0", "d3": "0"},
                "is_active": True,
            },
        )
        self.stdout.write(self.style.SUCCESS(f"Punto: {point}"))

        # Device
        device, _ = Device.objects.update_or_create(
            serial_number="UNI-LOGGER-P100",
            defaults={
                "point": point,
                "provider": provider,
                "external_id": "unipapel_p100",
                "model": "Novus FieldLogger 1000",
                "configuration": {
                    "ingest_token": "tok-unipapel-p100",
                    "variables": ["pulses"],
                },
                "is_active": True,
            },
        )
        self.stdout.write(self.style.SUCCESS(f"Device: {device}"))

        # Config stateful totalizador
        config = apply_totalizer_schema(
            device=device,
            source_variable="pulses",
            internal_variable="pulses",
            output_field="total",
            pulses_factor=1000,
            max_diff_m3_per_hour=500,
            reconnection_threshold_hours=2,
        )
        self.stdout.write(self.style.SUCCESS(f"Config: {config}"))

        self.stdout.write(self.style.SUCCESS("\nConfiguración lista."))
        self.stdout.write(
            "Ingesta de prueba:\n"
            "  curl -X POST http://localhost/api/void/ingest/ \\\n"
            "    -H 'Content-Type: application/json' \\\n"
            "    -H 'X-Device-Token: tok-unipapel-p100' \\\n"
            "    -d '{\"serial_number\":\"UNI-LOGGER-P100\",\"source_variable\":\"pulses\",\"value\":\"100\"}'"
        )
