import logging
import requests

from api.cronjobs.telemetry.utils.connection import utc_iso_to_chile_str
from api.cronjobs.telemetry.utils.getter_result import (
    http_status_from_exc,
    no_data_result,
    ok_result,
    request_failed_result,
)

logger = logging.getLogger(__name__)


def _provider_val(provider, key, default=None):
    if not provider:
        return default
    return provider.get(key, default) if isinstance(provider, dict) else getattr(provider, key, default)


def get_data_thethings(provider, token_service, str_variable):
    """Obtener datos de THETHINGS´."""

    token = token_service
    base_url = _provider_val(provider, 'base_url') or "https://api.thethings.io/v2"
    url = f"{base_url.rstrip('/')}/things/{token}/resources/{str_variable}"

    try:
        response = requests.request("GET", url, timeout=15)
        response.raise_for_status()
        data = response.json()
        # Debug logs removidos para evitar fuga de tokens en producción
        if data and len(data) > 0:
            item = data[0]  # Obtener el último elemento
            # TheThings.io entrega la fecha en UTC ("...Z"): convertir a hora de Chile.
            # Antes se guardaba la hora UTC como si fuera local (3-4 h adelantada).
            formatted_ts = utc_iso_to_chile_str(item.get("datetime"))
            value = item.get("value", 0)
            return ok_result(value, formatted_ts)
        return no_data_result()
    except requests.RequestException as e:
        logger.error(f"Error al obtener datos: {e}")
        return request_failed_result(error=e, http_status=http_status_from_exc(e))
