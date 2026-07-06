"""App config for void."""
from django.apps import AppConfig


class VoidConfig(AppConfig):
    """Configuración de la app void."""

    name = "void"
    verbose_name = "Void — Nueva generación"

    def ready(self):
        # Importar señales cuando existan.
        # Por ahora no registramos señales para mantener desacoplamiento con legacy.
        import void.signals  # noqa: F401
