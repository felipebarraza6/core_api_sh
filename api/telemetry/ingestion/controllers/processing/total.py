"""Telemetry Total Calculation Utilities."""

from datetime import datetime, timedelta

def total_day(
    current_total: float,
    last_day_total: float,
) -> float:
    """Calculate the total for the day."""
    if last_day_total is None:
        return 0.0
    return current_total - last_day_total

def total_hour(
    current_total: float,
    last_hour_total: float,
) -> float:
    """Calculate the total for the hour."""
    if last_hour_total is None:
        return 0.0
    return current_total - last_hour_total

def total_m3(
    value: float,
    is_liters: bool = False,
) -> float:
    """Convert a value to cubic meters."""
    if is_liters:
        return value / 1000
    return value
