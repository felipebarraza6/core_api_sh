"""Locks distribuidos para cronjobs usando Redis.

Extiende el patrón de locks por punto (api.cronjobs.telemetry.utils.locks)
con locks globales por job, para prevenir ejecuciones paralelas de cronjobs
que procesan lotes (alert_engine, alert_dispatcher, DGA, SMA).
"""

import functools
import logging

from django.core.cache import cache

logger = logging.getLogger(__name__)

# Timeouts recomendados por job (segundos)
CRON_LOCK_TIMEOUTS = {
    "alert_engine": 90,
    "alert_dispatcher": 120,
    "dga": 300,
    "sma": 300,
}


def acquire_cron_lock(lock_name: str, timeout: int) -> bool:
    """
    Adquiere lock global para un cronjob.
    Usa cache.add() atómico (SET NX EX en Redis).

    Args:
        lock_name: Nombre identificador del job (ej. "alert_engine").
        timeout: TTL en segundos.

    Returns:
        True si se adquirió, False si ya está bloqueado o Redis falló.
    """
    key = f"smarthydro:cron_lock:{lock_name}"
    try:
        acquired = cache.add(key, 1, timeout)
        if not acquired:
            logger.warning(f"[CRON_LOCK] {lock_name} ya en ejecución. Saltando.")
        return acquired
    except Exception as e:
        logger.critical(
            f"[CRON_LOCK] Redis falló al adquirir lock para {lock_name}: {e}. "
            f"Saltando ejecución por seguridad."
        )
        return False


def release_cron_lock(lock_name: str) -> None:
    """Libera lock global de un cronjob. No lanza excepciones."""
    key = f"smarthydro:cron_lock:{lock_name}"
    try:
        cache.delete(key)
    except Exception as e:
        logger.error(f"[CRON_LOCK] Redis falló al liberar lock para {lock_name}: {e}")


def cron_job_lock(lock_name: str, timeout: int = 300):
    """
    Decorador para envolver funciones de cronjob con un lock global.

    Uso:
        @cron_job_lock("alert_engine", timeout=90)
        def run():
            ...
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if not acquire_cron_lock(lock_name, timeout):
                return {"skipped": True, "reason": "locked", "job": lock_name}
            try:
                return func(*args, **kwargs)
            finally:
                try:
                    release_cron_lock(lock_name)
                except Exception:
                    pass  # Ya logueado; no enmascarar excepción original

        return wrapper

    return decorator
