"""Plantillas stateful reutilizables para void.

Toda la lógica de negocio (totalizador, nivel, etc.) se expresa como
``ProcessingSchema`` + ``ProcessingStep`` + ``ProcessingRule``.
No hay handlers mágicos: el motor ``StatefulRuleHandler`` ejecuta estas
reglas contra el namespace del contexto.
"""
from typing import Optional

from void.models import DeviceVariableConfig, ProcessingRule, ProcessingSchema, ProcessingStep


CURRENT_TOTALIZER_VERSION = "1.5"
CURRENT_NIVEL_VERSION = "1.1"


def _schema_template(name: str, version: str, description: str) -> ProcessingSchema:
    """Obtiene o crea un schema marcado como plantilla."""
    schema, created = ProcessingSchema.objects.get_or_create(
        name=name,
        is_template=True,
        defaults={
            "version": version,
            "description": description,
            "is_active": True,
        },
    )
    needs_rebuild = created or (schema.version or "") < version
    if not needs_rebuild:
        return schema
    if not created:
        schema.steps.all().delete()
    return schema


def _step(schema: ProcessingSchema, order: int, name: str) -> ProcessingStep:
    return ProcessingStep.objects.create(
        schema=schema,
        order=order,
        step_type="stateful",
        name=name,
    )


def _rule(step: ProcessingStep, order: int, action: str, action_params: dict, condition: str = "") -> ProcessingRule:
    return ProcessingRule.objects.create(
        step=step,
        order=order,
        condition=condition,
        action=action,
        action_params=action_params,
    )


# -----------------------------------------------------------------------------
# Totalizador
# -----------------------------------------------------------------------------

def create_totalizer_schema(name: str = "Totalizador stateful v1") -> ProcessingSchema:
    """Plantilla de totalizador robusto: paridad con legacy ``controllers/total``."""
    schema = _schema_template(
        name=name,
        version=CURRENT_TOTALIZER_VERSION,
        description="Totalizador monotónico con detección de resets, reconexiones y caudal derivado.",
    )
    if schema.version == CURRENT_TOTALIZER_VERSION and schema.steps.exists():
        return schema

    _build_totalizer_steps(schema)
    schema.version = CURRENT_TOTALIZER_VERSION
    schema.save(update_fields=["version"])
    return schema


