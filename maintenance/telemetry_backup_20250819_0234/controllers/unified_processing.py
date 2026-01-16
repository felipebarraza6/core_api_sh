"""
CONTROLADORES UNIFICADOS PARA CRONJOBS DE TELEMETRÍA
=====================================================

Este archivo centraliza toda la lógica de procesamiento de variables para que
todos los cronjobs (twin.py, twin_f1.py, twin_f5.py, nettra.py, novus.py)
usen exactamente la misma lógica robusta.

IMPORTANTE: Todos los cronjobs deben importar y usar estas funciones.
"""

import time
from datetime import datetime
from typing import Any, Dict, Optional

from api.core.models import InteractionDetail


def get_data_with_retry(getter_func, *args, max_retries=3, backoff_factor=2):
    """
    Retry inteligente con backoff exponencial para obtener datos de APIs

    Args:
        getter_func: Función getter a ejecutar
        *args: Argumentos para la función
        max_retries: Número máximo de intentos
        backoff_factor: Factor de espera exponencial

    Returns:
        Dict con datos o None si falla
    """
    for attempt in range(max_retries):
        try:
            data = getter_func(*args)
            if data and data.get("value") is not None:
                return data
        except Exception as e:
            if attempt == max_retries - 1:
                print(f"Error después de {max_retries} intentos: {e}")
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
    Logging estructurado para debugging de procesamiento de variables

    Args:
        point_catchment_id: ID del punto de captación
        variable_name: Nombre de la variable
        variable_type: Tipo de variable (TOTALIZADO, NIVEL, CAUDAL, etc.)
        success: Si el procesamiento fue exitoso
        error_msg: Mensaje de error si falló
    """
    if success:
        print(
            f"✅ Punto {point_catchment_id} - {variable_type} '{variable_name}' procesada"
        )
    else:
        print(
            f"❌ Punto {point_catchment_id} - Error en {variable_type} '{variable_name}': {error_msg}"
        )


def validate_frequency(point_catchment: Dict[str, Any], current_time: datetime) -> bool:
    """
    Validar si debe procesar según estándar DGA

    Args:
        point_catchment: Datos del punto de captación
        current_time: Tiempo actual

    Returns:
        True si debe procesar, False si no
    """
    try:
        from api.core.models import DgaDataConfigCatchment

        get = DgaDataConfigCatchment.objects.get(
            point_catchment__id=point_catchment["id"]
        )
        standard = get.standard

        if standard == "MAYOR":
            return current_time.minute == 0  # Cada hora
        elif standard == "MEDIO":
            return current_time.hour == 0 and current_time.minute == 0  # Diario
        elif standard == "MENOR":
            return (
                current_time.day == 1
                and current_time.hour == 0
                and current_time.minute == 0
            )  # Mensual
        elif standard == "CAUDALES_MUY_PEQUENOS":
            return (
                current_time.month in [1, 7]
                and current_time.day == 1
                and current_time.hour == 0
                and current_time.minute == 0
            )  # Semestral

        return True  # SIN_ESTANDAR siempre procesa
    except Exception as e:
        print(f"Error validando frecuencia: {e}")
        return True


def process_totalizado_variable(
    data: Dict[str, Any],
    variable: Dict[str, Any],
    point_catchment: Dict[str, Any],
    created_register: Dict[str, Any],
) -> tuple:
    """
    Procesar variable de tipo TOTALIZADO (pulsos)

    Args:
        data: Datos obtenidos de la API
        variable: Configuración de la variable
        point_catchment: Datos del punto de captación
        created_register: Registro en construcción

    Returns:
        Tuple con (date_time_last_logger_total, created_register actualizado)
    """
    from .total import total_day, total_hour, total_m3

    # Validar conversión segura
    try:
        value = int(float(data["value"]))
    except (ValueError, TypeError) as e:
        print(f"Error convirtiendo {data['value']}: {e}")
        value = 0

    created_register["pulses"] = value

    # ✅ FÓRMULA CORRECTA: (pulsos * factor) / 1000
    created_register["total"] = total_m3(
        variable.get("pulses_factor"), value, point_catchment
    )

    # ✅ DIFERENCIA POR HORA (consumo actual)
    created_register["total_diff"] = total_hour(
        created_register["total"], point_catchment
    )

    # ✅ ACUMULADO DEL DÍA
    created_register["total_today_diff"] = total_day(
        created_register["total"], point_catchment
    )

    created_register["date_time_last_logger"] = data["date_time"]
    date_time_last_logger_total = data["date_time"]

    log_variable_processing(
        point_catchment["id"],
        variable.get("str_variable"),
        "TOTALIZADO",
        True,
    )

    return date_time_last_logger_total, created_register


def process_nivel_variable(
    data: Dict[str, Any],
    variable: Dict[str, Any],
    point_catchment: Dict[str, Any],
    created_register: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Procesar variable de tipo NIVEL

    Args:
        data: Datos obtenidos de la API
        variable: Configuración de la variable
        point_catchment: Datos del punto de captación
        created_register: Registro en construcción

    Returns:
        created_register actualizado
    """
    from .nivel import nivel_mt, water_table

    # Manejar nivel negativo
    try:
        nivel_value = float(data["value"])
    except (ValueError, TypeError):
        nivel_value = 0

    if nivel_value < 0:
        # Buscar nivel más alto registrado
        nivel_mas_alto = (
            InteractionDetail.objects.filter(catchment_point_id=point_catchment["id"])
            .exclude(nivel__isnull=True)
            .order_by("-nivel")
            .first()
        )

        if nivel_mas_alto:
            nivel_value = nivel_mas_alto.nivel
            print(f"Nivel negativo corregido usando valor más alto: {nivel_value}")
        else:
            nivel_value = 0

    # Caso especial para punto 149
    if point_catchment["id"] == 149:
        created_register["nivel"] = nivel_mt(
            float(nivel_value) - 17.0,
            variable.get("calculate_nivel"),
            point_catchment["id"],
        )
    else:
        created_register["nivel"] = nivel_mt(
            nivel_value,
            variable.get("calculate_nivel"),
            point_catchment["id"],
        )

    # Validar d3 antes de calcular nivel freático
    d3 = point_catchment["profile_data_config"].get("d3", 0)
    if not d3 or float(d3 if d3 else 0) <= 0:
        print(f"Error: d3 no válido para punto {point_catchment['id']}")
        d3 = 0

    created_register["water_table"] = water_table(created_register["nivel"], d3)
    created_register["date_time_last_logger"] = data["date_time"]

    log_variable_processing(
        point_catchment["id"], variable.get("str_variable"), "NIVEL", True
    )

    return created_register


