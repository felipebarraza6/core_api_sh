"""
Providers App Configuration
"""

from django.apps import AppConfig


class ProvidersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'api.providers'
    verbose_name = 'Proveedores de Telemetría'
