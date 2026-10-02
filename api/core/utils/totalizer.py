"""
Vistas del totalizador — fuente de verdad única.

Hay tres números distintos del "total" en el sistema. No son bugs de cálculo
independientes: parten del mismo valor almacenado y aplican transformaciones
documentadas según el consumidor.

  stored   = (pulsos × pulses_factor) / 1000 + addition
             → lo que vive en InteractionDetail.total
             → incluye `addition` para mantener continuidad tras resets

  display  = stored + d6
             → lo que muestra la API (interaction_detail_json / serializers)
             → d6 = caudalímetro inicial / baseline histórico de presentación

  dga      = stored − addition  (= pulsos × factor / 1000, sin offset de resets)
             → lo que se informa a la DGA (norma: escala del sensor, sin addition)

Ver docs/TOTALIZER_VIEWS.md para el razonamiento y decisiones abiertas.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Mapping, Optional, Union


NumberLike = Union[int, float, Decimal, str, None]


def _to_int(value: NumberLike, default: int = 0) -> int:
    """Convierte a int de forma segura (CharField / Decimal / None)."""
    if value is None or value == "":
        return default
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return default


def resolve_totalizer_views(
    stored_total: NumberLike,
    addition: NumberLike = 0,
    d6: NumberLike = 0,
) -> dict:
    """
    Calcula las tres vistas del totalizador desde el valor almacenado.

    Args:
        stored_total: InteractionDetail.total (incluye addition).
        addition: ProfileDataConfigCatchment.addition (offset por resets).
        d6: ProfileDataConfigCatchment.d6 (caudalímetro inicial / display).

    Returns:
        dict con claves: stored, display, dga, addition, d6.
    """
    stored = _to_int(stored_total)
    addition_i = _to_int(addition)
    d6_i = _to_int(d6)

    # DGA: nunca negativo por over-subtraction de addition
    dga = max(0, stored - addition_i)
    display = stored + d6_i

    return {
        "stored": stored,
        "display": display,
        "dga": dga,
        "addition": addition_i,
        "d6": d6_i,
    }


def views_from_profile(
    stored_total: NumberLike,
    profile: Optional[Any] = None,
) -> dict:
    """Atajo: lee addition/d6 desde un ProfileDataConfigCatchment (o dict)."""
    if profile is None:
        return resolve_totalizer_views(stored_total)

    if isinstance(profile, Mapping):
        addition = profile.get("addition", 0)
        d6 = profile.get("d6", 0)
    else:
        addition = getattr(profile, "addition", 0)
        d6 = getattr(profile, "d6", 0)

    return resolve_totalizer_views(stored_total, addition=addition, d6=d6)
