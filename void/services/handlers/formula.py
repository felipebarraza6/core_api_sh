"""Handler para variables configurables mediante fórmula."""
from decimal import Decimal, InvalidOperation

from void.services.handlers.base import BaseHandler, HandlerResult


class FormulaHandler(BaseHandler):
    """Procesa una variable evaluando una fórmula configurable.

    Variables disponibles en la fórmula:
    - value: valor crudo de la lectura
    - scale, offset: de DeviceVariableConfig
    - d1, d2, d3, d4, d5, d6: constantes del punto
    """

    SAFE_FUNCTIONS = {
        "abs": abs,
        "max": max,
        "min": min,
        "round": round,
    }

    def process(self, raw_reading, config):
        try:
            raw_value = Decimal(str(raw_reading.raw_value))
        except (InvalidOperation, TypeError, ValueError):
            return HandlerResult(
                values={},
                is_error=True,
                error_message="Valor crudo no numérico",
            )

        formula = config.formula or "value"
        output_field = config.output_field or config.internal_variable or "value"

        point_constants = raw_reading.device.point.constants or {}

        context = {
            **self.SAFE_FUNCTIONS,
            "value": raw_value,
            "scale": Decimal(config.scale),
            "offset": Decimal(config.offset),
        }
        for key, val in point_constants.items():
            if key not in context:
                try:
                    context[key] = Decimal(str(val))
                except (InvalidOperation, TypeError, ValueError):
                    context[key] = val

        try:
            code = compile(formula, "<formula>", "eval")
            for name in code.co_names:
                if name not in context:
                    raise NameError(f"Nombre no permitido en fórmula: {name}")
            result = eval(code, {"__builtins__": {}}, context)
        except Exception as exc:
            return HandlerResult(
                values={},
                is_error=True,
                error_message=f"Error evaluando fórmula '{formula}': {exc}",
            )

        try:
            result_dec = Decimal(str(result))
        except (InvalidOperation, TypeError, ValueError):
            return HandlerResult(
                values={},
                is_error=True,
                error_message=f"Resultado de fórmula no numérico: {result}",
            )

        return HandlerResult(values={output_field: result_dec})
