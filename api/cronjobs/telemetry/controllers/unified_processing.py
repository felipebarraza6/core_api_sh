"""
CONTROLADORES UNIFICADOS PARA CRONJOBS DE TELEMETRÍA
=====================================================

Este archivo centraliza toda la lógica de procesamiento de variables para que
telemetry_unified.py (reemplaza cronjobs legacy)
usen exactamente la misma lógica robusta.

IMPORTANTE: Todos los cronjobs deben importar y usar estas funciones.
"""

import time
from datetime import datetime
from typing import Any, Dict, Optional

from api.core.models import InteractionDetail

# ✅ Logging estructurado
from api.cronjobs.utils.logging_config import telemetry_logger

# ✅ Timezone para Chile
import pytz
chile_tz = pytz.timezone('America/Santiago')


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
                telemetry_logger.error(f"Error después de {max_retries} intentos: {e}", exc_info=True)
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
        telemetry_logger.info(
            f"Punto {point_catchment_id} - {variable_type} '{variable_name}' procesada"
        )
    else:
        telemetry_logger.error(
            f"Punto {point_catchment_id} - Error en {variable_type} '{variable_name}': {error_msg}"
        )
        
        # ✅ ALERTA A GOOGLE CHAT
        try:
            from api.core.utils.google_chat import check_and_notify_error
            from api.core.models import CatchmentPoint
            
            # Necesitamos obtener info del punto para el mensaje
            # Como esto es solo en error, el query extra es aceptable
            point = CatchmentPoint.objects.select_related('project__client').filter(id=point_catchment_id).first()
            if point:
                p_name = point.title
                c_name = point.project.client.name if (point.project and point.project.client) else "N/A"
            else:
                p_name = f"ID {point_catchment_id}"
                c_name = "Unknown"
                
            check_and_notify_error(
                point_id=point_catchment_id,
                error_msg=f"{variable_type}: {error_msg}",
                point_name=p_name,
                client_name=c_name
            )
        except Exception as e:
            telemetry_logger.error(f"Error enviando alerta chat: {e}")


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
        telemetry_logger.error(f"Error validando frecuencia: {e}", exc_info=True)
        return True


