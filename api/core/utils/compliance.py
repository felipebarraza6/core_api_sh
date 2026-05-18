"""Helpers para obtener configuración de ComplianceProvider."""

from django.conf import settings

from api.core.models import ComplianceProvider


class ComplianceConfig:
    """
    Lee configuración de cumplimiento desde ComplianceProvider (BD)
    con fallback a settings/env.

    Uso:
        config = ComplianceConfig('dga')
        base_url = config.get('base_url', settings.DGA_BASE_URL)
    """

    def __init__(self, code):
        self.code = code
        self._provider = None
        self._load()

    def _load(self):
        try:
            self._provider = ComplianceProvider.objects.get(
                code=self.code, is_active=True
            )
        except ComplianceProvider.DoesNotExist:
            self._provider = None

    def get(self, attr, fallback=None):
        """Obtener atributo del provider o fallback."""
        if self._provider and hasattr(self._provider, attr):
            val = getattr(self._provider, attr)
            if val not in (None, ''):
                return val
        return fallback

    def get_protocol_config(self, key, fallback=None):
        """Obtener clave de protocol_config JSON."""
        if self._provider and self._provider.protocol_config:
            return self._provider.protocol_config.get(key, fallback)
        return fallback

    @property
    def provider(self):
        return self._provider
