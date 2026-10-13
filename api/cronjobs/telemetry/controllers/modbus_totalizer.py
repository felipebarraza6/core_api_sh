"""
Totalizador Modbus de dos registros (LO 16-bit + HI multiplicador).
====================================================================

Dispositivos Modbus suelen exponer el acumulado en:
- Registro LO (ej. 5001): contador 16-bit que vuelve a 0 al alcanzar el módulo.
- Registro HI (ej. 5002): cuenta cuántas veces hizo rollover el LO.

Acumulado bruto = HI * 65536 + LO

El wrap puede ocurrir en 65535→0 (uint16) o, en algunos equipos, al llegar a
65536. Ambas se normalizan de forma segura.

Cuando HI y LO llegan desfasados (mid-rollover), el valor combinado naive
puede bajar o saltar ~65536. Este módulo solo corrige esos bordes cuando el
patrón es inequívoco (LO previo cerca del tope + LO nuevo cerca de 0, o HI
adelantado con LO aún alto). Cualquier otra regresión se sostiene; avances
grandes con HI/LO coherentes se aceptan (huecos largos).
"""

from __future__ import annotations

from typing import Any, Optional, Tuple

# Módulo del contador LO. uint16 wrapa en 65535→0; la base aritmética es 65536.
MODBUS_UINT16_MODULUS = 65536

# Umbrales conservadores para detectar wrap real vs ruido de LO.
# Solo se aplica corrección LO-ahead si el LO previo estaba en el tramo alto
# y el nuevo en el tramo bajo (wrap 65535→0 típico).
LO_NEAR_TOP_RATIO = 0.90
LO_NEAR_ZERO_RATIO = 0.10

# Tipos semánticos reconocidos (Variable.type_variable, free string).
TYPE_MODBUS_LO = "TOTALIZADO_MODBUS_LO"
TYPE_MODBUS_HI = "TOTALIZADO_MODBUS_HI"
# Alias del LO: permite un solo nombre "primario" en configs simples.
TYPE_MODBUS_PRIMARY = "TOTALIZADO_MODBUS"

MODBUS_LO_TYPES = frozenset({TYPE_MODBUS_LO, TYPE_MODBUS_PRIMARY})
MODBUS_HI_TYPES = frozenset({TYPE_MODBUS_HI})
MODBUS_TOTALIZER_TYPES = MODBUS_LO_TYPES | MODBUS_HI_TYPES

# Tipos que alimentan pulses/total (TOTALIZADO clásico + LO Modbus).
TOTALIZADO_PRIMARY_TYPES = frozenset({"TOTALIZADO"}) | MODBUS_LO_TYPES


def is_modbus_totalizer_type(type_variable: Optional[str]) -> bool:
    """True si el type_variable es parte del par Modbus HI/LO."""
    if not type_variable:
        return False
    return type_variable.upper() in MODBUS_TOTALIZER_TYPES


def is_modbus_lo_type(type_variable: Optional[str]) -> bool:
    if not type_variable:
        return False
    return type_variable.upper() in MODBUS_LO_TYPES


def is_modbus_hi_type(type_variable: Optional[str]) -> bool:
    if not type_variable:
        return False
    return type_variable.upper() in MODBUS_HI_TYPES


def is_totalizado_primary_type(type_variable: Optional[str]) -> bool:
    """
    True si el tipo es el que escribe pulses/total (TOTALIZADO o LO Modbus).
    Usado para prioridad de sort, is_error de getter y validación de rango.
    """
    if not type_variable:
        return False
    return type_variable.upper() in TOTALIZADO_PRIMARY_TYPES


def last_record_used_modbus(variable_details: Any) -> bool:
    """
    True si el InteractionDetail previo ya fue producido con el par Modbus.

    Sirve para no usar pulses de un TOTALIZADO clásico como baseline de
    mid-rollover al migrar un punto (ej. 152).
    """
    if not variable_details:
        return False
    if isinstance(variable_details, dict):
        items = variable_details.get("variables") or variable_details.get("items") or []
        if not items and any(
            is_modbus_totalizer_type(k) for k in variable_details.keys()
        ):
            return True
    elif isinstance(variable_details, list):
        items = variable_details
    else:
        return False

    for item in items:
        if not isinstance(item, dict):
            continue
        if is_modbus_totalizer_type(item.get("type_variable")):
            return True
    return False


def normalize_lo_register(
    lo: Any, modulus: int = MODBUS_UINT16_MODULUS
) -> Tuple[int, int]:
    """
    Normaliza el registro LO al rango [0, modulus).

    Returns:
        (lo_normalizado, hi_extra) donde hi_extra es 1 si el dispositivo
        reportó LO >= modulus (conteo inclusivo hasta 65536 u overflow).
    """
    try:
        lo_int = int(float(lo))
    except (TypeError, ValueError):
        return 0, 0

    if lo_int < 0:
        return 0, 0

    if lo_int < modulus:
        return lo_int, 0

    # LO == 65536 (o mayor): wrap inclusivo / overflow — aportar a HI.
    hi_extra = lo_int // modulus
    return lo_int % modulus, hi_extra


