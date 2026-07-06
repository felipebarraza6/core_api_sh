"""Base provider and dynamic HTTP provider for void telemetry."""
from abc import ABC, abstractmethod
from datetime import datetime, timezone as dt_timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode, urljoin

import requests


class BaseProvider(ABC):
    """Clase base para proveedores de telemetría.

    Los proveedores concretos pueden heredar de esta clase o simplemente
    usar ProviderConfiguration + IngestService para APIs dinámicas.
    """

    name: str = ""

    def __init__(self, provider: "void.Provider"):
        self.provider = provider
        self._session: Optional[requests.Session] = None

    @property
    def session(self) -> requests.Session:
        if self._session is None:
            self._session = self.authenticate()
        return self._session

    @abstractmethod
    def authenticate(self) -> requests.Session:
        """Retorna una sesión requests autenticada (o no)."""
        ...

    @abstractmethod
    def fetch(
        self,
        device: "void.Device",
        variable: str,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """Consulta el proveedor y retorna lista de lecturas crudas."""
        ...

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} provider={self.provider}>"


class DynamicHttpProvider(BaseProvider):
    """Proveedor HTTP genérico que usa ProviderEndpoint para armar requests.

    No requiere código nuevo por cada API: solo crear el proveedor, sus
    endpoints y su parser de respuesta desde el admin.

    Soporta autenticación a nivel proveedor y por dispositivo (usando
    placeholders como {external_id} en auth_config).
    """

    name = "dynamic_http"

    def authenticate(self) -> requests.Session:
        session = requests.Session()
        auth_config = self.provider.auth_config or {}

        if self.provider.auth_type == "NONE":
            return session

        if self.provider.auth_type == "BASIC":
            session.auth = (auth_config.get("username", ""), auth_config.get("password", ""))
            return session

        if self.provider.auth_type in ("BEARER", "API_KEY_HEADER"):
            token = auth_config.get("token") or auth_config.get("api_key", "")
            header_name = auth_config.get("header_name", "Authorization")
            if header_name.lower() == "authorization" and self.provider.auth_type == "BEARER":
                session.headers[header_name] = f"Bearer {token}"
            else:
                session.headers[header_name] = token
            return session

        if self.provider.auth_type == "API_KEY_QUERY":
            # Se aplica en cada request via params.
            return session

        if self.provider.auth_type.startswith("OAUTH2"):
            # Placeholder: OAuth2 requiere lógica específica de refresh.
            token = auth_config.get("access_token", "")
            session.headers["Authorization"] = f"Bearer {token}"
            return session

        return session

    def fetch(
        self,
        device: "void.Device",
        variable: str,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """Ejecuta el endpoint INGEST del proveedor."""
        endpoint = self.provider.get_endpoint("INGEST")
        if endpoint is None:
            return []

        url = self._build_url(endpoint, device, variable, since, until)
        params = self._build_query_params(endpoint, device, variable, since, until)
        headers = {**(endpoint.headers or {})}

        # Auth por dispositivo (p.ej. Tago.io usa token = external_id).
        headers.update(self._build_auth_headers(device))
        params.update(self._build_auth_params(device))

        response = self.session.request(
            method=endpoint.http_method,
            url=url,
            params=params if params else None,
            headers=headers,
            timeout=self.provider.metadata.get("timeout_seconds", 10),
        )
        response.raise_for_status()

        payload = response.json()
        return self._parse_payload(payload, endpoint.response_parser or {})

    def _device_context(
        self,
        device: "void.Device",
        variable: str,
        since: Optional[datetime],
        until: Optional[datetime],
    ) -> Dict[str, Any]:
        """Contexto disponible para templates de URL, query y auth."""
        return {
            "base_url": (self.provider.base_url or "").rstrip("/"),
            "external_id": device.external_id or "",
            "variable": variable,
            "serial": device.serial_number or "",
            "startTs": self._to_epoch_ms(since) if since else "",
            "endTs": self._to_epoch_ms(until) if until else "",
            "start_date": self._to_iso_utc(since) if since else "",
            "end_date": self._to_iso_utc(until) if until else "",
            "limit": 10000,
        }

    def _build_url(
        self,
        endpoint,
        device: "void.Device",
        variable: str,
        since: Optional[datetime],
        until: Optional[datetime],
    ) -> str:
        base = (self.provider.base_url or "").rstrip("/")
        path = endpoint.path_template or ""
        ctx = self._device_context(device, variable, since, until)
        path = path.format(**ctx)
        return urljoin(base + "/", path.lstrip("/"))

    def _build_query_params(
        self,
        endpoint,
        device: "void.Device",
        variable: str,
        since: Optional[datetime],
        until: Optional[datetime],
    ) -> Dict[str, Any]:
        ctx = self._device_context(device, variable, since, until)
        params = {}
        for key, template in (endpoint.query_params or {}).items():
            params[key] = template.format(**ctx)
        return params

    def _build_auth_headers(self, device: "void.Device") -> Dict[str, str]:
        """Headers de auth con soporte a placeholders por dispositivo."""
        if self.provider.auth_type not in ("BEARER", "API_KEY_HEADER"):
            return {}

        auth_config = self.provider.auth_config or {}
        ctx = self._device_context(device, "", None, None)
        token_template = auth_config.get("token") or auth_config.get("api_key", "")
        token = token_template.format(**ctx)
        header_name = auth_config.get("header_name", "Authorization")

        if self.provider.auth_type == "BEARER" and header_name.lower() == "authorization":
            return {header_name: f"Bearer {token}"}
        return {header_name: token}

    def _build_auth_params(self, device: "void.Device") -> Dict[str, str]:
        """Query params de auth con soporte a placeholders por dispositivo."""
        if self.provider.auth_type != "API_KEY_QUERY":
            return {}

        auth_config = self.provider.auth_config or {}
        ctx = self._device_context(device, "", None, None)
        key_name = auth_config.get("key_name", "api_key")
        value_template = auth_config.get("api_key", "")
        return {key_name: value_template.format(**ctx)}

    def _parse_payload(self, payload: Any, parser_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Parsea payload según parser_config.

        Soporta:
        - response_is_array=True
        - response_root_key
        - value_field, timestamp_field, unit_field
        - timestamp_format: iso, epoch_ms, epoch_s
        """
        root_key = parser_config.get("response_root_key")
        if root_key:
            payload = payload.get(root_key, payload)

        if parser_config.get("response_is_array"):
            items = payload if isinstance(payload, list) else []
        else:
            items = [payload] if isinstance(payload, dict) else []

        value_field = parser_config.get("value_field", "value")
        timestamp_field = parser_config.get("timestamp_field", "timestamp")
        unit_field = parser_config.get("unit_field", "unit")
        ts_format = parser_config.get("timestamp_format", "iso")

        results = []
        for item in items:
            if not isinstance(item, dict):
                continue
            results.append({
                "value": item.get(value_field),
                "timestamp": self._parse_timestamp(item.get(timestamp_field), ts_format),
                "unit": item.get(unit_field, ""),
                "payload": item,
            })
        return results

    @staticmethod
    def _to_epoch_ms(dt: datetime) -> int:
        return int(dt.timestamp() * 1000)

    @staticmethod
    def _to_iso_utc(dt: datetime) -> str:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=dt_timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")

    @staticmethod
    def _parse_timestamp(value: Any, fmt: str) -> Optional[datetime]:
        from django.utils import timezone
        if value is None:
            return None
        if fmt == "epoch_ms":
            return timezone.datetime.fromtimestamp(value / 1000, tz=timezone.utc)
        if fmt == "epoch_s":
            return timezone.datetime.fromtimestamp(value, tz=timezone.utc)
        if fmt == "iso" and isinstance(value, str):
            from django.utils.dateparse import parse_datetime
            return parse_datetime(value)
        return None
