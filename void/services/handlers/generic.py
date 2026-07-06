"""Handlers genéricos para variables no procesadas o passthrough."""
from decimal import Decimal, InvalidOperation

from void.services.handlers.base import BaseHandler, HandlerResult


class PassthroughHandler(BaseHandler):
    """Guarda el valor crudo tal cual en un campo del mismo nombre."""

    def process(self, raw_reading, config):
        try:
            value = Decimal(str(raw_reading.raw_value))
        except (InvalidOperation, TypeError, ValueError):
            value = raw_reading.raw_value

        return HandlerResult(
            values={config.internal_variable or "value": value},
        )


class UnconfiguredHandler(BaseHandler):
    """Variable sin clasificar: marca error para revisión humana."""

    def process(self, raw_reading, config):
        return HandlerResult(
            values={},
            is_error=True,
            error_message=(
                f"Variable '{raw_reading.source_variable}' no tiene processing_type asignado."
            ),
        )
