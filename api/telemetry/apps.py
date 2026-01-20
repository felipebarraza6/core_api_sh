from django.apps import AppConfig


class TelemetryConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'api.telemetry'

    def ready(self):
        """Importar admins cuando la app esté lista."""
        # Importar admin de configuración para registrar modelos
        try:
            import api.telemetry.admin_configuration  # noqa
        except ImportError:
            pass  # Ignorar si no existe aún