def process_caudal_variable(
    data: Dict[str, Any],
    variable: Dict[str, Any],
    point_catchment: Dict[str, Any],
    created_register: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Procesar variable de tipo CAUDAL (instantáneo)

    Args:
        data: Datos obtenidos de la API
        variable: Configuración de la variable
        point_catchment: Datos del punto de captación
        created_register: Registro en construcción

    Returns:
        created_register actualizado
    """
    from .flow import instantaneous_flow

    created_register["flow"] = instantaneous_flow(
        data["value"], variable.get("convert_to_lt"), variable.get("calculate_nivel")
    )
    created_register["date_time_last_logger"] = data["date_time"]

    log_variable_processing(
        point_catchment["id"], variable.get("str_variable"), "CAUDAL", True
    )

    return created_register


def process_caudal_promedio_variable(
    date_time_last_logger_total: str,
    created_register: Dict[str, Any],
    point_catchment: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Procesar variable de tipo CAUDAL_PROMEDIO

    Args:
        date_time_last_logger_total: Timestamp del último totalizado
        created_register: Registro en construcción
        point_catchment: Datos del punto de captación

    Returns:
        created_register actualizado
    """
    from .flow import average_flow

    if date_time_last_logger_total:
        created_register["flow"] = average_flow(
            point_catchment,
            created_register["total"],
            datetime.strptime(date_time_last_logger_total, "%Y-%m-%dT%H:%M:%S"),
        )

    log_variable_processing(
        point_catchment["id"],
        "CAUDAL_PROMEDIO",
        "CAUDAL_PROMEDIO",
        True,
    )

    return created_register


def process_variable_safely(
    variable: Dict[str, Any],
    data: Dict[str, Any],
    point_catchment: Dict[str, Any],
    created_register: Dict[str, Any],
    date_time_last_logger_total: Optional[str] = None,
) -> tuple:
    """
    Procesar variable de forma segura con manejo de errores

    Args:
        variable: Configuración de la variable
        data: Datos obtenidos de la API
        point_catchment: Datos del punto de captación
        created_register: Registro en construcción
        date_time_last_logger_total: Timestamp del último totalizado

    Returns:
        Tuple con (date_time_last_logger_total, created_register actualizado)
    """
    type_variable = variable.get("type_variable")

    try:
        if type_variable == "TOTALIZADO":
            date_time_last_logger_total, created_register = process_totalizado_variable(
                data, variable, point_catchment, created_register
            )

        elif type_variable == "NIVEL":
            created_register = process_nivel_variable(
                data, variable, point_catchment, created_register
            )

        elif type_variable == "CAUDAL":
            created_register = process_caudal_variable(
                data, variable, point_catchment, created_register
            )

        elif type_variable == "CAUDAL_PROMEDIO":
            created_register = process_caudal_promedio_variable(
                date_time_last_logger_total, created_register, point_catchment
            )

        else:
            print("Invalid type_variable")
            log_variable_processing(
                point_catchment["id"],
                variable.get("str_variable"),
                "DESCONOCIDO",
                False,
                "Tipo de variable inválido",
            )

    except Exception as e:
        log_variable_processing(
            point_catchment["id"],
            variable.get("str_variable"),
            type_variable,
            False,
            str(e),
        )

    return date_time_last_logger_total, created_register


def calculate_days_not_connection(
    created_register: Dict[str, Any], chile_tz: Any
) -> Dict[str, Any]:
    """
    Calcular días sin conexión

    Args:
        created_register: Registro en construcción
        chile_tz: Zona horaria de Chile

    Returns:
        created_register actualizado
    """
    if created_register.get("date_time_last_logger"):
        date_time_medition = datetime.now(chile_tz).strftime("%Y-%m-%dT%H:%M:00")
        date_time_last_logger = created_register["date_time_last_logger"]

        try:
            date_time_medition = datetime.strptime(
                date_time_medition, "%Y-%m-%dT%H:%M:00"
            )
            date_time_last_logger = datetime.strptime(
                date_time_last_logger, "%Y-%m-%dT%H:%M:%S"
            )
            days_not_conection = (date_time_medition - date_time_last_logger).days
            if days_not_conection < 0:
                days_not_conection = 0
            created_register["days_not_conection"] = days_not_conection
        except Exception as e:
            print(f"Error calculando días sin conexión: {e}")
            created_register["days_not_conection"] = 0

    return created_register


def determine_dga_send(point_catchment: Dict[str, Any], chile_tz: Any) -> bool:
    """
    Determinar si debe enviar datos a DGA

    Args:
        point_catchment: Datos del punto de captación
        chile_tz: Zona horaria de Chile

    Returns:
        True si debe enviar, False si no
    """
    from api.core.models import DgaDataConfigCatchment

    try:
        get = DgaDataConfigCatchment.objects.get(
            point_catchment__id=point_catchment["id"]
        )
        current_time = datetime.now(chile_tz)

        # Solo enviar a DGA si está habilitado Y corresponde la frecuencia
        return get.send_dga and validate_frequency(point_catchment, current_time)
    except Exception as e:
        print(f"Error determinando envío a DGA: {e}")
        return False