def _build_totalizer_steps(schema: ProcessingSchema) -> None:
    # -------------------------------------------------------------------------
    # Paso 0: contexto
    # -------------------------------------------------------------------------
    step_ctx = _step(schema, 0, "Contexto")
    _rule(step_ctx, 0, "update_state", {"key": "raw_m3", "formula": "value * pulses_factor / 1000"})
    _rule(
        step_ctx,
        1,
        "update_state",
        {
            "key": "time_diff_hours_real",
            "formula": (
                "1 if state_last_timestamp is None else "
                "max(Decimal(total_seconds(timestamp - state_last_timestamp)) / Decimal(3600), Decimal('0.1'))"
            ),
        },
    )
    # La reconexión se decide con el tiempo real, no con el ajustado.
    _rule(
        step_ctx,
        2,
        "update_state",
        {"key": "is_reconnection", "formula": "state_time_diff_hours_real > reconnection_threshold_hours"},
        condition="state_last_timestamp is not None",
    )
    _rule(
        step_ctx,
        3,
        "set_metadata",
        {"is_reconnection": "state_time_diff_hours_real > reconnection_threshold_hours"},
        condition="state_last_timestamp is not None",
    )
    _rule(
        step_ctx,
        4,
        "update_state",
        {"key": "is_reconnection", "formula": "False"},
        condition="state_last_timestamp is None",
    )
    _rule(
        step_ctx,
        5,
        "set_metadata",
        {"is_reconnection": "False"},
        condition="state_last_timestamp is None",
    )
    # Ajustar time_diff por frecuencia esperada (anti-salto artificial).
    _rule(
        step_ctx,
        6,
        "update_state",
        {
            "key": "time_diff_hours",
            "formula": (
                "state_time_diff_hours_real if frequency_minutes is None else "
                "(Decimal(frequency_minutes) / Decimal(60) "
                "if state_time_diff_hours_real > (Decimal(frequency_minutes) / Decimal(60)) * Decimal(3) "
                "else state_time_diff_hours_real)"
            ),
        },
        condition="state_last_timestamp is not None and frequency_minutes is not None",
    )
    _rule(
        step_ctx,
        7,
        "update_state",
        {"key": "time_diff_hours", "formula": "state_time_diff_hours_real"},
        condition="state_last_timestamp is not None and frequency_minutes is None",
    )
    _rule(
        step_ctx,
        7,
        "update_state",
        {"key": "current_date", "formula": "to_date(timestamp)"},
    )
    _rule(
        step_ctx,
        8,
        "update_state",
        {"key": "offset", "formula": "offset"},
        condition="state_last_timestamp is None",
    )

    # -------------------------------------------------------------------------
    # Paso 1: pulsos negativos
    # -------------------------------------------------------------------------
    step_neg = _step(schema, 1, "Pulsos negativos")
    _rule(
        step_neg,
        0,
        "set_output",
        {"output": "total", "formula": "state_last_total or 0"},
        condition="value < 0",
    )
    _rule(
        step_neg,
        1,
        "log_counter_reset",
        {
            "reset_type": "NEGATIVE_PULSES",
            "current_pulses": "value",
            "total_after": "state_last_total or 0",
        },
        condition="value < 0",
    )
    _rule(
        step_neg,
        2,
        "flag_error",
        {"message": "Pulsos negativos"},
        condition="value < 0",
    )
    _rule(
        step_neg,
        3,
        "log_event",
        {
            "event_type": "negative_pulses",
            "severity": "warning",
            "message": "Pulsos negativos detectados; se mantiene último total.",
        },
        condition="value < 0",
    )
    _rule(step_neg, 4, "stop", {}, condition="value < 0")

    # -------------------------------------------------------------------------
    # Paso 2: pulsos = 0 con histórico
    # -------------------------------------------------------------------------
    step_zero = _step(schema, 2, "Pulsos en cero")
    _rule(
        step_zero,
        0,
        "set_output",
        {"output": "total", "formula": "state_last_total"},
        condition="value == 0 and (state_last_pulses or 0) > 0",
    )
    _rule(
        step_zero,
        1,
        "log_counter_reset",
        {
            "reset_type": "ZERO_KEPT",
            "current_pulses": 0,
            "total_before": "state_last_total",
            "total_after": "state_last_total",
        },
        condition="value == 0 and (state_last_pulses or 0) > 0",
    )
    _rule(
        step_zero,
        2,
        "log_event",
        {
            "event_type": "zero_kept",
            "severity": "info",
            "message": "Pulsos en cero con histórico; total preservado.",
        },
        condition="value == 0 and (state_last_pulses or 0) > 0",
    )
    _rule(
        step_zero,
        3,
        "stop",
        {},
        condition="value == 0 and (state_last_pulses or 0) > 0",
    )

    # -------------------------------------------------------------------------
    # Paso 3: detección de reset
    # -------------------------------------------------------------------------
    step_reset = _step(schema, 3, "Detección de reset")
    # Ruido (< 1% de caída): mantener total.
    _rule(
        step_reset,
        0,
        "set_output",
        {"output": "total", "formula": "state_last_total"},
        condition=(
            "(state_last_pulses or 0) > 0 and value > 0 and value < state_last_pulses and "
            "(1 - (value / state_last_pulses)) < Decimal('0.01')"
        ),
    )
    _rule(
        step_reset,
        1,
        "log_counter_reset",
        {
            "reset_type": "NOISE_DROP",
            "last_pulses": "state_last_pulses",
            "current_pulses": "value",
            "total_before": "state_last_total",
            "total_after": "state_last_total",
        },
        condition=(
            "(state_last_pulses or 0) > 0 and value > 0 and value < state_last_pulses and "
            "(1 - (value / state_last_pulses)) < Decimal('0.01')"
        ),
    )
    _rule(
        step_reset,
        2,
        "stop",
        {},
        condition=(
            "(state_last_pulses or 0) > 0 and value > 0 and value < state_last_pulses and "
            "(1 - (value / state_last_pulses)) < Decimal('0.01')"
        ),
    )
    # Caída > 90% sin reconexión: rechazar y mantener total.
    _rule(
        step_reset,
        3,
        "set_output",
        {"output": "total", "formula": "state_last_total"},
        condition=(
            "not state_is_reconnection and (state_last_pulses or 0) > 0 and value > 0 and "
            "value < state_last_pulses and (1 - (value / state_last_pulses)) > Decimal('0.90')"
        ),
    )
    _rule(
        step_reset,
        4,
        "log_counter_reset",
        {
            "reset_type": "PARTIAL_REJECTED",
            "last_pulses": "state_last_pulses",
            "current_pulses": "value",
            "total_before": "state_last_total",
            "total_after": "state_last_total",
            "is_reconnection": "False",
        },
        condition=(
            "not state_is_reconnection and (state_last_pulses or 0) > 0 and value > 0 and "
            "value < state_last_pulses and (1 - (value / state_last_pulses)) > Decimal('0.90')"
        ),
    )
    _rule(
        step_reset,
        5,
        "stop",
        {},
        condition=(
            "not state_is_reconnection and (state_last_pulses or 0) > 0 and value > 0 and "
            "value < state_last_pulses and (1 - (value / state_last_pulses)) > Decimal('0.90')"
        ),
    )
    # Reset real parcial: compensar offset.
    _rule(
        step_reset,
        6,
        "update_state",
        {"key": "addition_before", "formula": "state_offset or 0"},
        condition="(state_last_pulses or 0) > 0 and value > 0 and value < state_last_pulses",
    )
    _rule(
        step_reset,
        7,
        "update_state",
        {"key": "offset", "formula": "(state_offset or 0) + (state_last_pulses * pulses_factor / 1000)"},
        condition="(state_last_pulses or 0) > 0 and value > 0 and value < state_last_pulses",
    )
    _rule(
        step_reset,
        8,
        "set_metadata",
        {"is_reset": "True"},
        condition="(state_last_pulses or 0) > 0 and value > 0 and value < state_last_pulses",
    )
    _rule(
        step_reset,
        9,
        "log_counter_reset",
        {
            "reset_type": "PARTIAL",
            "amount_to_add": "state_last_pulses * pulses_factor / 1000",
            "addition_before": "state_addition_before",
            "addition_after": "state_offset",
            "total_before": "state_last_total",
            "total_after": "state_raw_m3 + state_offset",
        },
        condition="(state_last_pulses or 0) > 0 and value > 0 and value < state_last_pulses",
    )
    _rule(
        step_reset,
        10,
        "log_event",
        {
            "event_type": "counter_reset",
            "severity": "critical",
            "message": "Reset parcial compensado con offset.",
        },
        condition="(state_last_pulses or 0) > 0 and value > 0 and value < state_last_pulses",
    )

    # -------------------------------------------------------------------------
    # Paso 4: salto masivo
    # -------------------------------------------------------------------------
    step_jump = _step(schema, 4, "Salto masivo")
    _rule(
        step_jump,
        0,
        "log_event",
        {
            "event_type": "massive_jump",
            "severity": "warning",
            "message": "Salto masivo detectado; se acepta el nuevo total.",
        },
        condition=(
            "state_last_total is not None and state_time_diff_hours > 0 and "
            "(state_raw_m3 + (state_offset or 0) - state_last_total) > "
            "(max_diff_m3_per_hour * state_time_diff_hours)"
        ),
    )

    # -------------------------------------------------------------------------
    # Paso 5: cálculo total
    # -------------------------------------------------------------------------
    step_calc = _step(schema, 5, "Cálculo total")
    _rule(step_calc, 0, "set_output", {"output": "total", "formula": "max(state_raw_m3 + (state_offset or 0), 0)"})
    _rule(step_calc, 1, "set_output", {"output": "pulses", "formula": "int(value)"})

    # -------------------------------------------------------------------------
    # Paso 6: diffs y baseline diario
    # -------------------------------------------------------------------------
    step_diff = _step(schema, 6, "Diffs y caudal")
    # previous_total = last_total o total actual (primera lectura)
    _rule(
        step_diff,
        0,
        "update_state",
        {"key": "previous_total", "formula": "state_last_total if state_last_total is not None else total"},
    )
    # total_diff = max(total - previous_total, 0)
    _rule(
        step_diff,
        1,
        "set_output",
        {"output": "total_diff", "formula": "max(total - (state_previous_total or total), 0)"},
    )
    # Cambio de día: actualizar baseline
    _rule(
        step_diff,
        2,
        "update_state",
        {
            "key": "daily_baseline_total",
            "formula": "state_last_total if state_last_total is not None else total",
        },
        condition="state_daily_baseline_date != state_current_date",
    )
    _rule(
        step_diff,
        3,
        "update_state",
        {"key": "daily_baseline_date", "formula": "state_current_date"},
        condition="state_daily_baseline_date != state_current_date",
    )
    # total_today_diff
    _rule(
        step_diff,
        4,
        "set_output",
        {"output": "total_today_diff", "formula": "max(total - (state_daily_baseline_total or total), 0)"},
    )

    # -------------------------------------------------------------------------
    # Paso 7: actualizar estado
    # -------------------------------------------------------------------------
    step_state = _step(schema, 7, "Actualizar estado")
    _rule(step_state, 0, "update_state", {"key": "last_pulses", "formula": "value"})
    _rule(step_state, 1, "update_state", {"key": "last_total", "formula": "total"})
    _rule(step_state, 2, "update_state", {"key": "last_timestamp", "formula": "timestamp"})

    # -------------------------------------------------------------------------
    # Paso 8: caudal derivado
    # -------------------------------------------------------------------------
    step_flow = _step(schema, 8, "Caudal derivado")
    _rule(
        step_flow,
        0,
        "set_output",
        {
            "output": "flow",
            "formula": (
                "max((total - state_previous_total) / (state_time_diff_hours * Decimal(3600)) * Decimal(1000), Decimal(0))"
            ),
        },
        condition=(
            "compute_flow and state_previous_total is not None and "
            "state_time_diff_hours is not None and state_time_diff_hours > 0"
        ),
    )
    _rule(
        step_flow,
        1,
        "set_output",
        {"output": "flow", "formula": "Decimal(0)"},
        condition=(
            "compute_flow and (state_previous_total is None or "
            "state_time_diff_hours is None or state_time_diff_hours <= 0)"
        ),
    )


