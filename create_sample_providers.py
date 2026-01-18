#!/usr/bin/env python3
"""
Create Sample Providers

Script to create sample telemetry providers for testing the dynamic provider system.
"""

import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.providers.models import TelemetryProvider

def create_sample_providers():
    """Create sample providers for testing."""

    providers_data = [
        {
            'name': 'nettra',
            'display_name': 'Nettra IoT Platform',
            'description': 'Plataforma IoT especializada en monitoreo hidrológico',
            'provider_type': 'api',
            'base_url': 'https://api.nettra.cl/v1',
            'auth_method': 'bearer',
            'auth_config': {'token': 'sample_token_replace_with_real'},
            'endpoint_template': '/devices/{device_id}/data',
            'request_template': {'variable': '{variable_type}'},
            'response_mapping': {
                'timestamp': 'timestamp',
                'value': 'value',
                'unit': 'unit',
                'variable_type': 'variable'
            },
            'max_retries': 3,
            'timeout_seconds': 30
        },
        {
            'name': 'twin',
            'display_name': 'Twin Monitoring System',
            'description': 'Sistema de monitoreo avanzado con análisis predictivo',
            'provider_type': 'api',
            'base_url': 'https://api.twin.cl/v2',
            'auth_method': 'basic',
            'auth_config': {'username': 'sample_user', 'password': 'sample_pass'},
            'endpoint_template': '/sensors/{device_id}/readings',
            'request_template': {'type': '{variable_type}', 'period': 'latest'},
            'response_mapping': {
                'timestamp': 'measurement_time',
                'value': 'measurement_value',
                'unit': 'unit',
                'variable_type': 'measurement_type'
            },
            'max_retries': 2,
            'timeout_seconds': 25
        },
        {
            'name': 'novus',
            'display_name': 'Novus Automation',
            'description': 'Solución integral de automatización industrial',
            'provider_type': 'api',
            'base_url': 'https://api.novus.cl/v3',
            'auth_method': 'api_key',
            'auth_config': {'key': 'sample_api_key', 'header': 'X-API-Key'},
            'endpoint_template': '/devices/{device_id}/measurements',
            'request_template': {'parameter': '{variable_type}'},
            'response_mapping': {
                'timestamp': 'timestamp',
                'value': 'value',
                'unit': 'unit',
                'variable_type': 'parameter'
            },
            'max_retries': 3,
            'timeout_seconds': 20
        }
    ]

    created_providers = []

    for provider_data in providers_data:
        provider, created = TelemetryProvider.objects.get_or_create(
            name=provider_data['name'],
            defaults=provider_data
        )

        if created:
            print(f"✅ Creado proveedor: {provider.display_name}")
            created_providers.append(provider)
        else:
            print(f"ℹ️ Proveedor ya existe: {provider.display_name}")

    print(f"\n📊 Resumen: {len(created_providers)} proveedores creados, {len(providers_data) - len(created_providers)} ya existían")

    return created_providers

if __name__ == '__main__':
    create_sample_providers()