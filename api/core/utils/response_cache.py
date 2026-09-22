"""
Cache opt-in de respuestas HTTP idénticas (GET).
=================================================

Guarda en el backend de cache (Redis en prod, LocMem en tests) la respuesta
de vistas GET cuando API_RESPONSE_CACHE_TTL > 0. Si TTL es 0 o no está
definido, el decorator es no-op (comportamiento por defecto: sin cache).

Clave: método + path + query string + user id (aislamiento por usuario).
TTL corto: pensado para telemetría/dashboards que se consultan seguido.
"""
import hashlib
import logging

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


def _get_ttl():
    return int(getattr(settings, "API_RESPONSE_CACHE_TTL", 0) or 0)


def make_cache_key(request):
    """Clave de cache estable para una request GET autenticada."""
    user_id = getattr(request.user, "id", None) if request.user else None
    raw = "|".join([
        request.method,
        request.get_full_path(),
        str(user_id),
    ])
    return "api:resp:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def cached_get_response(view_func):
    """
    Decorator para APIView.get / vistas function-based GET.

    Solo actúa si:
    - settings.API_RESPONSE_CACHE_TTL > 0
    - request.method == 'GET'
    - la respuesta es exitosa (status_code 200)

    Fallo de cache = comportamiento normal (fail-open).
    """
    def wrapper(self, request, *args, **kwargs):
        ttl = _get_ttl()
        if ttl <= 0 or request.method != "GET":
            return view_func(self, request, *args, **kwargs)

        key = make_cache_key(request)
        try:
            cached = cache.get(key)
            if cached is not None:
                return cached
        except Exception:
            logger.debug("response cache get failed", exc_info=True)

        response = view_func(self, request, *args, **kwargs)

        try:
            if getattr(response, "status_code", None) == 200:
                cache.set(key, response, ttl)
        except Exception:
            logger.debug("response cache set failed", exc_info=True)

        return response

    return wrapper
