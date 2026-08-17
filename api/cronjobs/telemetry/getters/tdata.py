"""Script TDATA."""
import base64
import hashlib
import json
import logging
import os
import requests
from datetime import datetime
import time

from django.core.cache import cache

logger = logging.getLogger(__name__)


def _provider_val(provider, key, default=None):
    if not provider:
        return default
    return provider.get(key, default) if isinstance(provider, dict) else getattr(provider, key, default)


def _cache_key(provider):
    """Generar clave de caché única por proveedor para el token TDATA."""
    provider_id = _provider_val(provider, 'id')
    if provider_id:
        return f"tdata:token:{provider_id}"
    base_url = _provider_val(provider, 'base_url') or 'default'
    username = _provider_val(provider, 'auth_username') or 'default'
    key = hashlib.md5(f"{base_url}:{username}".encode()).hexdigest()
    return f"tdata:token:{key}"


TOKEN_CACHE_TTL_FALLBACK = 3300  # Fallback si no podemos decodificar el JWT
TOKEN_CACHE_MARGIN = 60  # Segundos de margen antes del exp para evitar race conditions


def _jwt_expiry_ttl(token):
    """Extraer el campo 'exp' del payload JWT y calcular TTL restante en segundos."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return TOKEN_CACHE_TTL_FALLBACK
        payload_b64 = parts[1]
        # Agregar padding base64url si falta
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding
        payload_json = base64.urlsafe_b64decode(payload_b64)
        payload = json.loads(payload_json)
        exp = payload.get("exp")
        if not exp:
            return TOKEN_CACHE_TTL_FALLBACK
        ttl = int(exp) - int(time.time()) - TOKEN_CACHE_MARGIN
        return max(ttl, 300)  # Mínimo 5 minutos de cache
    except Exception:
        return TOKEN_CACHE_TTL_FALLBACK


def get_token(provider=None):
    """Obtener token de autenticación con cache en Redis (TTL según expiración JWT)."""
    cache_key = _cache_key(provider)
    try:
        cached_token = cache.get(cache_key)
        if cached_token:
            return cached_token
    except Exception:
        # Si Redis falla, continuar sin cache
        pass

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
    if response.status_code != 200:
        logger.error(
            f"TDATA login falló: HTTP {response.status_code} desde {url}"
        )
        raise RuntimeError(
            f"TDATA login falló con HTTP {response.status_code}"
        )
    response_data = response.json()
    token = response_data.get("token")
    if not token:
        logger.error(f"TDATA login: respuesta sin 'token': {list(response_data.keys())}")
        raise RuntimeError("TDATA login: respuesta sin campo 'token'")

    ttl = _jwt_expiry_ttl(token)
    try:
        cache.set(cache_key, token, timeout=ttl)
    except Exception:
        # Si Redis falla, devolver token igual pero no cachear
        pass

    return token


def get_data_tdata(provider, token_service, str_variable):
    """Obtener datos de TDATA (último valor)."""
    token_auth = get_token(provider)
    if not token_auth:
        logger.error("No se pudo obtener el token de autenticación.")
        return {"date_time": None, "value": 0}

    token = token_service
    base_url = getattr(provider, 'base_url', None) or "https://api.twindimension.com/tdata/v1"
    url = f"{base_url.rstrip('/')}/telemetry/DEVICE/{token}/values/timeseries?keys={str_variable}"
    headers = {
        'Authorization': f"Bearer {token_auth}"
    }
    # Debug logs removidos para evitar fuga de tokens en producción
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
        logger.error(f"Error al obtener datos: {e}")
        return {"date_time": None, "value": 0}


def get_data_tdata_history(provider, token_service, str_variable, start_dt, end_dt, limit=10000):
    """
    Obtener histórico de datos de TDATA para un rango de fechas.

    Args:
        provider: Instancia del proveedor de telemetría.
        token_service: Token del dispositivo en TDATA.
        str_variable: Clave de la variable (ej: '5001', '5003').
        start_dt: datetime de inicio (timezone-aware o naive UTC).
        end_dt: datetime de fin (timezone-aware o naive UTC).
        limit: Máximo registros a obtener (ThingsBoard default=100).

    Returns:
        Lista de dicts: [{"ts_ms": int, "value": any, "date_time": "YYYY-MM-DDTHH:MM:SS"}, ...]
        Ordenada cronológicamente (más antiguo primero).
        Vacía si no hay datos o hay error.
    """
    token_auth = get_token(provider)
    if not token_auth:
        logger.error("No se pudo obtener el token de autenticación para histórico.")
        return []

    token = token_service
    base_url = getattr(provider, 'base_url', None) or "https://api.twindimension.com/tdata/v1"

    # ThingsBoard usa timestamps en milisegundos
    start_ms = int(start_dt.timestamp() * 1000)
    end_ms = int(end_dt.timestamp() * 1000)

    all_results = []
    current_start_ms = start_ms

    while current_start_ms < end_ms:
        url = (
            f"{base_url.rstrip('/')}/telemetry/DEVICE/{token}/values/timeseries"
            f"?keys={str_variable}&startTs={current_start_ms}&endTs={end_ms}"
            f"&limit={limit}&asc=true"
        )
        headers = {'Authorization': f"Bearer {token_auth}"}

        for attempt in range(3):
            try:
                response = requests.request("GET", url, headers=headers, timeout=30)
                response.raise_for_status()
                data = response.json()

                if str_variable not in data or not data[str_variable]:
                    return all_results

                batch = []
                for item in data[str_variable]:
                    ts = datetime.fromtimestamp(item["ts"] / 1000)
                    formatted_ts = ts.strftime("%Y-%m-%dT%H:%M:%S")
                    batch.append({
                        "ts_ms": item["ts"],
                        "value": item.get("value", 0),
                        "date_time": formatted_ts,
                    })

                if not batch:
                    return all_results

                all_results.extend(batch)

                # Si recibimos menos del límite, es el último batch
                if len(batch) < limit:
                    return all_results

                # Paginar: el último timestamp + 1 ms como nuevo start
                current_start_ms = batch[-1]["ts_ms"] + 1
                break  # Salir del retry loop, continuar while

            except requests.RequestException as e:
                logger.error(f"Error al obtener histórico TDATA (intento {attempt + 1}): {e}")
                if attempt == 2:
                    return all_results
                time.sleep(1)

    return all_results
