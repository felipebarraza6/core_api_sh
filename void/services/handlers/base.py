"""Base para handlers de procesamiento de telemetría."""
from abc import ABC, abstractmethod
from typing import Any, Dict

from void.models import DeviceVariableConfig, RawReading


class HandlerResult:
    """Resultado de un handler de procesamiento."""

    def __init__(
        self,
        values: Dict[str, Any],
        is_error: bool = False,
        error_message: str = "",
        metadata: Dict[str, Any] = None,
    ):
        self.values = values
        self.is_error = is_error
        self.error_message = error_message
        self.metadata = metadata or {}


class BaseHandler(ABC):
    """Handler base para procesar una RawReading según su DeviceVariableConfig."""

    @abstractmethod
    def process(
        self,
        raw_reading: RawReading,
        config: DeviceVariableConfig,
    ) -> HandlerResult:
        """Procesa la lectura y retorna valores normalizados."""
        raise NotImplementedError
