"""
Circuit Breaker Pattern Implementation

Protects against cascading failures when calling external services:
- DGA API (Direccion General de Aguas)
- SMA API (Servicio de Evaluacion Ambiental)
- MQTT Broker
- External telemetry providers

States:
- CLOSED: Normal operation, requests pass through
- OPEN: Failure threshold reached, requests fail fast
- HALF_OPEN: Testing if service recovered

Inspired by Martin Fowler's Circuit Breaker pattern.
"""

import logging
import time
from enum import Enum
from functools import wraps
from typing import Any, Callable, Optional, Type

from django.core.cache import cache
from django.utils import timezone

from .models import CircuitBreakerLog, CircuitState

logger = logging.getLogger("api.gateway.circuit")


class CircuitBreakerError(Exception):
    """Raised when circuit breaker is open."""

    def __init__(self, provider_name: str, message: str = ""):
        self.provider_name = provider_name
        self.message = message or f"Circuit breaker is OPEN for {provider_name}"
        super().__init__(self.message)


class CircuitBreaker:
    """
    Circuit breaker for external service calls.

    Usage:
        breaker = CircuitBreaker("dga_api")
        try:
            result = breaker.call(dga_client.submit_data, data)
        except CircuitBreakerError:
            # Handle circuit open - use cached data or fail gracefully
            pass
    """

    CACHE_PREFIX = "circuit_breaker"
    CACHE_TTL = 3600  # 1 hour

    def __init__(
        self,
        provider_name: str,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        half_open_max_calls: int = 3,
        expected_exception: Type[Exception] = Exception,
    ):
        self.provider_name = provider_name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self.expected_exception = expected_exception

    def _get_cache_key(self, suffix: str) -> str:
        return f"{self.CACHE_PREFIX}:{self.provider_name}:{suffix}"

    def _get_state(self) -> dict:
        """Get current circuit state from cache."""
        state = cache.get(self._get_cache_key("state"))
        if state is None:
            state = {
                "state": CircuitState.CLOSED,
                "failure_count": 0,
                "success_count": 0,
                "last_failure": None,
                "last_success": None,
                "opened_at": None,
                "half_open_calls": 0,
            }
        return state

    def _set_state(self, state: dict):
        """Persist circuit state to cache."""
        cache.set(self._get_cache_key("state"), state, self.CACHE_TTL)

    def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function with circuit breaker protection.

        Args:
            func: Function to call
            *args, **args: Arguments for the function

        Returns:
            Result of func(*args, **kwargs)

        Raises:
            CircuitBreakerError: If circuit is OPEN
            expected_exception: If the wrapped function raises
        """
        state = self._get_state()

        if state["state"] == CircuitState.OPEN:
            if self._can_attempt_reset(state):
                state["state"] = CircuitState.HALF_OPEN
                state["half_open_calls"] = 0
                self._set_state(state)
                logger.info(f"Circuit {self.provider_name} entering HALF_OPEN")
            else:
                raise CircuitBreakerError(self.provider_name)

        if state["state"] == CircuitState.HALF_OPEN:
            if state["half_open_calls"] >= self.half_open_max_calls:
                raise CircuitBreakerError(self.provider_name)
            state["half_open_calls"] += 1
            self._set_state(state)

        # Execute the call
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except self.expected_exception as e:
            self._on_failure()
            raise

    def _on_success(self):
        """Handle successful call."""
        state = self._get_state()
        state["success_count"] += 1
        state["last_success"] = time.time()

        if state["state"] == CircuitState.HALF_OPEN:
            # If enough successes in half-open, close the circuit
            if state["success_count"] >= self.half_open_max_calls:
                state["state"] = CircuitState.CLOSED
                state["failure_count"] = 0
                state["half_open_calls"] = 0
                logger.info(f"Circuit {self.provider_name} CLOSED (recovered)")
                self._persist_log(state)

        self._set_state(state)

    def _on_failure(self):
        """Handle failed call."""
        state = self._get_state()
        state["failure_count"] += 1
        state["last_failure"] = time.time()

        if state["state"] == CircuitState.HALF_OPEN:
            # Failed in half-open, go back to open
            state["state"] = CircuitState.OPEN
            state["opened_at"] = time.time()
            logger.warning(
                f"Circuit {self.provider_name} OPEN (failed in half-open)"
            )
            self._persist_log(state)
        elif state["failure_count"] >= self.failure_threshold:
            # Threshold reached, open circuit
            state["state"] = CircuitState.OPEN
            state["opened_at"] = time.time()
            logger.warning(
                f"Circuit {self.provider_name} OPEN ({state['failure_count']} failures)"
            )
            self._persist_log(state)

        self._set_state(state)

    def _can_attempt_reset(self, state: dict) -> bool:
        """Check if enough time has passed to try half-open."""
        if not state.get("opened_at"):
            return True
        return (time.time() - state["opened_at"]) >= self.recovery_timeout

    def _persist_log(self, state: dict):
        """Persist state transition to database for monitoring."""
        try:
            log, _ = CircuitBreakerLog.objects.get_or_create(
                provider_name=self.provider_name,
                defaults={
                    "failure_threshold": self.failure_threshold,
                    "recovery_timeout": self.recovery_timeout,
                    "half_open_max_calls": self.half_open_max_calls,
                },
            )
            log.state = state["state"]
            log.failure_count = state["failure_count"]
            log.success_count = state["success_count"]

            if state.get("last_failure"):
                log.last_failure_at = timezone.make_aware(
                    timezone.datetime.fromtimestamp(state["last_failure"])
                )
            if state.get("last_success"):
                log.last_success_at = timezone.make_aware(
                    timezone.datetime.fromtimestamp(state["last_success"])
                )
            if state.get("opened_at"):
                log.opened_at = timezone.make_aware(
                    timezone.datetime.fromtimestamp(state["opened_at"])
                )

            log.save()
        except Exception as e:
            logger.error(f"Failed to persist circuit log: {e}")


def circuit_breaker(
    provider_name: str,
    failure_threshold: int = 5,
    recovery_timeout: int = 60,
    expected_exception: Type[Exception] = Exception,
):
    """
    Decorator for circuit breaker pattern.

    Usage:
        @circuit_breaker("dga_api", failure_threshold=3, recovery_timeout=30)
        def submit_dga_data(data):
            return dga_client.submit(data)
    """
    breaker = CircuitBreaker(
        provider_name=provider_name,
        failure_threshold=failure_threshold,
        recovery_timeout=recovery_timeout,
        expected_exception=expected_exception,
    )

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            return breaker.call(func, *args, **kwargs)
        return wrapper
    return decorator
