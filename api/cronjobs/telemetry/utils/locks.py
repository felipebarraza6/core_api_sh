"""Locks distribuidos para procesamiento de telemetría usando Redis."""

import logging

from django.core.cache import cache

logger = logging.getLogger(__name__)
LOCK_TIMEOUT_SECONDS = 120  # Máximo tiempo que un punto puede estar bloqueado


def acquire_point_lock(point_id: int, timeout: int = LOCK_TIMEOUT_SECONDS) -> bool:
    """
    Adquiere lock distribuido para un punto de captación.
    Usa cache.add() que es atómico en Redis (SET NX EX).

    Args:
        point_id: ID del CatchmentPoint.
        timeout: TTL en segundos del lock.

    Returns:
        True si se adquirió el lock, False si ya está bloqueado o Redis falló.
    """
    key = f"smarthydro:point_lock:{point_id}"
    try:
        return cache.add(key, 1, timeout)
    except Exception as e:
        logger.critical(
            f"[LOCK] Redis falló al adquirir lock para punto {point_id}: {e}. "
            f"Continuando sin lock (riesgo de race condition)."
        )
        return False


def release_point_lock(point_id: int) -> None:
    """Libera el lock de un punto. No lanza excepciones."""
    key = f"smarthydro:point_lock:{point_id}"
    try:
        cache.delete(key)
    except Exception as e:
        logger.error(f"[LOCK] Redis falló al liberar lock para punto {point_id}: {e}")