def apply_totalizer_schema(
    device,
    source_variable: str,
    internal_variable: str = "pulses",
    output_field: str = "total",
    pulses_factor: int = 1000,
    max_diff_m3_per_hour: Optional[float] = 500,
    reconnection_threshold_hours: Optional[float] = 2,
    compute_flow: bool = False,
) -> DeviceVariableConfig:
    """Asigna la plantilla stateful del totalizador a una variable."""
    schema = create_totalizer_schema()
    config, _ = DeviceVariableConfig.objects.update_or_create(
        device=device,
        source_variable=source_variable,
        defaults={
            "internal_variable": internal_variable,
            "output_field": output_field,
            "processing_type": "stateful",
            "custom_schema": schema,
            "pulses_factor": pulses_factor,
            "max_diff_m3_per_hour": max_diff_m3_per_hour,
            "reconnection_threshold_hours": reconnection_threshold_hours,
            "compute_flow": compute_flow,
        },
    )
    return config


# -----------------------------------------------------------------------------
# Nivel
# -----------------------------------------------------------------------------

def create_nivel_schema(name: str = "Nivel stateful v1") -> ProcessingSchema:
    """Plantilla de nivel: corrige negativos con histórico y calcula freático."""
    schema = _schema_template(
        name=name,
        version=CURRENT_NIVEL_VERSION,
        description="Nivel con corrección de lecturas negativas usando histórico y cálculo de nivel freático.",
    )
    if schema.version == CURRENT_NIVEL_VERSION and schema.steps.exists():
        return schema

    _build_nivel_steps(schema)
    schema.version = CURRENT_NIVEL_VERSION
    schema.save(update_fields=["version"])
    return schema


