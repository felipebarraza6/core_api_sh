"""
Getter universal de telemetría.

Soporta handlers específicos para retrocompatibilidad (tdata, thethings, tago)
y un parser genérico JSON configurable para proveedores nuevos sin tocar código.
"""

from .tdata import get_data_tdata
from .thingsio import get_data_thethings
from .tago import get_data_tago
from .generic import get_data_generic


def get_data_universal(provider, token_service, str_variable):
    """
    Obtener datos de telemetría usando el handler configurado en el proveedor.

    Args:
        provider: dict o instancia de TelemetryProvider (puede ser None)
        token_service: token del dispositivo/punto
        str_variable: nombre de la variable

    Returns:
        dict con {"value": ..., "date_time": ...} o {"value": 0, "date_time": None}
    """
    if not provider:
        # Fallback legacy: usa TDATA como default (mantener retrocompatibilidad)
        return get_data_tdata(None, token_service, str_variable)

    # Extraer handler_name sea dict u objeto
    handler_name = provider.get("handler_name") if isinstance(provider, dict) else getattr(provider, "handler_name", None)

    if handler_name == "tdata":
        return get_data_tdata(provider, token_service, str_variable)
    elif handler_name == "thethings":
        return get_data_thethings(provider, token_service, str_variable)
    elif handler_name == "tago":
        return get_data_tago(provider, token_service, str_variable)
    else:
        return get_data_generic(provider, token_service, str_variable)