def combine_raw(hi: Any, lo: Any, modulus: int = MODBUS_UINT16_MODULUS) -> int:
    """Combina HI/LO sin corrección de mid-rollover."""
    try:
        hi_int = int(float(hi))
    except (TypeError, ValueError):
        hi_int = 0
    if hi_int < 0:
        hi_int = 0

    lo_norm, hi_extra = normalize_lo_register(lo, modulus=modulus)
    return (hi_int + hi_extra) * modulus + lo_norm


def decompose_combined(
    combined: int, modulus: int = MODBUS_UINT16_MODULUS
) -> Tuple[int, int]:
    """Descompone un acumulado en (hi, lo)."""
    try:
        value = int(combined)
    except (TypeError, ValueError):
        return 0, 0
    if value < 0:
        return 0, 0
    return value // modulus, value % modulus


def combine_modbus_registers(
    hi: Any,
    lo: Any,
    prev_combined: Optional[int] = None,
    modulus: int = MODBUS_UINT16_MODULUS,
    lo_near_top_ratio: float = LO_NEAR_TOP_RATIO,
    lo_near_zero_ratio: float = LO_NEAR_ZERO_RATIO,
) -> Tuple[int, str]:
    """
    Combina registros Modbus en un acumulado seguro ante mid-rollover.

    Args:
        hi: Multiplicador / conteo de rollovers (registro 5002).
        lo: Contador 16-bit (registro 5001).
        prev_combined: Acumulado Modbus de la lectura anterior (solo si el
            punto ya venía en TOTALIZADO_MODBUS_*). None = primera lectura
            Modbus / sin baseline comparable.
        modulus: Base del LO (65536).

    Returns:
        (combined, status) con status en:
        - OK: avance normal, hueco largo coherente, o primera lectura
        - MID_ROLLOVER_LO_AHEAD: LO wrapeó (cerca de 0) y HI aún no subió
        - MID_ROLLOVER_HI_AHEAD: HI subió y LO sigue alto (aún no wrapeó)
        - DEVICE_RESET: HI=0 y LO=0 tras un acumulado previo → re-baseline
        - HELD_NEGATIVE: regresión no explicable como wrap → se mantiene prev
    """
    try:
        hi_int = int(float(hi))
    except (TypeError, ValueError):
        hi_int = 0
    if hi_int < 0:
        hi_int = 0

    lo_norm, hi_extra = normalize_lo_register(lo, modulus=modulus)
    curr_hi = hi_int + hi_extra
    combined = curr_hi * modulus + lo_norm

    if prev_combined is None:
        return combined, "OK"

    try:
        prev = int(prev_combined)
    except (TypeError, ValueError):
        return combined, "OK"

    if prev < 0:
        return combined, "OK"

    # Reset de dispositivo: ambos registros en 0. No sostener forever;
    # el caller debe absorber el acumulado previo en addition.
    if curr_hi == 0 and lo_norm == 0 and prev > 0:
        return 0, "DEVICE_RESET"

    prev_hi, prev_lo = decompose_combined(prev, modulus=modulus)
    near_top = int(modulus * lo_near_top_ratio)
    near_zero = int(modulus * lo_near_zero_ratio)
    diff = combined - prev

    if diff >= 0:
        # Mid-rollover HI-ahead: HI +1 y LO sigue en zona alta (no wrapeó).
        # No aplicar si HI/LO son coherentes con un hueco largo (LO ya no alto).
        if (
            curr_hi == prev_hi + 1
            and prev_lo >= near_top
            and lo_norm >= near_top
        ):
            corrected = (prev_hi * modulus) + lo_norm  # = combined - modulus
            if corrected >= prev:
                return corrected, "MID_ROLLOVER_HI_AHEAD"
            return prev, "MID_ROLLOVER_HI_AHEAD"

        # Avance normal o hueco largo con HI/LO mutuamente consistentes.
        return combined, "OK"

    # diff < 0 — regresión -------------------------------------------------
    # Mid-rollover LO-ahead SOLO si el wrap es inequívoco:
    # LO previo cerca del tope y LO nuevo cerca de 0, mismo HI.
    if (
        curr_hi == prev_hi
        and prev_lo >= near_top
        and lo_norm <= near_zero
    ):
        corrected = combined + modulus  # (hi+1)*modulus + lo
        if corrected >= prev:
            return corrected, "MID_ROLLOVER_LO_AHEAD"
        return prev, "HELD_NEGATIVE"

    # Regresión chica (ej. LO 5→3) u otra caída no-wrap: sostener.
    return prev, "HELD_NEGATIVE"
