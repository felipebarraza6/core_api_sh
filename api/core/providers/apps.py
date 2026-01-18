from django.apps import AppConfig


class ProvidersConfig(AppConfig):
    """Configuración de la aplicación de proveedores dinámicos."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'api.core.providers'
    verbose_name = 'Proveedores Dinámicos'