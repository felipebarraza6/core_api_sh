"""Script TDATA."""
import json
import os
import requests
from datetime import datetime
import time


def _provider_val(provider, key, default=None):
    if not provider:
        return default
    return provider.get(key, default) if isinstance(provider, dict) else getattr(provider, key, default)


def get_token(provider=None):
    """Obtener token de autenticación."""
    username = _provider_val(provider, 'auth_username') or os.environ.get("TDATA_USERNAME")
    password = _provider_val(provider, 'auth_password') or os.environ.get("TDATA_PASSWORD")
    if not username or not password:
        raise RuntimeError(
            "TDATA_USERNAME y TDATA_PASSWORD deben estar configurados "
            "en el proveedor o como variables de entorno."
        )
    base_url = _provider_val(provider, 'base_url') or "https://api.twindimension.com/tdata/v1"
    url = f"{base_url.rstrip('/')}/login"
    payload = json.dumps({
        "username": username,
        "password": password,
    })
    headers = {
        'Content-Type': 'application/json'
    }
    response = requests.request(
        "POST", url, headers=headers, data=payload, timeout=5)
    response_data = response.json()
    return response_data["token"]


def get_data_tdata(provider, token_service, str_variable):
    """Obtener datos de TDATA."""
    token_auth = get_token(provider)
    if not token_auth:
        print("No se pudo obtener el token de autenticación.")
        return {"date_time": None, "value": 0}

    token = token_service
    base_url = getattr(provider, 'base_url', None) or "https://api.twindimension.com/tdata/v1"
    url = f"{base_url.rstrip('/')}/telemetry/DEVICE/{token}/values/timeseries?keys={str_variable}"
    headers = {
        'Authorization': f"Bearer {token_auth}"
    }
    # Debug logs removidos para evitar fuga de tokens en producción
    for _ in range(3):  # Intentar hasta 3 veces
        try:
            response = requests.request("GET", url, headers=headers, timeout=5)
            response.raise_for_status()
            data = response.json()
            # Response data procesada sin log
            if str_variable in data and data[str_variable]:
                item = data[str_variable][-1]  # Obtener el último elemento
                ts = datetime.fromtimestamp(item["ts"] / 1000)
                formatted_ts = ts.strftime("%Y-%m-%dT%H:%M:%S")
                value = item.get("value", 0)
                return {"date_time": formatted_ts, "value": value}
            else:
                return {"date_time": None, "value": 0}
        except requests.RequestException as e:
            print(f"Error al obtener datos: {e}")
            time.sleep(1)  # Esperar 1 segundo antes de reintentar
    return {"date_time": None, "value": 0}
