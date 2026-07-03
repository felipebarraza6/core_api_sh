"""
Utilidad para calcular deadlines dentro de horario hábil.
Horario hábil: lunes a viernes, 09:00 a 18:00.
"""

from datetime import timedelta


BUSINESS_START_HOUR = 9
BUSINESS_END_HOUR = 18


def _is_business_day(dt):
    """Retorna True si dt es día hábil (lunes-viernes)."""
    return dt.weekday() < 5


def _next_business_day_start(dt):
    """Avanza al inicio del siguiente día hábil."""
    dt = dt + timedelta(days=1)
    dt = dt.replace(hour=BUSINESS_START_HOUR, minute=0, second=0, microsecond=0)
    while not _is_business_day(dt):
        dt = dt + timedelta(days=1)
    return dt


def add_business_hours(start_dt, hours):
    """
    Suma `hours` horas hábiles a `start_dt`.
    Horario hábil: L-V 09:00-18:00.
    Si start_dt está fuera de horario hábil, se ajusta al inicio del siguiente día hábil.
    """
    if hours <= 0:
        return start_dt

    current = start_dt

    # Ajustar si está fuera de horario hábil
    if not _is_business_day(current):
        current = _next_business_day_start(current)
    elif current.hour < BUSINESS_START_HOUR:
        current = current.replace(
            hour=BUSINESS_START_HOUR, minute=0, second=0, microsecond=0
        )
    elif current.hour >= BUSINESS_END_HOUR:
        current = _next_business_day_start(current)

    remaining = timedelta(hours=hours)

    while remaining > timedelta(0):
        end_of_day = current.replace(
            hour=BUSINESS_END_HOUR, minute=0, second=0, microsecond=0
        )
        available_today = end_of_day - current

        if remaining <= available_today:
            return current + remaining

        remaining -= available_today
        current = _next_business_day_start(current)

    return current
