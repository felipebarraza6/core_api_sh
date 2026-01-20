# -*- coding: utf-8 -*-
"""
Shared utilities for telemetry processing.
Extracted from unified_processing.py for modularity.
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional
import pytz
import re

# ✅ Timezone configuration
chile_tz = pytz.timezone("America/Santiago")

# ✅ Structured Logging
telemetry_logger = logging.getLogger(__name__)

def get_data_with_retry(getter_func, *args, max_retries=3, backoff_factor=2):
    """
    Intelligent retry with exponential backoff for API data retrieval.
    """
    import time
    for attempt in range(max_retries):
        try:
            data = getter_func(*args)
            if data and data.get("value") is not None:
                return data
        except Exception as e:
            if attempt == max_retries - 1:
                telemetry_logger.error(
                    f"Error después de {max_retries} intentos: {e}", exc_info=True
                )
                return None
            time.sleep(backoff_factor**attempt)
    return None

def log_variable_processing(
    point_catchment_id: int,
    variable_name: str,
    variable_type: str,
    success: bool = True,
    error_msg: Optional[str] = None,
):
    """
    Structured logging for variable processing debugging and Google Chat alerts.
    """
    if success:
        telemetry_logger.info(
            f"Punto {point_catchment_id} - {variable_type} '{variable_name}' procesada"
        )
    else:
        telemetry_logger.error(
            f"Punto {point_catchment_id} - Error en {variable_type} '{variable_name}': {error_msg}"
        )

        # ✅ GOOGLE CHAT ALERT
        try:
            from api.telemetry.models import CatchmentPoint
            from api.core.utils.google_chat import check_and_notify_error

            point = (
                CatchmentPoint.objects.select_related("project__client")
                .filter(id=point_catchment_id)
                .first()
            )
            if point:
                p_name = point.title
                c_name = (
                    point.project.client.name
                    if (point.project and point.project.client)
                    else "N/A"
                )
            else:
                p_name = f"ID {point_catchment_id}"
                c_name = "Unknown"

            check_and_notify_error(
                point_id=point_catchment_id,
                error_msg=f"{variable_type}: {error_msg}",
                point_name=p_name,
                client_name=c_name,
            )
        except Exception as e:
            telemetry_logger.error(f"Error enviando alerta chat: {e}")

def validate_frequency(point_catchment: Dict[str, Any], current_time: datetime) -> bool:
    """
    Validate if processing should occur based on DGA standard.
    """
    try:
        from api.telemetry.models import DgaDataConfigCatchment
        config = DgaDataConfigCatchment.objects.get(
            point_catchment__id=point_catchment["id"]
        )
        standard = config.standard

        if standard == "MAYOR":
            return current_time.minute == 0
        elif standard == "MEDIO":
            return current_time.hour == 0 and current_time.minute == 0
        elif standard == "MENOR":
            return (
                current_time.day == 1
                and current_time.hour == 0
                and current_time.minute == 0
            )
        elif standard == "CAUDALES_MUY_PEQUENOS":
            return (
                current_time.month in [1, 7]
                and current_time.day == 1
                and current_time.hour == 0
                and current_time.minute == 0
            )

        return True  # SIN_ESTANDAR always processes
    except Exception as e:
        telemetry_logger.error(f"Error validando frecuencia: {e}", exc_info=True)
        return True

def calculate_days_not_connection(
    created_register: Dict[str, Any],
    chile_tz: Any,
    point_catchment: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """
    Calculate days without connection.
    """
    from api.telemetry.models import TelemetryRecord
    current_dt = datetime.now(chile_tz)

    if created_register.get("date_time_last_logger"):
        date_time_medition_str = current_dt.strftime("%Y-%m-%dT%H:%M:00")
        date_time_last_logger_str = created_register["date_time_last_logger"]

        try:
            dt_med = datetime.strptime(date_time_medition_str, "%Y-%m-%dT%H:%M:00")
            dt_log = datetime.strptime(date_time_last_logger_str, "%Y-%m-%dT%H:%M:%S")

            days = (dt_med - dt_log).days
            created_register["days_not_conection"] = max(0, days)
        except Exception as e:
            telemetry_logger.error(f"Error calculando días con timestamp: {e}")
            created_register["days_not_conection"] = 0

    elif point_catchment and point_catchment.get("id"):
        try:
            ultimo_valido = (
                TelemetryRecord.objects.filter(point_id=point_catchment["id"])
                .order_by("-timestamp")
                .first()
            )

            if ultimo_valido:
                days = (current_dt - ultimo_valido.timestamp.astimezone(chile_tz)).days
                created_register["days_not_conection"] = max(0, days)

                last_ts = ultimo_valido.metadata.get("last_logger_timestamp")
                if days > 1 and last_ts:
                    created_register["date_time_last_logger"] = last_ts
            else:
                created_register["days_not_conection"] = 0
        except Exception as e:
            telemetry_logger.error(f"Error fallback días sin conexión: {e}")
            created_register["days_not_conection"] = 0
    else:
        created_register["days_not_conection"] = 0

    return created_register

def determine_dga_send(point_catchment: Dict[str, Any], chile_tz: Any) -> bool:
    """
    Determine if data should be sent to DGA.
    """
    try:
        from api.telemetry.models import DgaDataConfigCatchment
        config = DgaDataConfigCatchment.objects.get(
            point_catchment__id=point_catchment["id"]
        )
        current_time = datetime.now(chile_tz)
        return config.send_dga and validate_frequency(point_catchment, current_time)
    except Exception as e:
        telemetry_logger.error(f"Error determinando envío a DGA: {e}", exc_info=True)
        return False

def evaluate_dynamic_formula(formula: str, context: Dict[str, Any]) -> float:
    """
    Evaluates a dynamic formula replacing {internal_code} with values from context.
    Use this to execute user-defined rules from the database.

    Args:
        formula: String like "({v1} + {v2}) * 0.5"
        context: Dict mapping internal_code to current values

    Returns:
        float: Result of calculation or 0.0 if error
    """
    if not formula:
        return 0.0

    processed_formula = formula
    # Find all {var} patterns
    tokens = re.findall(r"\{([a-zA-Z0-9_]+)\}", formula)

    # Sort tokens by length descending to avoid partial replacement issues (e.g. {v1} and {v11})
    tokens = sorted(list(set(tokens)), key=len, reverse=True)

    for token in tokens:
        # Get value from context, fallback to 0 if not found
        # We try to convert to float to be safe
        try:
            val = float(context.get(token, 0))
        except (ValueError, TypeError):
            val = 0.0
        processed_formula = processed_formula.replace(f"{{{token}}}", str(val))

    # Whitelist characters for security (allow numbers, operators, dots, parens, spaces)
    # We also allow scientific notation e.g. 1e-5
    if not re.match(r"^[0-9\.\+\-\*\/\(\)\s eE]+$", processed_formula):
        telemetry_logger.error(
            f"Formula contains insecure characters after processing: {processed_formula} (Original: {formula})"
        )
        return 0.0

    try:
        # Evaluate safely without builtins
        # Note: eval is generally discouraged, but here we have a strict whitelist regex check above.
        result = eval(processed_formula, {"__builtins__": {}})
        return float(result)
    except ZeroDivisionError:
        telemetry_logger.warning(f"Division by zero in formula: {formula}")
        return 0.0
    except Exception as e:
        telemetry_logger.error(f"Error evaluating formula '{formula}' (processed: '{processed_formula}'): {e}")
        return 0.0
