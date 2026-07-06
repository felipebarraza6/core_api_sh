"""Provider registry for void."""
from typing import Any, Dict, List, Optional, Type

from void.models import Provider

from .base import BaseProvider, DynamicHttpProvider
from .tdata import TdataProvider


class ProviderRegistry:
    """Registro de handlers de proveedores.

    Permite agregar handlers específicos (p.ej. TDATA con login propio) sin
    tocar el orquestador. Si no hay handler registrado, usa DynamicHttpProvider.
    """

    def __init__(self):
        self._handlers: Dict[str, Type[BaseProvider]] = {
            "dynamic_http": DynamicHttpProvider,
            "tdata": TdataProvider,
        }

    def register(self, provider_class: Type[BaseProvider]) -> Type[BaseProvider]:
        if not provider_class.name:
            raise ValueError(f"{provider_class.__name__} debe definir name")
        self._handlers[provider_class.name] = provider_class
        return provider_class

    def get(self, handler_name: str) -> Optional[Type[BaseProvider]]:
        return self._handlers.get(handler_name)

    def build(self, provider: Provider) -> BaseProvider:
        """Construye el provider adecuado para un Provider configurado.

        Si el proveedor tiene un handler_name en metadata, lo usa.
        Si no, usa DynamicHttpProvider según el protocolo.
        """
        handler_name = provider.metadata.get("handler_name")
        if handler_name and handler_name in self._handlers:
            return self._handlers[handler_name](provider)

        if provider.protocol in ("HTTP_REST", "HTTP_GET"):
            return DynamicHttpProvider(provider)

        raise ValueError(f"No hay handler para protocolo {provider.protocol}")

    def list_handlers(self) -> List[str]:
        return list(self._handlers.keys())


# Registro global
registry = ProviderRegistry()
