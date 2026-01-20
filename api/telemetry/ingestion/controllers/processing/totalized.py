"""Processing functions for totalizado (pulse) variables.

This module contains the logic previously located in `unified_processing.py` under
`process_totalizado_variable`. It has been extracted to improve modularity and
testability.
"""

from datetime import datetime
import logging
from typing import Any, Dict, Tuple

from .utils import chile_tz, telemetry_logger, calculate_days_not_connection, log_variable_processing
from .total import total_day, total_hour, total_m3


def process_totalizado_variable(
    data: Dict[str, Any],
    variable: Dict[str, Any],
    point_catchment: Dict[str, Any],
    created_register: Dict[str, Any],
) -> Tuple[str, Dict[str, Any]]:
    """Process a TOTALIZADO (pulse) variable.

    Args:
        data: Raw data from the provider API.
        variable: Variable configuration from the DB.
        point_catchment: Point configuration.
        created_register: Dictionary being built for the telemetry record.

    Returns:
        A tuple ``(date_time_last_logger_total, created_register)`` where the
        first element is the timestamp of the last logger entry and the second
        element is the updated register dictionary.
    """
    # 1. Validate and convert pulse value
    try:
        value = int(float(data.get("value", 0)))
    except (ValueError, TypeError) as e:
        telemetry_logger.warning(
            f"Error convirtiendo valor {data.get('value')}: {e}"
        )
        value = 0

    # 2. Assign pulses to register
    created_register["pulses"] = value

    # 3. Calculate total using unified formula (pulses × factor) ÷ 1000
    pulses_factor = variable.get("pulses_factor", 1000)
    if not pulses_factor or pulses_factor <= 0:
        telemetry_logger.warning(
            f"Factor de pulsos no válido: {pulses_factor}, usando 1000"
        )
        pulses_factor = 1000

    total_calculado = total_m3(pulses_factor, value, point_catchment)
    created_register["total"] = total_calculado

    # 4. Hourly difference (consumption)
    current_dt = (
        datetime.strptime(data["date_time"], "%Y-%m-%dT%H:%M:%S")
        if data.get("date_time")
        else datetime.now()
    )
    total_diff = total_hour(created_register["total"], point_catchment, current_dt)
    created_register["total_diff"] = total_diff

    # 5. Daily accumulated total (corrected to use total, not diff)
    total_today_diff = total_day(point_catchment, current_dt, created_register["total"])
    created_register["total_today_diff"] = total_today_diff

    # 6. Assign timestamp of last logger
    if data.get("date_time"):
        created_register["date_time_last_logger"] = data["date_time"]
        date_time_last_logger_total = data["date_time"]
    else:
        # Fallback: use measurement timestamp if logger does not provide one
        created_register["date_time_last_logger"] = created_register["date_time_medition"]
        date_time_last_logger_total = created_register["date_time_last_logger"]

    # 7. Calculate days without connection
    created_register = calculate_days_not_connection(
        created_register, chile_tz, point_catchment
    )

    # 8. Success logging
    telemetry_logger.info(
        f"Punto {point_catchment['id']} - TOTALIZADO "
        f"'{variable.get('str_variable')}' procesado: "
        f"pulsos={value}, factor={pulses_factor}, "
        f"total={total_calculado}, diff_hora={total_diff}, "
        f"diff_dia={total_today_diff}"
    )

    return date_time_last_logger_total, created_register
