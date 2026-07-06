"""Registry de adaptadores de cumplimiento."""
from typing import Dict, Type

from .base import BaseComplianceAdapter


class ComplianceAdapterRegistry:
    """Mapa authority.code → adaptador."""

    _adapters: Dict[str, Type[BaseComplianceAdapter]] = {}

    @classmethod
    def register(cls, code: str) -> callable:
        def decorator(adapter_class: Type[BaseComplianceAdapter]) -> Type[BaseComplianceAdapter]:
            if not issubclass(adapter_class, BaseComplianceAdapter):
                raise ValueError("El adaptador debe heredar de BaseComplianceAdapter")
            cls._adapters[code] = adapter_class
            return adapter_class
        return decorator

    @classmethod
    def get_adapter_class(cls, code: str) -> Type[BaseComplianceAdapter]:
        adapter_class = cls._adapters.get(code)
        if adapter_class is None:
            raise ValueError(f"No hay adaptador registrado para '{code}'")
        return adapter_class

    @classmethod
    def get_adapter(cls, authority) -> BaseComplianceAdapter:
        adapter_class = cls.get_adapter_class(authority.code)
        return adapter_class(authority)

    @classmethod
    def registered_codes(cls):
        return list(cls._adapters.keys())
