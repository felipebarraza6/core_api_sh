"""Registry de handlers de procesamiento para void.

Los únicos tipos fundamentales son:
  - stateful  : motor de reglas con memoria (ProcessingSchema).
  - formula   : fórmula directa sobre la lectura.
  - passthrough: guarda el valor crudo tal cual.
  - none      : sin clasificar (marca error).

Toda la lógica de negocio (totalizador, nivel, etc.) vive como reglas
stateful en ``void.services.handlers.stateful_rulesets``.
"""
from void.services.handlers.base import BaseHandler, HandlerResult
from void.services.handlers.formula import FormulaHandler
from void.services.handlers.generic import PassthroughHandler, UnconfiguredHandler
from void.services.handlers.stateful import StatefulRuleHandler
from void.services.handlers.stateful_rulesets import (
    apply_nivel_schema,
    apply_totalizer_schema,
    create_nivel_schema,
    create_totalizer_schema,
)


class HandlerRegistry:
    """Mapa processing_type → handler."""

    _handlers = {
        "stateful": StatefulRuleHandler,
        "formula": FormulaHandler,
        "passthrough": PassthroughHandler,
        "none": UnconfiguredHandler,
    }

    @classmethod
    def get_handler(cls, processing_type: str) -> BaseHandler:
        handler_class = cls._handlers.get(processing_type)
        if handler_class is None:
            return UnconfiguredHandler()
        return handler_class()

    @classmethod
    def register(cls, processing_type: str, handler_class: type) -> None:
        if not issubclass(handler_class, BaseHandler):
            raise ValueError("El handler debe heredar de BaseHandler")
        cls._handlers[processing_type] = handler_class


__all__ = [
    "BaseHandler",
    "HandlerResult",
    "HandlerRegistry",
    "FormulaHandler",
    "StatefulRuleHandler",
    "PassthroughHandler",
    "UnconfiguredHandler",
    "create_totalizer_schema",
    "create_nivel_schema",
    "apply_totalizer_schema",
    "apply_nivel_schema",
]
