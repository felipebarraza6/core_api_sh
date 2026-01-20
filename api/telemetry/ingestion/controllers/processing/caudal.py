# -*- coding: utf-8 -*-
"""
Processing for CAUDAL and CAUDAL_PROMEDIO variables.
Extracted from unified_processing.py for modularity.
"""

from typing import Any, Dict
from .utils import telemetry_logger, log_variable_processing
from .flow import instantaneous_flow

def process_caudal_variable(
    data: Dict[str, Any],
    variable: Dict[str, Any],
    point_catchment: Dict[str, Any],
    created_register: Dict[str, Any],
) -> Dict[str, Any]:
    """Process variable of type CAUDAL (instantaneous)."""
    created_register["flow"] = instantaneous_flow(
        data["value"], variable.get("convert_to_lt"), variable.get("calculate_nivel")
    )
    created_register["date_time_last_logger"] = data["date_time"]

    log_variable_processing(
        point_catchment["id"], variable.get("str_variable"), "CAUDAL", True
    )

    return created_register

def process_caudal_promedio_variable(
    date_time_last_logger_total: str,
    created_register: Dict[str, Any],
    point_catchment: Dict[str, Any],
) -> Dict[str, Any]:
    """Process variable of type CAUDAL_PROMEDIO (calculated dynamically)."""
    log_variable_processing(
        point_catchment["id"],
        "CAUDAL_PROMEDIO",
        "CAUDAL_PROMEDIO",
        True,
    )
    return created_register
