"""Handler para procesamiento con estado persistente.

Permite definir reglas condicionales que leen y escriben un estado
persistente (DeviceVariableState).  Útil para totalizadores, contadores,
alarmas flanqueadas y cualquier lógica que dependa de lecturas anteriores.

Las reglas se definen como ProcessingStep de tipo ``stateful`` dentro de un
ProcessingSchema.  Cada ProcessingRule del step tiene:
  - condition: fórmula string evaluada contra el contexto.
  - action: nombre de la acción registrada en StatefulActionRegistry.
  - action_params: parámetros específicos de la acción.
"""
import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Dict, Optional

Decimal = Decimal

from django.db import transaction
from django.utils import timezone

from void.models import (
    CounterResetLog,
    Device,
    DeviceEvent,
    DeviceVariableConfig,
    DeviceVariableState,
    ProcessingSchema,
    ProcessingStep,
    RawReading,
)
from void.services.handlers.base import BaseHandler, HandlerResult

logger = logging.getLogger(__name__)


class StatefulActionRegistry:
    """Registro de acciones ejecutables por StatefulRuleHandler."""

    _actions: Dict[str, Callable] = {}

    @classmethod
    def register(cls, name: str) -> Callable:
        def decorator(func: Callable) -> Callable:
            cls._actions[name] = func
            return func
        return decorator

    @classmethod
    def get(cls, name: str) -> Callable:
        action = cls._actions.get(name)
        if action is None:
            raise ValueError(f"Acción stateful desconocida: '{name}'")
        return action


class StatefulContext:
    """Contexto de ejecución de un handler stateful.

    Combina valor crudo, configuración, constantes del punto y estado
    persistente.  Expone todo bajo un namespace plano para las fórmulas.
    """

    SAFE_FUNCTIONS = {
        "abs": abs,
        "max": max,
        "min": min,
        "round": round,
        "int": int,
        "total_seconds": lambda td: td.total_seconds() if td else 0,
        "Decimal": Decimal,
        "to_date": lambda dt: dt.date().isoformat() if dt else None,
    }

    def __init__(
        self,
        raw_reading: RawReading,
        config: DeviceVariableConfig,
        state: DeviceVariableState,
    ):
        self.raw_reading = raw_reading
        self.config = config
        self.state = state
        self.values: Dict[str, Any] = {}
        self.metadata: Dict[str, Any] = {}
        self.is_error = False
        self.error_message = ""

        device = raw_reading.device
        point_constants = device.point.constants or {}

        raw_value = self._to_decimal(raw_reading.raw_value)

        frequency_minutes = getattr(getattr(device.point, "frequency_minutes", None), "__int__", lambda: None)()

        self.namespace: Dict[str, Any] = {
            **self.SAFE_FUNCTIONS,
            "value": raw_value,
            "raw_value": raw_reading.raw_value,
            "variable": raw_reading.variable,
            "source_variable": raw_reading.source_variable or raw_reading.variable,
            "timestamp": raw_reading.timestamp,
            "scale": self._to_decimal(config.scale),
            "offset": self._to_decimal(config.offset),
            "pulses_factor": int(config.pulses_factor or 1000),
            "max_diff_m3_per_hour": self._to_decimal(config.max_diff_m3_per_hour),
            "reconnection_threshold_hours": self._to_decimal(config.reconnection_threshold_hours),
            "compute_flow": bool(config.compute_flow),
            "frequency_minutes": frequency_minutes,
        }

        # Estado persistente bajo prefijo state_ para evitar colisiones.
        for key, val in (state.state or {}).items():
            parsed = self._parse_datetime(val)
            if self._is_numeric_string(parsed):
                parsed = self._to_decimal(parsed)
            self.namespace[f"state_{key}"] = parsed

        # Configuración extra (p.ej. calculate_nivel para nivel stateful).
        for key, val in (config.extra_data or {}).items():
            if key not in self.namespace:
                self.namespace[key] = self._to_decimal(val)

        # Constantes del punto.
        for key, val in point_constants.items():
            if key not in self.namespace:
                self.namespace[key] = self._to_decimal(val)

        # Defaults de variables físicas frecuentes para evitar NameError
        # cuando un schema las referencia pero no están configuradas.
        for key in ("d1", "d2", "d3", "d4", "d5", "d6"):
            if key not in self.namespace:
                self.namespace[key] = None

    @staticmethod
    def _to_decimal(value: Any) -> Any:
        if value is None:
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return value

    @staticmethod
    def _is_numeric_string(value: Any) -> bool:
        if not isinstance(value, str):
            return False
        try:
            Decimal(value)
            return True
        except (InvalidOperation, ValueError):
            return False

    @staticmethod
    def _parse_datetime(value: Any) -> Any:
        if not isinstance(value, str):
            return value
        for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
        return value

    def eval(self, formula: str) -> Any:
        if not formula:
            return None
        code = compile(formula, "<stateful>", "eval")
        for name in code.co_names:
            if name not in self.namespace:
                # Las claves de estado futuras son legítimas; se inician en None.
                if name.startswith("state_"):
                    self.namespace[name] = None
                else:
                    raise NameError(f"Nombre no permitido en fórmula: {name}")
        return eval(code, {"__builtins__": {}}, self.namespace)

    def set_output(self, key: str, value: Any) -> None:
        self.values[key] = value

    @staticmethod
    def _serialize_state_value(value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, (int, float, str, bool)):
            return value
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return str(value)

    def update_state(self, key: str, value: Any) -> None:
        if self.state.state is None:
            self.state.state = {}
        self.state.state[key] = self._serialize_state_value(value)
        self.namespace[f"state_{key}"] = value

    def flag_error(self, message: str) -> None:
        self.is_error = True
        self.error_message = message