def _build_nivel_steps(schema: ProcessingSchema) -> None:
    # -------------------------------------------------------------------------
    # Paso 0: corregir valor negativo
    # -------------------------------------------------------------------------
    step_correct = _step(schema, 0, "Corrección negativo")
    _rule(
        step_correct,
        0,
        "set_output",
        {"output": "nivel_corrected", "formula": "True"},
        condition="value < 0 and state_highest_nivel is not None",
    )
    _rule(
        step_correct,
        1,
        "update_state",
        {"key": "corrected_value", "formula": "state_highest_nivel"},
        condition="value < 0 and state_highest_nivel is not None",
    )
    _rule(
        step_correct,
        2,
        "set_output",
        {"output": "nivel_corrected", "formula": "True"},
        condition="value < 0 and state_highest_nivel is None",
    )
    _rule(
        step_correct,
        3,
        "update_state",
        {"key": "corrected_value", "formula": "0"},
        condition="value < 0 and state_highest_nivel is None",
    )
    _rule(
        step_correct,
        4,
        "set_output",
        {"output": "nivel_corrected", "formula": "False"},
        condition="value >= 0",
    )
    _rule(
        step_correct,
        5,
        "update_state",
        {"key": "corrected_value", "formula": "value"},
        condition="value >= 0",
    )

    # -------------------------------------------------------------------------
    # Paso 1: calcular nivel
    # -------------------------------------------------------------------------
    step_calc = _step(schema, 1, "Cálculo nivel")
    _rule(
        step_calc,
        0,
        "set_output",
        {
            "output": "nivel",
            "formula": (
                "0 if calculate_nivel == 0 else "
                "max((state_corrected_value + offset) / calculate_nivel, 0)"
            ),
        },
    )

    # -------------------------------------------------------------------------
    # Paso 2: actualizar histórico más alto
    # -------------------------------------------------------------------------
    step_hist = _step(schema, 2, "Actualizar histórico")
    _rule(
        step_hist,
        0,
        "update_state",
        {"key": "highest_nivel", "formula": "nivel"},
        condition="state_highest_nivel is None",
    )
    _rule(
        step_hist,
        1,
        "update_state",
        {"key": "highest_nivel", "formula": "max(state_highest_nivel, nivel)"},
        condition="state_highest_nivel is not None",
    )

    # -------------------------------------------------------------------------
    # Paso 3: calcular nivel freático
    # -------------------------------------------------------------------------
    step_wt = _step(schema, 3, "Nivel freático")
    _rule(
        step_wt,
        0,
        "set_output",
        {"output": "water_table", "formula": "0 if (d3 is None or d3 <= 0) else max(d3 - nivel, 0)"},
    )


def apply_nivel_schema(
    device,
    source_variable: str,
    internal_variable: str = "nivel",
    output_field: str = "nivel",
    offset: float = 0,
    calculate_nivel: int = 1,
    d3: Optional[float] = None,
) -> DeviceVariableConfig:
    """Asigna la plantilla stateful de nivel a una variable."""
    schema = create_nivel_schema()
    extra = {"calculate_nivel": calculate_nivel}
    if d3 is not None:
        extra["d3"] = d3

    config, _ = DeviceVariableConfig.objects.update_or_create(
        device=device,
        source_variable=source_variable,
        defaults={
            "internal_variable": internal_variable,
            "output_field": output_field,
            "processing_type": "stateful",
            "custom_schema": schema,
            "offset": offset,
            "scale": 1,
            "extra_data": extra,
        },
    )
    return config