def process_totalizado_variable(
    data: Dict[str, Any],
    variable: Dict[str, Any],
    point_catchment: Dict[str, Any],
    created_register: Dict[str, Any],
) -> tuple:
    """
    FUNCIÓN UNIFICADA para procesar variable de tipo TOTALIZADO (pulsos)
    
    Esta función centraliza TODA la lógica de procesamiento de totalizados para
    garantizar consistencia absoluta entre todos los cronjobs.

    Args:
        data: Datos obtenidos de la API
        variable: Configuración de la variable
        point_catchment: Datos del punto de captación
        created_register: Registro en construcción

    Returns:
        Tuple con (date_time_last_logger_total, created_register actualizado)
    """
    from .total import total_day, total_hour, total_m3

    # 1. VALIDAR Y CONVERTIR VALOR DE PULSOS
    try:
        value = int(float(data.get("value", 0)))
    except (ValueError, TypeError) as e:
        telemetry_logger.warning(f"Error convirtiendo valor {data.get('value')}: {e}")
        value = 0

    # 2. ASIGNAR PULSOS AL REGISTRO
    created_register["pulses"] = value

    # 3. CALCULAR TOTAL USANDO FÓRMULA UNIFICADA: (pulsos × factor) ÷ 1000
    pulses_factor = variable.get("pulses_factor", 1000)
    if not pulses_factor or pulses_factor <= 0:
        telemetry_logger.warning(f"Factor de pulsos no válido: {pulses_factor}, usando 1000")
        pulses_factor = 1000
    
    total_calculado = total_m3(pulses_factor, value, point_catchment)
    created_register["total"] = total_calculado

    # 4. CALCULAR DIFERENCIA POR HORA (consumo actual)
    current_dt = datetime.strptime(data["date_time"], "%Y-%m-%dT%H:%M:%S") if data.get("date_time") else datetime.now()
    total_diff = total_hour(created_register["total"], point_catchment, current_dt)
    created_register["total_diff"] = total_diff

    # 5. CALCULAR ACUMULADO DEL DÍA (✅ CORRECCIÓN: Pasar total, no diff)
    total_today_diff = total_day(point_catchment, current_dt, created_register["total"])
    created_register["total_today_diff"] = total_today_diff

    # 6. ASIGNAR TIMESTAMP DEL ÚLTIMO LOGGER
    if data.get("date_time"):
        created_register["date_time_last_logger"] = data["date_time"]
        date_time_last_logger_total = data["date_time"]
    else:
        # Fallback: Usar fecha de medición si el logger no envía fecha
        # Esto asegura que audits y history tengan fecha válida
        created_register["date_time_last_logger"] = created_register["date_time_medition"]
        date_time_last_logger_total = created_register["date_time_last_logger"]

    # 7. CALCULAR DÍAS SIN CONEXIÓN
    # CORRECCIÓN: Pasar point_catchment para poder buscar historial si falta info
    created_register = calculate_days_not_connection(created_register, chile_tz, point_catchment)

    # 8. LOGGING DE ÉXITO
    telemetry_logger.info(
        f"Punto {point_catchment['id']} - TOTALIZADO "
        f"'{variable.get('str_variable')}' procesado: "
        f"pulsos={value}, factor={pulses_factor}, "
        f"total={total_calculado}, diff_hora={total_diff}, "
        f"diff_dia={total_today_diff}"
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
            telemetry_logger.info(f"Nivel negativo corregido usando valor más alto: {nivel_value}")
        else:
            nivel_value = 0

    # Aplicar offset configurable del profile (reemplaza hardcodeo punto 149)
    nivel_offset = float(point_catchment.get("profile_data_config", {}).get("nivel_offset", 0) or 0)
    nivel_con_offset = float(nivel_value) + nivel_offset
    created_register["nivel"] = nivel_mt(
        nivel_con_offset,
        variable.get("calculate_nivel"),
        point_catchment["id"],
        point_catchment["profile_data_config"].get("d3", 0)
    )

    # Validar d3 antes de calcular nivel freático
    d3 = point_catchment["profile_data_config"].get("d3", 0)
    if not d3 or float(d3 if d3 else 0) <= 0:
        telemetry_logger.warning(f"Error: d3 no válido para punto {point_catchment['id']}")
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
    variable: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Procesar variable de tipo CAUDAL_PROMEDIO

    Args:
        date_time_last_logger_total: Timestamp del último totalizado
        created_register: Registro en construcción
        point_catchment: Datos del punto de captación
        variable: Configuración de la variable (opcional, para leer store_average_flow)

    Returns:
        created_register actualizado
    """
    store_flow = variable.get("store_average_flow", False) if variable else False

    if store_flow and date_time_last_logger_total and created_register.get("total") is not None:
        from .flow import average_flow
        try:
            dt_lg = datetime.strptime(date_time_last_logger_total, "%Y-%m-%dT%H:%M:%S")
            created_register["flow"] = average_flow(
                point_catchment,
                created_register["total"],
                dt_lg,
            )
        except Exception as e:
            telemetry_logger.warning(f"Error calculando caudal promedio para punto {point_catchment['id']}: {e}")

    log_variable_processing(
        point_catchment["id"],
        variable.get("str_variable", "CAUDAL_PROMEDIO") if variable else "CAUDAL_PROMEDIO",
        "CAUDAL_PROMEDIO",
        True,
    )

    return created_register


def _validate_variable_range(
    variable: Dict[str, Any],
    raw_value: float,
    point_catchment: Dict[str, Any],
    created_register: Dict[str, Any],
) -> bool:
    """
    Valida que el valor crudo esté dentro del rango min/max configurado.
    Si está fuera de rango, marca is_error=True en el registro y loguea.

    Returns:
        True si pasó validación (o no hay rango configurado), False si falló.
    """
    min_val = variable.get("min_value")
    max_val = variable.get("max_value")

    if min_val is None and max_val is None:
        return True

    try:
        val = float(raw_value)
    except (ValueError, TypeError):
        return True  # No validamos si no es numérico

    if min_val is not None and val < float(min_val):
        telemetry_logger.warning(
            f"[VALIDACION] Punto {point_catchment['id']} - {variable.get('str_variable')}: "
            f"valor {val} < mínimo {min_val}"
        )
        created_register["is_error"] = True
        return False

    if max_val is not None and val > float(max_val):
        telemetry_logger.warning(
            f"[VALIDACION] Punto {point_catchment['id']} - {variable.get('str_variable')}: "
            f"valor {val} > máximo {max_val}"
        )
        created_register["is_error"] = True
        return False

    return True


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

    # Validación de calidad: rango min/max
    raw_value = data.get("value")
    if raw_value is not None:
        _validate_variable_range(variable, raw_value, point_catchment, created_register)

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
                date_time_last_logger_total, created_register, point_catchment, variable
            )

        else:
            telemetry_logger.warning(f"Tipo de variable inválido: {type_variable}")
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
    created_register: Dict[str, Any], chile_tz: Any, point_catchment: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Calcular días sin conexión.
    Si no hay date_time_last_logger, busca el último registro válido en BD.
    
    Args:
        created_register: Registro en construcción
        chile_tz: Zona horaria
        point_catchment: Info del punto para búsquedas históricas
    """
    current_dt = datetime.now(chile_tz)
    
    if created_register.get("date_time_last_logger"):
        # CASO 1: Tenemos timestamp del logger
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
            
    elif point_catchment and point_catchment.get('id'):
        # CASO 2: No hay timestamp (ej. sensor enviando 0s), buscar último dato válido en BD
        try:
            # Buscar último registro que NO tenga total=0 o que tenga un logger stamp válido
            ultimo_valido = InteractionDetail.objects.filter(
                catchment_point_id=point_catchment['id']
            ).exclude(date_time_last_logger__isnull=True).order_by('-created').first()
            
            if ultimo_valido and ultimo_valido.created:
                # Calcular días desde ese último registro válido
                days = (current_dt - ultimo_valido.created.astimezone(chile_tz)).days
                created_register["days_not_conection"] = max(0, days)
                
                # Opcional: Si el último válido fue hace mucho, inyectar el timestamp antiguo
                # para que se vea en el frontend
                if days > 1 and ultimo_valido.date_time_last_logger:
                     created_register["date_time_last_logger"] = str(ultimo_valido.date_time_last_logger)
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
        telemetry_logger.error(f"Error determinando envío a DGA: {e}", exc_info=True)
        return False
