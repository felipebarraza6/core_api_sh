import requests
from datetime import datetime
import time


def _provider_val(provider, key, default=None):
    if not provider:
        return default
    return provider.get(key, default) if isinstance(provider, dict) else getattr(provider, key, default)


def get_data_thethings(provider, token_service, str_variable):
    """Obtener datos de THETHINGS´."""

    token = token_service
    base_url = _provider_val(provider, 'base_url') or "https://api.thethings.io/v2"
    url = f"{base_url.rstrip('/')}/things/{token}/resources/{str_variable}"

    for _ in range(3):  # Intentar hasta 3 veces
        try:
            response = requests.request("GET", url, timeout=5)
            response.raise_for_status()
            data = response.json()
            # Debug logs removidos para evitar fuga de tokens en producción
            if data and len(data) > 0:
                item = data[0]  # Obtener el último elemento
                ts = datetime.strptime(
                    item["datetime"], "%Y-%m-%dT%H:%M:%S.%fZ")
                formatted_ts = ts.strftime("%Y-%m-%dT%H:%M:%S")
                value = item.get("value", 0)
                # Valores procesados sin log de debug
                return {"value": value, "date_time": formatted_ts}
            else:
                return {"value": 0, "date_time": None}
        except requests.RequestException as e:
            print(f"Error al obtener datos: {e}")
            time.sleep(1)  # Esperar 1 segundo antes de reintentar
    return {"value": 0, "date_time": None}
