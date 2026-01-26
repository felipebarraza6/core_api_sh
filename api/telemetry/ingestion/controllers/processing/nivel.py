# -*- coding: utf-8 -*-
"""
Processing for NIVEL variable.
Extracted from unified_processing.py for modularity.
"""

from typing import Any, Dict
from .utils import telemetry_logger, log_variable_processing
from api.telemetry.models import TelemetryRecord

def nivel_mt(
    value: float,
    d3: float,
    is_inverse: bool = False,
) -> float:
    """
    Calculate the nivel in meters.
    """
    if is_inverse:
        return d3 - value
    return value

def water_table(
    nivel: float,
    d3: float,
) -> float:
    """
    Calculate the water table.
    """
    return d3 - nivel

def process_nivel_variable(
    data: Dict[str, Any],
    variable: Dict[str, Any],
    point_catchment: Dict[str, Any],
    created_register: Dict[str, Any],
) -> Dict[str, Any]:
    """Process variable of type NIVEL."""
    # Handle negative level
    try:
        nivel_value = float(data["value"])
    except (ValueError, TypeError):
        nivel_value = 0

    if nivel_value < 0:
        last_valid = (
            TelemetryRecord.objects.filter(point_id=point_catchment["id"])
            .order_by("-timestamp")
            .first()
        )
        if last_valid and "level" in last_valid.data:
            nivel_value = float(last_valid.data["level"])
            telemetry_logger.info(
                f"Nivel negativo corregido usando último valor V3: {nivel_value}"
            )
        else:
            nivel_value = 0

    # Prioritize d3 from variable, fallback to global profile
    config = variable.get("configuration", {})
    d3 = config.get("d3")
    if d3 is None:
        d3 = point_catchment["profile_data_config"].get("d3", 0)

    created_register["nivel"] = nivel_mt(
        nivel_value,
        variable.get("calculate_nivel"),
        point_catchment["id"],
        d3,
    )

    # Validate d3 before calculating water table
    if not d3 or float(d3 if d3 else 0) <= 0:
        telemetry_logger.warning(
            f"Error: d3 no válido para punto {point_catchment['id']}"
        )
        d3 = 0

    created_register["water_table"] = water_table(created_register["nivel"], d3)
    created_register["date_time_last_logger"] = data["date_time"]

    from .utils import log_variable_processing
    log_variable_processing(
        point_catchment["id"], variable.get("str_variable"), "NIVEL", True
    )

    return created_register