# ---------------------------------------------------------------------------
# Acciones registradas
# ---------------------------------------------------------------------------

@StatefulActionRegistry.register("set_output")
def _action_set_output(ctx: StatefulContext, params: Dict[str, Any]) -> None:
    """Calcula una fórmula y la guarda como salida del handler."""
    formula = params.get("formula", "value")
    output = params.get("output", "value")
    result = ctx.eval(formula)
    ctx.set_output(output, result)
    # Los outputs están disponibles en namespace para pasos posteriores.
    ctx.namespace[output] = result


@StatefulActionRegistry.register("update_state")
def _action_update_state(ctx: StatefulContext, params: Dict[str, Any]) -> None:
    """Calcula una fórmula y la guarda en el estado persistente."""
    key = params.get("key")
    formula = params.get("formula", "value")
    if not key:
        raise ValueError("update_state requiere 'key'")
    ctx.update_state(key, ctx.eval(formula))


@StatefulActionRegistry.register("flag_error")
def _action_flag_error(ctx: StatefulContext, params: Dict[str, Any]) -> None:
    """Marca la lectura como error y opcionalmente detiene el pipeline."""
    message = params.get("message", "Error stateful")
    ctx.flag_error(message)


@StatefulActionRegistry.register("set_metadata")
def _action_set_metadata(ctx: StatefulContext, params: Dict[str, Any]) -> None:
    """Guarda pares clave/valor en metadata del handler (no son salidas)."""
    for key, formula in params.items():
        ctx.metadata[key] = ctx.eval(formula)


@StatefulActionRegistry.register("log_event")
def _action_log_event(ctx: StatefulContext, params: Dict[str, Any]) -> None:
    """Crea un DeviceEvent (mejor esfuerzo; no falla el pipeline)."""
    try:
        DeviceEvent.objects.create(
            device=ctx.raw_reading.device,
            variable=ctx.raw_reading.variable,
            event_type=params.get("event_type", "stateful_event"),
            severity=params.get("severity", "info"),
            timestamp=ctx.raw_reading.timestamp,
            message=params.get("message", ""),
            context=params.get("context", {}),
        )
    except Exception as exc:
        logger.error("[STATEFUL] Error guardando DeviceEvent: %s", exc)


