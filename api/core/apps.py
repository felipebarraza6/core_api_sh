"""App Config"""
from django.apps import AppConfig


class CoreAppConfig(AppConfig):
    """AppConfig"""
    name = 'api.core'
    verbose_name = 'Operaciones y Telemetría'  # Nombre más descriptivo para el menú

    def ready(self):
        import api.core.signals
