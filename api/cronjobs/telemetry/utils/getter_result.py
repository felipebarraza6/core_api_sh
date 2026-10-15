"""
Contrato de respuesta de getters de telemetría.

Distingue:
- ok: medición real con valor y timestamp
- no_data: el proveedor respondió OK pero no tiene datos
- request_failed: fallo de red/HTTP/timeout (NO inventar value=0)
"""

from typing import Any, Dict, Optional

STATUS_OK = "ok"
STATUS_NO_DATA = "no_data"
STATUS_REQUEST_FAILED = "request_failed"


def ok_result(value: Any, date_time: Optional[str]) -> Dict[str, Any]:
    """Medición válida del proveedor."""
    return {"value": value, "date_time": date_time, "status": STATUS_OK}


def no_data_result() -> Dict[str, Any]:
    """El proveedor respondió pero no hay datos para la variable."""
    return {"value": None, "date_time": None, "status": STATUS_NO_DATA}


def request_failed_result(
    error: Any = None,
    http_status: Optional[int] = None,
) -> Dict[str, Any]:
    """Fallo de la llamada (HTTP, timeout, excepción). Nunca inventa un 0."""
    result: Dict[str, Any] = {
        "value": None,
        "date_time": None,
        "status": STATUS_REQUEST_FAILED,
    }
    if error is not None:
        result["error"] = str(error)
    if http_status is not None:
        result["http_status"] = http_status
    return result


def is_getter_success(data: Optional[Dict[str, Any]]) -> bool:
    """True solo cuando hay timestamp válido y no es un fallo explícito."""
    if not data:
        return False
    status = data.get("status")
    if status in (STATUS_REQUEST_FAILED, STATUS_NO_DATA):
        return False
    return data.get("date_time") is not None


def http_status_from_exc(exc: BaseException) -> Optional[int]:
    """Extrae status HTTP de requests.HTTPError / RequestException si existe."""
    response = getattr(exc, "response", None)
    if response is not None:
        return getattr(response, "status_code", None)
    return None
