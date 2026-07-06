"""TDATA (TwinDimension / ThingsBoard) provider for void."""
import base64
import hashlib
import json
import logging
import time
from datetime import datetime, timezone as dt_timezone
from typing import Any, Dict, List, Optional

import requests
from django.core.cache import cache

from void.models import Provider

from .base import BaseProvider

logger = logging.getLogger(__name__)

TOKEN_CACHE_TTL_FALLBACK = 3300
TOKEN_CACHE_MARGIN = 60


def _jwt_expiry_ttl(token: str) -> int:
    """Extrae el campo 'exp' de un JWT y retorna TTL restante en segundos."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return TOKEN_CACHE_TTL_FALLBACK
        payload_b64 = parts[1]
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding
        payload_json = base64.urlsafe_b64decode(payload_b64)
        payload = json.loads(payload_json)
        exp = payload.get("exp")
        if not exp:
            return TOKEN_CACHE_TTL_FALLBACK
        ttl = int(exp) - int(time.time()) - TOKEN_CACHE_MARGIN
        return max(ttl, 300)
    except Exception:
        return TOKEN_CACHE_TTL_FALLBACK


class TdataProvider(BaseProvider):
    """Proveedor TDATA con login JWT + cache Redis.

    Requiere un Provider con:
    - auth_type=BASIC o CUSTOM (username/password en auth_config)
    - ProviderEndpoint AUTH: POST /login
    - ProviderEndpoint INGEST: GET /telemetry/DEVICE/{external_id}/values/timeseries
    """

    name = "tdata"

    def __init__(self, provider: Provider):
        super().__init__(provider)
        self._token: Optional[str] = None

    def _cache_key(self) -> str:
        provider_id = getattr(self.provider, "id", None)
        if provider_id:
            return f"void:tdata:token:{provider_id}"
        base_url = self.provider.base_url or "default"
        username = (self.provider.auth_config or {}).get("username", "default")
        key = hashlib.md5(f"{base_url}:{username}".encode()).hexdigest()
        return f"void:tdata:token:{key}"

    def _get_auth_token(self) -> str:
        """Obtiene token JWT, usando cache Redis cuando es posible."""
        cache_key = self._cache_key()
        try:
            cached = cache.get(cache_key)
            if cached:
                return cached
        except Exception:
            pass

        auth_config = self.provider.auth_config or {}
        username = auth_config.get("username")
        password = auth_config.get("password")
        if not username or not password:
            raise RuntimeError("TDATA requiere username y password en auth_config")

        auth_endpoint = self.provider.get_endpoint("AUTH")
        base_url = (self.provider.base_url or "https://api.twindimension.com/tdata/v1").rstrip("/")
        login_path = (auth_endpoint.path_template if auth_endpoint else "/login").lstrip("/")
        url = f"{base_url}/{login_path}"

        response = requests.post(
            url,
            json={"username": username, "password": password},
            headers={"Content-Type": "application/json"},
            timeout=self.provider.metadata.get("timeout_seconds", 10),
        )
        response.raise_for_status()
        token = response.json()["token"]

        ttl = _jwt_expiry_ttl(token)
        try:
            cache.set(cache_key, token, timeout=ttl)
        except Exception:
            pass
        return token

    def authenticate(self) -> requests.Session:
        session = requests.Session()
        token = self._get_auth_token()
        session.headers["Authorization"] = f"Bearer {token}"
        return session

    def fetch(
        self,
        device: "void.Device",
        variable: str,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        endpoint = self.provider.get_endpoint("INGEST")
        if endpoint is None:
            return []

        base_url = (self.provider.base_url or "https://api.twindimension.com/tdata/v1").rstrip("/")
        path = (endpoint.path_template or "/telemetry/DEVICE/{external_id}/values/timeseries").lstrip("/")
        url = f"{base_url}/{path.format(external_id=device.external_id, variable=variable)}"

        params = {}
        for key, template in (endpoint.query_params or {}).items():
            params[key] = template.format(
                variable=variable,
                external_id=device.external_id or "",
                startTs=int(since.timestamp() * 1000) if since else "",
                endTs=int(until.timestamp() * 1000) if until else "",
                limit=10000,
            )
        if not params:
            params = {"keys": variable}

        response = self.session.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        items = data.get(variable, [])
        results = []
        for item in items:
            ts_ms = item.get("ts")
            results.append({
                "value": item.get("value", 0),
                "timestamp": datetime.fromtimestamp(ts_ms / 1000, tz=dt_timezone.utc) if ts_ms else None,
                "unit": "",
                "payload": item,
            })
        return results
