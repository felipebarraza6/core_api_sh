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
from api.cronjobs.telemetry.utils.audit import emit_system_event

# ✅ Timezone desde settings (elimina hardcode de pytz)
from django.utils import timezone
chile_tz = timezone.get_current_timezone()


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
            # Éxito: valor presente Y timestamp válido (date_time=None indica fallo de getter)
            if data and data.get("value") is not None and data.get("date_time") is not None:
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
        
        # ✅ ALERTA: el motor nuevo (AlertRule PROCESSING_ERROR) se encarga
        # de notificar errores de procesamiento. Ya no se usa check_and_notify_error.


def validate_frequency(point_catchment: Dict[str, Any], current_time: datetime, frequency: str = "60") -> bool:
    """
    Validar si debe procesar según estándar DGA.

    Args:
        point_catchment: Datos del punto de captación
        current_time: Tiempo actual
        frequency: Frecuencia de telemetría en minutos (default "60")

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
            return current_time.minute == 0  # Cada hora en punto
        elif standard == "MEDIO":
            return current_time.hour == 0 and current_time.minute == 0  # Diario medianoche
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
        elif standard == "SIN_ESTANDAR":
            # SIN_ESTANDAR asume MAYOR (estándar más exigente).
            # Enviar solo registros en punto (minuto 0).
            # Si el punto realmente es MEDIO/MENOR, la DGA no penaliza por enviar
            # con mayor frecuencia; solo ignora/rechaza duplicados.
            return current_time.minute == 0

        # Fallback seguro para estándares desconocidos
        telemetry_logger.warning(
            f"Estándar DGA desconocido '{standard}' para punto {point_catchment['id']}. "
            f"No se enviará a DGA."
        )
        return False
    except Exception as e:
        telemetry_logger.error(f"Error validando frecuencia: {e}", exc_info=True)
        return False


def process_totalizado_variable(
    data: Dict[str, Any],
    variable: Dict[str, Any],
    point_catchment: Dict[str, Any],
    created_register: Dict[str, Any],
    medition_str: Optional[str] = None,
    current_dt: Optional[datetime] = None,
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

    # Fecha de la medición actual (necesaria antes de total_m3 para logs y anti-salto)
    # FIX COHERENCIA: Usar medition_str (fecha del cronjob) como base para cálculos,
    # garantizando que total_day busque registros del mismo día que date_time_medition.
    if current_dt is None:
        if medition_str:
            current_dt = datetime.strptime(medition_str, "%Y-%m-%dT%H:%M:%S")
        elif data.get("date_time"):
            current_dt = datetime.strptime(data["date_time"], "%Y-%m-%dT%H:%M:%S")
        else:
            current_dt = datetime.now()
        # Asegurar que current_dt sea aware (offset-aware) para evitar crash al restar con datetimes de BD
        if current_dt.tzinfo is None:
            current_dt = timezone.make_aware(current_dt)

    # Pasar current_dt y frecuencia para logs precisos y anti-salto en reprocesamiento
    frecuency = point_catchment.get("frecuency") if isinstance(point_catchment, dict) else None
    try:
        frecuency_minutes = int(frecuency) if frecuency else None
    except (ValueError, TypeError):
        frecuency_minutes = None

    total_result = total_m3(
        pulses_factor, value, point_catchment,
        current_dt=current_dt, frecuency_minutes=frecuency_minutes,
        return_full_details=True
    )
    # total_m3 con return_full_details=True retorna (total, metadata)
    if isinstance(total_result, tuple) and len(total_result) == 2:
        total_calculado, total_meta = total_result
    else:
        total_calculado = total_result
        total_meta = None

    created_register["total"] = total_calculado

    # ✅ FIX: El anti-salto ya NO bloquea el total (solo loguea warning).
    # Este bloqueo causó efecto cascada catastrófico en producción.
    # Ahora solo se registra el evento y se acepta el valor real del sensor.
    # Mantenemos la metadata para trazabilidad pero NO marcamos is_error.
    if total_meta and total_meta.get("status") == "MASSIVE_JUMP_BLOCKED":
        telemetry_logger.warning(
            f"Punto {point_catchment['id']} - TOTALIZADO con salto masivo detectado. "
            f"Registro guardado con valor real del sensor (no bloqueado)."
        )

    # 4. CALCULAR DIFERENCIA POR HORA (consumo actual)
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

        # Guardar advertencia en variable_values para que quede en el historial
        # sin afectar is_error (reservado para errores de DGA/procesamiento)
        telemetry_logger.warning(
            f"[NIVEL] Punto {point_catchment['id']} - Nivel negativo ({data.get('value')}) "
            f"corregido a {nivel_value}."
        )
        # Agregar flag en variable_values para trazabilidad histórica
        if "variable_values" not in created_register:
            created_register["variable_values"] = {}
        created_register["variable_values"]["_nivel_error"] = (
            f"negativo_corregido:{data.get('value')}->{nivel_value}"
        )

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
    if data.get("date_time"):
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
    if data.get("date_time"):
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

    # ✅ FIX: Si no hay min_value configurado y la variable es de tipo donde
    # valores negativos no tienen sentido físico, usar 0.0 como default.
    var_type = (variable.get("type_variable") or "").upper()
    if min_val is None and var_type in ("CAUDAL", "CAUDAL_PROMEDIO", "TOTALIZADO"):
        min_val = 0.0

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
        emit_system_event(
            event_type="MEASUREMENT_ERROR",
            point_id=point_catchment["id"],
            title="Valor fuera de rango configurado",
            message=f"Variable {variable.get('str_variable')}: valor {val} < mínimo {min_val}.",
            severity="WARNING",
            extra_data={
                "decision": "RECHAZAR",
                "reason": "El valor medido está por debajo del mínimo configurado para esta variable. Se marca el registro como error para evitar distorsiones en reportes y envíos DGA.",
                "actual_value": val,
                "threshold_value": float(min_val),
                "expected_range": [float(min_val), None],
                "variable": variable.get('str_variable'),
                "raw_value": val,
                "min_value": float(min_val),
                "is_error": True,
                "source": "api.cronjobs.telemetry.controllers.unified_processing:_validate_variable_range",
            },
        )
        created_register["is_error"] = True
        return False

    if max_val is not None and val > float(max_val):
        telemetry_logger.warning(
            f"[VALIDACION] Punto {point_catchment['id']} - {variable.get('str_variable')}: "
            f"valor {val} > máximo {max_val}"
        )
        emit_system_event(
            event_type="MEASUREMENT_ERROR",
            point_id=point_catchment["id"],
            title="Valor fuera de rango configurado",
            message=f"Variable {variable.get('str_variable')}: valor {val} > máximo {max_val}.",
            severity="WARNING",
            extra_data={
                "decision": "RECHAZAR",
                "reason": "El valor medido supera el máximo configurado para esta variable. Se marca el registro como error para evitar distorsiones en reportes y envíos DGA.",
                "actual_value": val,
                "threshold_value": float(max_val),
                "expected_range": [None, float(max_val)],
                "variable": variable.get('str_variable'),
                "raw_value": val,
                "max_value": float(max_val),
                "is_error": True,
                "source": "api.cronjobs.telemetry.controllers.unified_processing:_validate_variable_range",
            },
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
    medition_str: Optional[str] = None,
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

    # Regla de negocio: caudales negativos (ruido de sensor o offset)
    # se tratan como 0.0 para no generar falsos errores de validación.
    # Caudal negativo no tiene sentido físico.
    raw_value = data.get("value")
    if type_variable.upper() in ("CAUDAL", "CAUDAL_PROMEDIO") and raw_value is not None:
        try:
            v = float(raw_value)
            if v < 0.0:
                data = dict(data)
                data["value"] = 0.0
                raw_value = 0.0
        except (ValueError, TypeError):
            pass

    try:
        if type_variable.upper() == "TOTALIZADO":
            date_time_last_logger_total, created_register = process_totalizado_variable(
                data, variable, point_catchment, created_register, medition_str=medition_str
            )

        elif type_variable.upper() == "NIVEL":
            created_register = process_nivel_variable(
                data, variable, point_catchment, created_register
            )

        elif type_variable.upper() == "CAUDAL":
            created_register = process_caudal_variable(
                data, variable, point_catchment, created_register
            )

        elif type_variable.upper() == "CAUDAL_PROMEDIO":
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

    # Validación de calidad: rango min/max sobre el valor PROCESADO (P1.7)
    # Anteriormente se validaba el valor crudo (pulsos), que no tenía sentido
    # para los límites configurados en m³, metros o L/s.
    processed_value = None
    if type_variable.upper() == "TOTALIZADO":
        processed_value = created_register.get("total")
    elif type_variable.upper() == "NIVEL":
        processed_value = created_register.get("nivel")
    elif type_variable.upper() in ("CAUDAL", "CAUDAL_PROMEDIO"):
        processed_value = created_register.get("flow")

    if processed_value is not None:
        try:
            processed_value = float(processed_value)
        except (ValueError, TypeError):
            processed_value = None

    if processed_value is not None:
        if not _validate_variable_range(variable, processed_value, point_catchment, created_register):
            log_variable_processing(
                point_catchment["id"],
                variable.get("str_variable"),
                type_variable,
                False,
                f"Valor procesado fuera de rango: {processed_value}",
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