@StatefulActionRegistry.register("log_counter_reset")
def _action_log_counter_reset(ctx: StatefulContext, params: Dict[str, Any]) -> None:
    """Crea un CounterResetLog con los datos del contexto actual.

    Parámetros:
      - reset_type: tipo de reset (ZERO_KEPT, PARTIAL, etc.)
      - last_pulses, current_pulses, pulses_factor
      - addition_before, amount_to_add, addition_after, total_before, total_after
      - is_reconnection, time_diff_hours, days_not_connection
    Si un parámetro es un string, se evalúa como fórmula contra el namespace.
    Las claves faltantes se toman del namespace state_* cuando existen.
    """
    def _resolve(value):
        if isinstance(value, str):
            try:
                return ctx.eval(value)
            except Exception:
                return value
        return value

    try:
        ns = ctx.namespace
        last_pulses = _resolve(params.get("last_pulses", ns.get("state_last_pulses", 0)))
        current_pulses = _resolve(params.get("current_pulses", ns.get("value", 0)))
        pulses_factor = _resolve(params.get("pulses_factor", ns.get("pulses_factor", 1000)))
        addition_before = _resolve(params.get("addition_before", ns.get("state_offset", 0)))
        amount_to_add = _resolve(params.get("amount_to_add"))
        addition_after = _resolve(params.get("addition_after", ns.get("state_offset")))
        total_before = _resolve(params.get("total_before", ns.get("state_last_total")))
        total_after = _resolve(params.get("total_after", ctx.values.get("total")))
        is_reconnection = _resolve(params.get("is_reconnection", bool(ns.get("state_is_reconnection", False))))
        time_diff_hours = _resolve(params.get("time_diff_hours", ns.get("state_time_diff_hours")))
        days_not_connection = _resolve(params.get("days_not_connection", ns.get("state_days_not_connection")))

        CounterResetLog.objects.create(
            device=ctx.raw_reading.device,
            variable=ctx.raw_reading.variable,
            timestamp=ctx.raw_reading.timestamp,
            reset_type=params.get("reset_type", "PARTIAL"),
            last_pulses=last_pulses or 0,
            current_pulses=current_pulses if current_pulses is not None else 0,
            pulses_factor=pulses_factor or 1000,
            addition_before=addition_before,
            amount_to_add=amount_to_add,
            addition_after=addition_after,
            total_before=total_before,
            total_after=total_after,
            is_reconnection=bool(is_reconnection),
            time_diff_hours=time_diff_hours,
            days_not_connection=days_not_connection,
        )
    except Exception as exc:
        logger.error("[STATEFUL] Error guardando CounterResetLog: %s", exc)


@StatefulActionRegistry.register("stop")
def _action_stop(ctx: StatefulContext, params: Dict[str, Any]) -> None:
    """Detiene la ejecución de reglas y steps posteriores."""
    ctx.metadata["_stop_all"] = True


class StatefulRuleHandler(BaseHandler):
    """Ejecuta un schema de pasos stateful con memoria persistente.

    La fuente de verdad del schema es ``config.custom_schema``.  Si no está
    definida, retorna error.
    """

    def process(self, raw_reading: RawReading, config: DeviceVariableConfig) -> HandlerResult:
        schema = config.custom_schema
        if not schema:
            return HandlerResult(
                values={},
                is_error=True,
                error_message="processing_type='stateful' pero no tiene custom_schema asignado.",
            )

        device = raw_reading.device
        variable = raw_reading.source_variable or raw_reading.variable

        with transaction.atomic():
            state, _ = DeviceVariableState.objects.select_for_update().get_or_create(
                device=device,
                variable=variable,
                defaults={"state": {}},
            )

            ctx = StatefulContext(raw_reading, config, state)
            self._run_schema(schema, ctx)

            # Si el schema emitió "total" pero la config indica otro campo de salida
            # explícito, renombramos la clave para que el pipeline la guarde donde corresponda.
            output_field = (config.output_field or "total").strip()
            if output_field and output_field != "total" and "total" in ctx.values:
                ctx.values[output_field] = ctx.values.pop("total")

            state.last_processed_at = timezone.now()
            state.save(update_fields=["state", "last_processed_at"])

        return HandlerResult(
            values=ctx.values,
            metadata=ctx.metadata,
            is_error=ctx.is_error,
            error_message=ctx.error_message,
        )

    def _run_schema(self, schema: ProcessingSchema, ctx: StatefulContext) -> None:
        steps = schema.steps.filter(is_active=True, step_type="stateful").order_by("order")
        for step in steps:
            self._run_step(step, ctx)
            if ctx.is_error or ctx.metadata.get("_stop_all"):
                break

    def _run_step(self, step: ProcessingStep, ctx: StatefulContext) -> None:
        rules = step.rules.filter(is_active=True).order_by("order")
        for rule in rules:
            condition = rule.condition or ""
            if condition:
                try:
                    result = ctx.eval(condition)
                except Exception as exc:
                    logger.warning("[STATEFUL] Condición inválida '%s': %s", condition, exc)
                    continue
                if not result:
                    continue

            try:
                action = StatefulActionRegistry.get(rule.action)
                action(ctx, rule.action_params or {})
            except Exception as exc:
                logger.exception("[STATEFUL] Acción '%s' falló: %s", rule.action, exc)
                ctx.flag_error(f"Acción '{rule.action}' falló: {exc}")

            if ctx.metadata.get("_stop_all") or ctx.is_error:
                break
