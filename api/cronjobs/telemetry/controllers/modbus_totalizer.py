"""
Totalizador Modbus de dos registros (LO 16-bit + HI multiplicador).
====================================================================

Dispositivos Modbus suelen exponer el acumulado en:
- Registro LO (ej. 5001): contador 16-bit que vuelve a 0 al alcanzar el módulo.
- Registro HI (ej. 5002): cuenta cuántas veces hizo rollover el LO.

Acumulado bruto = HI * 65536 + LO

El wrap puede ocurrir en 65535→0 (uint16) o, en algunos equipos, al llegar a
65536. Ambas se normalizan de forma segura.

Cuando HI y LO llegan en lecturas distintas / desfasadas (mid-rollover), el
valor combinado naive puede bajar o saltar ~65536. Este módulo corrige esos
bordes antes de alimentar el pipeline TOTALIZADO (total_m3 / total_hour),
para no generar consumo negativo ni picos enormes, ni disparar resets falsos
en addition.
"""

from __future__ import annotations

from typing import Any, Optional, Tuple

# Módulo del contador LO. uint16 wrapa en 65535→0; la base aritmética es 65536.
MODBUS_UINT16_MODULUS = 65536

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


def combine_modbus_registers(
    hi: Any,
    lo: Any,
    prev_combined: Optional[int] = None,
    modulus: int = MODBUS_UINT16_MODULUS,
    max_step: Optional[int] = None,
) -> Tuple[int, str]:
    """
    Combina registros Modbus en un acumulado monotónico seguro.

    Args:
        hi: Multiplicador / conteo de rollovers (registro 5002).
        lo: Contador 16-bit (registro 5001).
        prev_combined: Acumulado de la lectura anterior (InteractionDetail.pulses).
        modulus: Base del LO (65536).
        max_step: Tope de avance tras corregir mid-rollover. Default = modulus - 1
            (un avance "normal" nunca alcanza un módulo completo; un salto de
            exactamente 65536 con LO aún alto es HI-ahead, no consumo real).

    Returns:
        (combined, status) con status en:
        - OK: avance normal o primera lectura
        - MID_ROLLOVER_LO_AHEAD: LO wrapeó y HI aún no incrementó
        - MID_ROLLOVER_HI_AHEAD: HI incrementó y LO aún no wrapeó
        - HELD_NEGATIVE: caída no explicable → se mantiene prev
        - HELD_SPIKE: salto demasiado grande → se mantiene prev
    """
    if max_step is None:
        max_step = modulus - 1

    combined = combine_raw(hi, lo, modulus=modulus)

    if prev_combined is None:
        return combined, "OK"

    try:
        prev = int(prev_combined)
    except (TypeError, ValueError):
        return combined, "OK"

    diff = combined - prev

    # Avance normal: [0, modulus). Un salto de exactamente `modulus` con el
    # mismo LO es mid-rollover HI-ahead, no progreso legítimo.
    if 0 <= diff < modulus:
        return combined, "OK"

    # Mid-rollover A: LO ya wrapeó, HI aún no → combined cae ~modulus.
    if -modulus <= diff < 0:
        corrected = combined + modulus  # equivalente a (hi+1)*modulus + lo
        corr_diff = corrected - prev
        if 0 <= corr_diff <= max_step:
            return corrected, "MID_ROLLOVER_LO_AHEAD"
        return prev, "HELD_NEGATIVE"

    # Mid-rollover B: HI ya subió, LO aún no wrapeó → salto ≈ modulus..2*modulus.
    if modulus <= diff <= 2 * modulus:
        corrected = combined - modulus  # equivalente a (hi-1)*modulus + lo
        corr_diff = corrected - prev
        if 0 <= corr_diff <= max_step:
            return corrected, "MID_ROLLOVER_HI_AHEAD"
        # Corregir deja valor < prev (desfase sin progreso) → sostener.
        if corrected <= prev:
            return prev, "MID_ROLLOVER_HI_AHEAD"
        return prev, "HELD_SPIKE"

    if diff < 0:
        return prev, "HELD_NEGATIVE"

    return prev, "HELD_SPIKE"
