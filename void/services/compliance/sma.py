"""SMA compliance adapter for void."""
import json

import requests

from void.models import ProcessedReading

from .base import BaseComplianceAdapter, ComplianceResult
from .registry import ComplianceAdapterRegistry


@ComplianceAdapterRegistry.register("sma")
class SMAComplianceAdapter(BaseComplianceAdapter):
    """Adaptador para envío de mediciones a SMA (conexiones.sma.gob.cl)."""

    code = "sma"

    def _get_token(self) -> str:
        """Obtiene token de autenticación desde endpoint /auth de SMA."""
        base_url = self.authority.base_url or "https://conexiones.sma.gob.cl/api/v1"
        url = f"{base_url.rstrip('/')}/auth"

        payload = self.authority.get_auth_payload() or {
            "usuario": self.authority.auth_username,
            "password": self.authority.auth_password,
        }
        headers = {"Content-Type": "application/json"}

        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=self.authority.timeout_seconds or 30,
        )
        response.raise_for_status()
        data = response.json()
        token = data.get("token")
        if not token:
            raise ValueError("No se encontró token en respuesta SMA")
        return token

    def build_payload(
        self,
        profile,
        reading,
        aggregate_readings=None,
    ) -> dict:
        """Construye payload SMA.

        SMA filtra registros cuyo minuto sea múltiplo de 5. Esa validación
        se hace en el servicio antes de llamar al adapter.
        """
        return {
            "device_id": profile.external_code or profile.point.code_internal or str(profile.point_id),
            "timestamp": self.format_timestamp(reading.timestamp),
            "flow": float(profile.resolve_value(reading, "flow") or 0),
            "total": float(profile.resolve_value(reading, "total") or 0),
        }

    def send(self, payload: dict) -> ComplianceResult:
        """Envía payload a SMA."""
        base_url = self.authority.base_url or "https://conexiones.sma.gob.cl/api/v1"
        url = f"{base_url.rstrip('/')}/mediciones"

        token = self._get_token()
        protocol_config = self.authority.protocol_config or {}
        token_prefix = protocol_config.get("token_prefix", "Bearer")
        token_header = protocol_config.get("token_header", "Authorization")

        headers = {
            "Content-Type": "application/json",
            token_header: f"{token_prefix} {token}".strip(),
        }

        last_exception = None
        for attempt in range(self.authority.retry_attempts or 1):
            try:
                response = requests.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=self.authority.timeout_seconds or 30,
                )
                return self.handle_response(response.status_code, response.text)
            except requests.RequestException as exc:
                last_exception = exc
                continue

        return ComplianceResult(
            success=False,
            status="failed",
            response_body=str(last_exception) if last_exception else "",
            error_message=f"Error de conexión tras {self.authority.retry_attempts} intentos",
        )

    def handle_response(self, response_status: int, response_body: str) -> ComplianceResult:
        """Interpreta respuesta SMA."""
        if response_status in (200, 201):
            tracking_id = ""
            try:
                data = json.loads(response_body)
                tracking_id = data.get("id_verificacion") or data.get("id") or ""
            except Exception:
                pass
            return ComplianceResult(
                success=True,
                status="confirmed",
                response_status=response_status,
                response_body=response_body,
                tracking_id=str(tracking_id),
            )

        return ComplianceResult(
            success=False,
            status="failed",
            response_status=response_status,
            response_body=response_body,
            error_message=f"HTTP {response_status}",
        )
