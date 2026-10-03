"""
Utilidades puras (sin Django) para calcular la conexión real de un punto.

Contexto (auditoría 30-09-2026):
- Los días sin conexión se calculaban solo con la fecha del TOTALIZADO, aunque
  caudal y nivel llegaran frescos. Un totalizador caído marcaba el punto como
  desconectado (ej. CPP Pozo 4: 160 días con el logger reportando cada hora).
- Si el TOTALIZADO llegaba sin fecha, se usaba la hora de la medición como fecha
  del logger: el punto aparecía con 0 días sin conexión sin haber recibido nada.
- TheThings.io (Nettra) entrega la fecha en UTC ("...Z") y se guardaba como si
  fuera hora de Chile (quedaba 3-4 horas adelantada).
"""

from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Optional

import pytz

CHILE_TZ = pytz.timezone("America/Santiago")
LOGGER_FMT = "%Y-%m-%dT%H:%M:%S"
STALE_VARIABLE_HOURS = 24


def parse_logger_ts(value) -> Optional[datetime]:
    """Convierte una fecha de logger (str o datetime) a datetime naive en hora de Chile."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return value.astimezone(CHILE_TZ).replace(tzinfo=None)
        return value
    text = str(value).strip()
    for fmt in (LOGGER_FMT, "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
        try:
            return datetime.strptime(text[:26], fmt)
        except ValueError:
            continue
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(CHILE_TZ).replace(tzinfo=None)
    return dt


def freshest_logger_ts(values: Iterable) -> Optional[datetime]:
    """Fecha más reciente entre las variables que realmente trajeron fecha."""
    parsed = [p for p in (parse_logger_ts(v) for v in values) if p is not None]
    return max(parsed) if parsed else None


def days_since(logger_dt: Optional[datetime], now: datetime) -> int:
    """Días completos entre la última fecha real del logger y ahora (nunca negativo)."""
    if logger_dt is None:
        return 0
    if now.tzinfo is not None:
        now = now.astimezone(CHILE_TZ).replace(tzinfo=None)
    return max(0, (now - logger_dt).days)


def utc_iso_to_chile_str(value: str) -> Optional[str]:
    """'2026-09-30T17:44:00.000Z' (UTC) -> '2026-09-30T14:44:00' (hora de Chile)."""
    if not value:
        return None
    text = str(value).strip()
    dt = None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            dt = datetime.strptime(text, fmt)
            break
        except ValueError:
            continue
    if dt is None:
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = pytz.utc.localize(dt)
    else:
        dt = pytz.utc.localize(dt)
    return dt.astimezone(CHILE_TZ).strftime(LOGGER_FMT)


def stale_variables(
    variable_ts: Dict[str, Optional[datetime]],
    reference: Optional[datetime],
    hours: int = STALE_VARIABLE_HOURS,
) -> List[str]:
    """Variables cuya fecha quedó atrás de la más fresca por más de `hours` (o sin fecha)."""
    if reference is None:
        return []
    limit = reference - timedelta(hours=hours)
    return [name for name, ts in variable_ts.items() if ts is None or ts < limit]
