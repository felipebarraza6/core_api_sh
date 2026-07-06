"""Pipeline service for void telemetry processing.

Diseño:
- La fuente de verdad del procesamiento es ``DeviceVariableConfig``:
  cada variable de un logger define su ``processing_type``.
- ``PipelineService`` ejecuta el handler registrado para ese tipo.
- ``ProcessingSchema`` es opcional y se usa solo para filtros,
  transformaciones, validaciones y cálculos adicionales.
"""
import logging
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

from django.db import transaction
from django.utils import timezone

from void.models import (
    Device,
    DeviceVariableConfig,
    ProcessedReading,
    ProcessingSchema,
    RawReading,
)
from void.services.handlers import HandlerRegistry


class _AutomationFlags:
    """Feature flags leídos de settings de forma lazy."""

    @staticmethod
    def pipeline_triggers_compliance() -> bool:
        from django.conf import settings
        return getattr(settings, "VOID_AUTOMATION_ENABLED", False)


logger = logging.getLogger(__name__)


class PipelineService:
    """Orquesta el procesamiento de lecturas crudas."""

    SAFE_FUNCTIONS = {
        "abs": abs,
        "max": max,
        "min": min,
        "round": round,
    }

    HANDLER_STEP_TYPES = {"stateful"}  # Steps reemplazados por handlers

    def process_reading(self, raw_reading: RawReading) -> ProcessedReading:
        """Procesa una lectura cruda usando su handler y schema opcional."""
        device = raw_reading.device

        context = self._build_context(raw_reading, device)
        step_results = dict(context)

        error_message = ""
        is_error = False

        # 1. Handler según DeviceVariableConfig (fuente de verdad)
        variable_config = self._get_or_create_variable_config(raw_reading)
        handler_values: Dict[str, Any] = {}
        if variable_config.processing_type == "none":
            is_error = True
            error_message = (
                f"Variable '{raw_reading.source_variable}' del device {device.id} "
                "no tiene processing_type asignado."
            )
            logger.warning(error_message)
        else:
            try:
                handler = HandlerRegistry.get_handler(variable_config.processing_type)
                result = handler.process(raw_reading, variable_config)
                handler_values = result.values
                step_results.update(handler_values)
                step_results["_handler_metadata"] = result.metadata
                if result.is_error:
                    is_error = True
                    error_message = result.error_message
            except Exception as exc:
                is_error = True
                error_message = f"Handler '{variable_config.processing_type}' failed: {exc}"
                logger.exception(error_message)

        # 2. Schema opcional: filtros/validaciones/transformaciones extra
        schema = None if is_error else self.get_schema_for_device(device)
        if schema:
            steps = schema.steps.filter(is_active=True).order_by("order")
            for step in steps:
                if step.step_type in self.HANDLER_STEP_TYPES:
                    logger.warning(
                        "Step '%s' del schema '%s' es un handler; "
                        "se ignora porque el pipeline ya aplicó el handler de DeviceVariableConfig.",
                        step,
                        schema,
                    )
                    continue
                try:
                    self._apply_step(step, step_results, raw_reading)
                except Exception as exc:
                    is_error = True
                    error_message = f"Step '{step}' failed: {exc}"
                    logger.exception(error_message)
                    break

        processed = self._save_processed(
            raw_reading=raw_reading,
            device=device,
            schema=schema,
            context=step_results,
            handler_values=handler_values,
            is_error=is_error,
            error_message=error_message,
        )

        # 3. Trigger de compliance (solo bajo feature flag).
        if _AutomationFlags.pipeline_triggers_compliance() and not processed.is_error:
            self._submit_to_compliance(processed)

        return processed

    def _submit_to_compliance(self, processed: ProcessedReading) -> None:
        """Envía lectura a todos los perfiles de cumplimiento activos del punto."""
        # Import lazy para evitar circularidad con void.services.compliance.
        from void.services import ComplianceService

        service = ComplianceService()
        profiles = service.get_active_profiles_for_reading(processed)
        for profile in profiles:
            try:
                service.submit_reading(profile, processed, auto_send=True)
            except Exception as exc:
                logger.exception(
                    "Error enviando lectura %s a compliance (profile %s): %s",
                    processed.id, profile.id, exc,
                )

    def _get_or_create_variable_config(
        self, raw_reading: RawReading
    ) -> DeviceVariableConfig:
        """Busca o crea la config de la variable del logger."""
        source = raw_reading.source_variable or raw_reading.variable
        config, created = DeviceVariableConfig.objects.get_or_create(
            device=raw_reading.device,
            source_variable=source,
            defaults={
                "internal_variable": raw_reading.variable,
                "processing_type": "none",
                "is_active": False,
            },
        )
        if created:
            logger.warning(
                "[PIPELINE] Device %s variable '%s' no configurada. "
                "Se creó DeviceVariableConfig inactiva.",
                raw_reading.device.id,
                source,
            )
        return config

    def get_schema_for_device(self, device: Device) -> Optional[ProcessingSchema]:
        """Determina el esquema aplicable a un dispositivo.

        Orden de prioridad:
        1. Esquema cuyo applies_to.devices contenga el ID del device.
        2. Esquema cuyo applies_to.providers contenga el handler del provider.
        3. Esquema cuyo applies_to.point_groups contenga algún grupo del punto.
        """
        schemas = ProcessingSchema.objects.filter(is_active=True)
        for schema in schemas:
            applies_to = schema.applies_to or {}
            device_ids = applies_to.get("devices", [])
            if device_ids and str(device.id) in [str(d) for d in device_ids]:
                return schema

        if device.provider:
            provider_id = str(device.provider.id)
            provider_name = device.provider.name
            for schema in schemas:
                applies_to = schema.applies_to or {}
                providers = applies_to.get("providers", [])
                if provider_id in [str(p) for p in providers]:
                    return schema
                if provider_name in providers:
                    return schema

        point_group_ids = set(device.point.groups.values_list("id", flat=True))
        for schema in schemas:
            applies_to = schema.applies_to or {}
            groups = applies_to.get("point_groups", [])
            if any(int(g) in point_group_ids for g in groups):
                return schema

        return None

    def _build_context(self, raw_reading: RawReading, device: Device) -> Dict[str, Any]:
        """Contexto inicial para el pipeline.

        Incluye valor crudo y config del device. También expone el valor bajo
        el nombre de la variable para que filtros/validaciones sean intuitivos.
        """
        try:
            raw_value = Decimal(raw_reading.raw_value)
        except (InvalidOperation, TypeError):
            raw_value = None

        context = {
            "value": raw_value,
            raw_reading.variable: raw_value,
            "raw_value": raw_reading.raw_value,
            "variable": raw_reading.variable,
            "source_variable": raw_reading.source_variable,
            "timestamp": raw_reading.timestamp,
            "device_config": device.configuration or {},
        }

        # Aplanar configuración del device para usar en fórmulas directamente.
        for key, val in (device.configuration or {}).items():
            if key not in context:
                context[key] = val

        return context

    def _apply_step(
        self,
        step,
        context: Dict[str, Any],
        raw_reading: RawReading,
    ) -> None:
        """Aplica un paso declarativo al contexto."""
        config = step.configuration or {}
        step_type = step.step_type

        if step_type == "filter":
            self._apply_filter(step, config, context)
        elif step_type == "transform":
            self._apply_transform(step, config, context)
        elif step_type == "validate":
            self._apply_validate(step, config, context)
        elif step_type == "calculate":
            self._apply_calculate(step, config, context)
        elif step_type == "aggregate":
            # Placeholder: agregaciones requieren ventana temporal.
            pass
        elif step_type in self.HANDLER_STEP_TYPES:
            # Ya fueron aplicados por el handler antes de llegar aquí.
            pass
        else:
            raise ValueError(f"Tipo de paso desconocido: {step_type}")

    def _apply_filter(self, step, config: Dict[str, Any], context: Dict[str, Any]) -> None:
        variable = config.get("variable", context.get("variable"))
        min_value = config.get("min_value")
        max_value = config.get("max_value")
        action = config.get("action", "drop")

        value = context.get(variable)
        if value is None:
            return

        if (min_value is not None and value < min_value) or (max_value is not None and value > max_value):
            if action == "drop":
                raise ValueError(f"Valor {value} fuera de rango [{min_value}, {max_value}]")

    def _apply_transform(self, step, config: Dict[str, Any], context: Dict[str, Any]) -> None:
        formula = config.get("formula", "value")
        output = config.get("output_variable", step.output_variable or "value")
        result = self._eval_formula(formula, context)
        context[output] = result

    def _apply_validate(self, step, config: Dict[str, Any], context: Dict[str, Any]) -> None:
        condition = config.get("condition", "")
        on_fail = config.get("on_fail", "flag_error")

        if not condition:
            return

        result = self._eval_formula(condition, context)
        if not result:
            if on_fail == "drop":
                raise ValueError(f"Validación fallida: {condition}")
            elif on_fail == "flag_error":
                context["_validation_error"] = f"Validación fallida: {condition}"

    def _apply_calculate(self, step, config: Dict[str, Any], context: Dict[str, Any]) -> None:
        formula = config.get("formula", "")
        output = config.get("output_variable", step.output_variable)
        if not formula or not output:
            return
        context[output] = self._eval_formula(formula, context)

    def _eval_formula(self, formula: str, context: Dict[str, Any]) -> Any:
        """Evalúa una fórmula de forma restringida."""
        safe_context = {
            **self.SAFE_FUNCTIONS,
            **{k: v for k, v in context.items() if not k.startswith("_")},
        }
        code = compile(formula, "<pipeline>", "eval")
        for name in code.co_names:
            if name not in safe_context:
                raise NameError(f"Nombre no permitido en fórmula: {name}")
        return eval(code, {"__builtins__": {}}, safe_context)

    # Campos propios del modelo ProcessedReading; todo lo demás va a extra_values.
    FIXED_FIELDS = {
        "pulses", "total", "flow", "nivel", "water_table",
        "total_diff", "total_today_diff",
    }

    @transaction.atomic
    def _save_processed(
        self,
        raw_reading: RawReading,
        device: Device,
        schema: Optional[ProcessingSchema],
        context: Dict[str, Any],
        handler_values: Dict[str, Any],
        is_error: bool,
        error_message: str,
    ) -> ProcessedReading:
        """Persiste el resultado procesado."""
        def _dec(key: str) -> Optional[Decimal]:
            val = context.get(key)
            if val is None:
                return None
            try:
                return Decimal(str(val))
            except (InvalidOperation, TypeError):
                return None

        def _to_serializable(val: Any) -> Any:
            if isinstance(val, Decimal):
                return str(val)
            if isinstance(val, (int, float, str, bool)) or val is None:
                return val
            return str(val)

        extra_values = {
            key: _to_serializable(val)
            for key, val in handler_values.items()
            if key not in self.FIXED_FIELDS and not key.startswith("_")
        }

        processed, _ = ProcessedReading.objects.update_or_create(
            device=device,
            variable=raw_reading.variable,
            timestamp=raw_reading.timestamp,
            defaults={
                "raw_reading": raw_reading,
                "pulses": context.get("pulses") if isinstance(context.get("pulses"), int) else None,
                "total": _dec("total"),
                "flow": _dec("flow"),
                "nivel": _dec("nivel"),
                "water_table": _dec("water_table"),
                "total_diff": _dec("total_diff"),
                "total_today_diff": _dec("total_today_diff"),
                "extra_values": extra_values,
                "is_reset": bool(context.get("_handler_metadata", {}).get("is_reset", False)),
                "is_reconnection": bool(context.get("_handler_metadata", {}).get("is_reconnection", False)),
                "is_interpolated": bool(context.get("is_interpolated", False)),
                "is_error": is_error or bool(context.get("_validation_error")),
                "error_message": error_message or context.get("_validation_error", ""),
                "processing_schema": schema,
                "processed_at": timezone.now(),
                "processor_version": "void.pipeline.v2",
            },
        )
        return processed

    def process_device_variable(
        self,
        device: Device,
        variable: str,
        since: Optional[timezone.datetime] = None,
        until: Optional[timezone.datetime] = None,
    ) -> List[ProcessedReading]:
        """Procesa lecturas crudas pendientes de una variable interna."""
        qs = device.raw_readings.filter(variable=variable)
        if since:
            qs = qs.filter(timestamp__gte=since)
        if until:
            qs = qs.filter(timestamp__lte=until)

        results = []
        # Orden estable por timestamp + id para evitar falsos resets parciales
        # cuando hay múltiples lecturas con el mismo timestamp.
        for raw in qs.order_by("timestamp", "id"):
            try:
                results.append(self.process_reading(raw))
            except Exception as exc:
                logger.exception("Error procesando lectura %s: %s", raw.id, exc)
        return results
