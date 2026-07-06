"""Base adapter for compliance authorities."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass
class ComplianceResult:
    """Resultado de un intento de envío de cumplimiento."""

    success: bool = False
    status: str = "pending"  # pending/sent/confirmed/failed/duplicate/unrecoverable/retrying
    response_status: Optional[int] = None
    response_body: str = ""
    voucher: str = ""
    tracking_id: str = ""
    error_message: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)


class BaseComplianceAdapter:
    """Interfaz base para adaptadores de cumplimiento."""

    code: str = ""

    def __init__(self, authority):
        self.authority = authority

    def build_payload(
        self,
        profile,
        reading,
        aggregate_readings: Optional[list] = None,
    ) -> Dict[str, Any]:
        """Construye el payload a enviar. Debe implementar en subclases."""
        raise NotImplementedError

    def send(self, payload: Dict[str, Any]) -> ComplianceResult:
        """Envía el payload a la entidad. Debe implementar en subclases."""
        raise NotImplementedError

    def handle_response(self, response_status: int, response_body: str) -> ComplianceResult:
        """Interpreta la respuesta HTTP. Puede sobreescribirse."""
        return ComplianceResult(
            success=response_status == 200,
            status="confirmed" if response_status == 200 else "failed",
            response_status=response_status,
            response_body=response_body,
        )

    def format_timestamp(self, value: datetime) -> str:
        """Formatea timestamp sin Z para compatibilidad con APIs legacy."""
        if value is None:
            return ""
        return value.strftime("%Y-%m-%dT%H:%M:%S")
