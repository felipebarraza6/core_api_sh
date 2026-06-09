"""Getter genérico JSON configurable via parser_config."""

import json
import logging
import requests
from datetime import datetime

logger = logging.getLogger(__name__)


def _provider_val(provider, key, default=None):
    if not provider:
        return default
    return provider.get(key, default) if isinstance(provider, dict) else getattr(provider, key, default)


def _resolve_json_path(data, path):
    """Navegar dict anidado por path con puntos. Ej: 'result.0.value'"""
    if not path:
        return data
    keys = path.split(".")
    for k in keys:
        if data is None:
            return None
        if isinstance(data, list):
            try:
                idx = int(k)
                data = data[idx]
            except (ValueError, IndexError):
                return None
        elif isinstance(data, dict):
            data = data.get(k)
        else:
            return None
    return data


def _parse_timestamp(ts_raw, fmt, custom_fmt=None):
    if fmt == "epoch_ms":
        ts = datetime.fromtimestamp(ts_raw / 1000.0)
    elif fmt == "epoch_s":
        ts = datetime.fromtimestamp(ts_raw)
    elif fmt == "iso8601":
        ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
    elif fmt == "custom_str":
        ts = datetime.strptime(ts_raw, custom_fmt or "%Y-%m-%dT%H:%M:%S")
    else:
        ts = datetime.now()
    return ts.strftime("%Y-%m-%dT%H:%M:%S")


def _build_headers(provider):
    auth_type = _provider_val(provider, "auth_type", "NONE")
    token = _provider_val(provider, "auth_token", "")
    header_name = _provider_val(provider, "auth_header_name", "Authorization")
    username = _provider_val(provider, "auth_username", "")
    password = _provider_val(provider, "auth_password", "")

    headers = {"Content-Type": "application/json"}

    if auth_type == "BEARER" and token:
        headers[header_name] = f"Bearer {token}"
    elif auth_type == "API_KEY_HEADER" and token:
        headers[header_name] = token
    elif auth_type == "BASIC" and username and password:
        import base64
        creds = base64.b64encode(f"{username}:{password}".encode()).decode()
        headers[header_name] = f"Basic {creds}"

    # Headers extra del parser_config
    parser_config = _provider_val(provider, "parser_config", {}) or {}
    extra_headers = parser_config.get("headers", {})
    headers.update(extra_headers)

    return headers


import time

def get_data_generic(provider, token_service, str_variable):
    """Obtener datos usando configuración genérica del proveedor."""
    base_url = (_provider_val(provider, "base_url") or "").rstrip("/")
    endpoint = _provider_val(provider, "endpoint_template", "")
    timeout = _provider_val(provider, "timeout_seconds", 5)
    retries = _provider_val(provider, "retry_attempts", 3)

    parser_config = _provider_val(provider, "parser_config", {}) or {}

    # Construir URL
    url = base_url
    if endpoint:
        url += endpoint.format(token=token_service, variable=str_variable)

    # Query param auth
    auth_type = _provider_val(provider, "auth_type", "NONE")
    if auth_type == "QUERY_PARAM":
        token = _provider_val(provider, "auth_token", "")
        sep = "&" if "?" in url else "?"
        url += f"{sep}api_key={token}"

    headers = _build_headers(provider)

    last_error = None
    for attempt in range(retries):
        try:
            response = requests.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()
            data = response.json()

            # Navegar respuesta
            root_key = parser_config.get("response_root_key")
            if root_key:
                root_key = root_key.format(token=token_service, variable=str_variable)
                data = _resolve_json_path(data, root_key)

            if parser_config.get("response_is_array") and isinstance(data, list):
                idx = parser_config.get("response_array_index", 0)
                data = data[idx] if len(data) > idx else None

            if data is None:
                return {"value": 0, "date_time": None}

            # Extraer valor y timestamp
            value_field = parser_config.get("value_field", "value")
            ts_field = parser_config.get("timestamp_field", "timestamp")
            ts_format = parser_config.get("timestamp_format", "iso8601")
            ts_custom = parser_config.get("timestamp_custom_format")

            value = _resolve_json_path(data, value_field)
            ts_raw = _resolve_json_path(data, ts_field)

            if value is None:
                return {"value": 0, "date_time": None}

            timestamp = _parse_timestamp(ts_raw, ts_format, ts_custom) if ts_raw else None
            return {"value": value, "date_time": timestamp}

        except Exception as e:
            last_error = e
            if attempt < retries - 1:
                time.sleep(2 ** attempt)  # backoff exponencial: 1s, 2s, 4s...
            else:
                logger.error(f"Error genérico getter {url} tras {retries} intentos: {e}")
                return {"value": 0, "date_time": None}

    logger.error(f"Error genérico getter {url} tras {retries} intentos: {last_error}")
    return {"value": 0, "date_time": None}
