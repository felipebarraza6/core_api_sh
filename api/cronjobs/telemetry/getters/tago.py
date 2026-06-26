from datetime import datetime
import logging
import time
import requests

logger = logging.getLogger(__name__)


def _provider_val(provider, key, default=None):
    if not provider:
        return default
    return provider.get(key, default) if isinstance(provider, dict) else getattr(provider, key, default)


def get_data_tago(provider, token_service, str_variable):
    """Obtener datos de Tago.io (último valor)."""

    token = token_service
    base_url = _provider_val(provider, 'base_url') or "https://api.tago.io"
    url = f"{base_url.rstrip('/')}/data/?variable={str_variable}&query=last_item"
    header_name = _provider_val(provider, 'auth_header_name') or "authorization"
    auth_token = _provider_val(provider, 'auth_token') or token
    try:
        response = requests.request("GET", url, timeout=5, headers={
                                    header_name: auth_token})
        response.raise_for_status()
        data = response.json()
        if data and data['result'] and len(data['result']) > 0:
            item = data['result'][0]
            ts = datetime.strptime(
                item.get('time'), "%Y-%m-%dT%H:%M:%S.%fZ")
            formatted_ts = ts.strftime("%Y-%m-%dT%H:%M:%S")
            value = item.get("value", 0)
            if isinstance(value, int) and value < 0:
                value = 0
            elif isinstance(value, float):
                value = round(value, 2)
            return {"date_time": formatted_ts, "value": value}
        else:
            return {"date_time": None, "value": 0}
    except requests.RequestException as e:
        logger.error(f"Error al obtener datos: {e}")
        return {"date_time": None, "value": 0}


def get_data_tago_history(provider, token_service, str_variable, start_dt, end_dt, limit=None):
    """
    Obtener histórico de datos de Tago.io para un rango de fechas.

    Args:
        provider: Instancia del proveedor de telemetría.
        token_service: Token del dispositivo en TagoIO.
        str_variable: Clave de la variable.
        start_dt: datetime de inicio (naive UTC).
        end_dt: datetime de fin (naive UTC).
        limit: No-op (compatibilidad con API de TDATA), TagoIO no usa limit.

    Returns:
        Lista de dicts ordenada cronológicamente.
    """
    token = token_service
    base_url = _provider_val(provider, 'base_url') or "https://api.tago.io"
    header_name = _provider_val(provider, 'auth_header_name') or "authorization"
    auth_token = _provider_val(provider, 'auth_token') or token

    start_str = start_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    end_str = end_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")

    url = (
        f"{base_url.rstrip('/')}/data"
        f"?variable={str_variable}&start_date={start_str}&end_date={end_str}&qty=10000"
    )
    headers = {header_name: auth_token}

    for attempt in range(3):
        try:
            response = requests.request("GET", url, headers=headers, timeout=30)
            response.raise_for_status()
            data = response.json()

            if not data.get('result') or len(data['result']) == 0:
                return []

            results = []
            for item in data['result']:
                ts = datetime.strptime(item.get('time'), "%Y-%m-%dT%H:%M:%S.%fZ")
                formatted_ts = ts.strftime("%Y-%m-%dT%H:%M:%S")
                results.append({
                    "ts_ms": int(ts.timestamp() * 1000),
                    "value": item.get("value", 0),
                    "date_time": formatted_ts,
                })
            results.sort(key=lambda x: x["ts_ms"])
            return results
        except requests.RequestException as e:
            logger.error(f"Error al obtener histórico TagoIO (intento {attempt + 1}): {e}")
            time.sleep(1)
    return []
