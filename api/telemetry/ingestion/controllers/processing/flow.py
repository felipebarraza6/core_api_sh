"""Telemetry Flow Calculation Utilities."""

from datetime import datetime, timedelta

def instantaneous_flow(
    value: float,
    last_value: float,
    current_timestamp: datetime,
    last_timestamp: datetime,
    is_totalized: bool = False,
) -> float:
    """
    Calculate instantaneous flow in L/s.
    Handles both direct flow values and totalized inputs.
    """
    if not is_totalized:
        return value

    if not all([last_value, last_timestamp]):
        return 0.0

    time_diff_seconds = (current_timestamp - last_timestamp).total_seconds()
    if time_diff_seconds <= 0:
        return 0.0

    value_diff = value - last_value
    if value_diff < 0:
        return 0.0

    # Convert from m³/hr to L/s
    flow_m3_per_second = value_diff / time_diff_seconds
    return flow_m3_per_second * (1000 / 3600)
