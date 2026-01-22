"""
CONTROLADORES UNIFICADOS PARA CRONJOBS DE TELEMETRÍA
=====================================================

Este archivo centraliza toda la lógica de procesamiento de variables para que
todos los cronjobs (twin.py, twin_f1.py, twin_f5.py, nettra.py, novus.py)
usen exactamente la misma lógica robusta.

IMPORTANTE: Todos los cronjobs deben importar y usar estas funciones.
"""
import time
import logging
from datetime import datetime
from typing import Any, Dict, Optional

import pytz

from api.telemetry.models import CoreVariable, TelemetryRecord
from api.telemetry.processing.formula_engine import FormulaEngine

# Alias para compatibilidad
evaluate_dynamic_formula = FormulaEngine.evaluate_dynamic_formula

# Timezone y logger
chile_tz = pytz.timezone("America/Santiago")
telemetry_logger = logging.getLogger(__name__)


def save_telemetry_data(
    point_id: int,
    created_register: Dict[str, Any],
    processed_variables: Optional[list] = None,
) -> TelemetryRecord:
    """
    Guarda los datos de telemetría exclusivamente en el esquema dinámico.

    Args:
        point_id: ID del punto de captación
        created_register: Diccionario con todos los valores procesados
        processed_variables: Lista de variables procesadas (del serializer).
            Si se proporciona, se usa para mapear datos en lugar de consultar
            solo CoreVariables. Esto permite guardar variables del esquema.

    MEJORAS:
    - Soporta variables heredadas del esquema (SchemeVariable)
    - Agrega device_id al metadata para trazabilidad de hardware
    - Agrega variable_details para debugging
    - Incluye timestamp de procesamiento
    """
    try:
        # 1. Preparar timestamp
        dt_medition = created_register.get("date_time_medition")
        if isinstance(dt_medition, str):
            try:
                dt_medition = datetime.strptime(dt_medition, "%Y-%m-%dT%H:%M:%S")
            except ValueError:
                dt_medition = datetime.now()

        # 2. Mapear datos al JSON
        v3_data = {}

        # Si tenemos las variables procesadas (incluye esquema + punto), usarlas
        if processed_variables:
            for var in processed_variables:
                internal_code = var.get("internal_code")
                provider_key = var.get("str_variable") or var.get("provider_key")
                val = created_register.get(internal_code) or created_register.get(
                    provider_key
                )
                if val is not None and internal_code:
                    v3_data[internal_code] = val
        else:
            # Fallback: solo CoreVariables del punto (comportamiento legacy)
            active_vars = CoreVariable.objects.filter(point_id=point_id, is_active=True)
            for var in active_vars:
                val = created_register.get(var.internal_code) or created_register.get(
                    var.provider_key
                )
                if val is not None:
                    v3_data[var.internal_code] = val

        # Siempre incluir campos calculados por el sistema si existen
        system_calculated_fields = [
            "total_diff",
            "total_today_diff",
            "days_not_conection",
            "water_table",
        ]
        for field in system_calculated_fields:
            if field in created_register and field not in v3_data:
                v3_data[field] = created_register[field]

        # Fallback a campos estándar si no hay variables configuradas
        if not v3_data:
            standard_fields = [
                "flow",
                "nivel",
                "total",
                "pulses",
            ]
            for field in standard_fields:
                if field in created_register:
                    v3_data[field] = created_register[field]

        # 3. Construir metadata extendido
        metadata = {
            "last_logger_timestamp": created_register.get("date_time_last_logger"),
            "days_not_connection": created_register.get("days_not_conection", 0),
            "processed_at": datetime.now(chile_tz).isoformat(),
            "variable_details": created_register.get("variable_details", []),
        }

        # Agregar device_id si está disponible
        device_id = created_register.get("device_id")
        if device_id:
            metadata["device_id"] = device_id
            metadata["device_tracking"] = True

        # Agregar información de frecuencia
        frequency = created_register.get("frequency")
        if frequency:
            metadata["frequency_minutes"] = frequency

        # Helper para garantizar serialización JSON
        def make_json_serializable(obj):
            if isinstance(obj, dict):
                return {k: make_json_serializable(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [make_json_serializable(v) for v in obj]
            elif isinstance(obj, datetime):
                return obj.isoformat()
            return obj

        # 4. Crear el registro
        v3_record = TelemetryRecord.objects.create(
            point_id=point_id,
            timestamp=dt_medition,
            data=make_json_serializable(v3_data),
            is_error=created_register.get("is_error", False),
            is_partial=created_register.get("is_partial", False),
            metadata=make_json_serializable(metadata),
        )

        telemetry_logger.info(
            f"Punto {point_id} - Datos guardados en sistema dinámico "
            f"(ID: {v3_record.id}, device: {device_id or 'N/A'})"
        )

        # 5. Enviar a proveedores de compliance dinámicamente (V3)
        try:
            compliance_configs = get_compliance_configs_for_record(point_id, dt_medition)

            if compliance_configs:
                # Importar tarea de Celery para envío asíncrono
                from api.core.tasks.compliance_unified import send_compliance_data

                for config in compliance_configs:
                    # Encolar envío asíncrono
                    send_compliance_data.delay(v3_record.id, config.id)
                    telemetry_logger.info(
                        f"Punto {point_id} - Encolado envío a {config.provider.display_name} "
                        f"(record: {v3_record.id}, config: {config.id})"
                    )

        except Exception as e:
            telemetry_logger.error(
                f"Error encolando envíos de compliance para punto {point_id}: {e}",
                exc_info=True
            )
            # No fallar si hay error en compliance, el registro ya está guardado

        return v3_record

    except Exception as e:
        telemetry_logger.error(
            f"Error crítico guardando telemetría para punto {point_id}: {e}",
            exc_info=True,
        )
        return None





def get_data_with_retry(getter_func, *args, max_retries=None, backoff_factor=None):
    """
    Retry inteligente con backoff exponencial para obtener datos de APIs

    Args:
        getter_func: Función getter a ejecutar
        *args: Argumentos para la función
        max_retries: Número máximo de intentos (None = desde configuración)
        backoff_factor: Factor de espera exponencial (None = desde configuración)

    Returns:
        Dict con datos o None si falla
    """
    from api.core.services.config_service import ConfigService
    
    # Obtener valores desde configuración dinámica si no se proporcionan
    if max_retries is None:
        max_retries = ConfigService.get_int('retry.max_retries', 3)
    if backoff_factor is None:
        backoff_factor = ConfigService.get_int('retry.backoff_factor', 2)
    
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
            from api.telemetry.models import CatchmentPoint
            from api.core.utils.google_chat import check_and_notify_error

            # Necesitamos obtener info del punto para el mensaje
            # Como esto es solo en error, el query extra es aceptable
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
    from api.telemetry.processing import FormulaEngine

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
        telemetry_logger.warning(
            f"Factor de pulsos no válido: {pulses_factor}, usando 1000"
        )
        pulses_factor = 1000

    total_calculado = FormulaEngine.calculate_total_m3(pulses_factor, value, point_catchment)
    created_register["total"] = total_calculado

    # 4. CALCULAR DIFERENCIA POR HORA (consumo actual)
    current_dt = (
        datetime.strptime(data["date_time"], "%Y-%m-%dT%H:%M:%S")
        if data.get("date_time")
        else datetime.now()
    )
    total_diff = FormulaEngine.total_hour(created_register["total"], point_catchment, current_dt)
    created_register["total_diff"] = total_diff

    # 5. CALCULAR ACUMULADO DEL DÍA (✅ CORRECCIÓN: Pasar total, no diff)
    total_today_diff = FormulaEngine.total_day(point_catchment, current_dt, created_register["total"])
    created_register["total_today_diff"] = total_today_diff

    # 6. ASIGNAR TIMESTAMP DEL ÚLTIMO LOGGER
    if data.get("date_time"):
        created_register["date_time_last_logger"] = data["date_time"]
        date_time_last_logger_total = data["date_time"]
    else:
        # Fallback: Usar fecha de medición si el logger no envía fecha
        # Esto asegura que audits y history tengan fecha válida
        created_register["date_time_last_logger"] = created_register[
            "date_time_medition"
        ]
        date_time_last_logger_total = created_register["date_time_last_logger"]

    # 7. CALCULAR DÍAS SIN CONEXIÓN
    # CORRECCIÓN: Pasar point_catchment para poder buscar historial si falta info
    created_register = calculate_days_not_connection(
        created_register, chile_tz, point_catchment
    )

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
    from api.telemetry.processing import FormulaEngine

    # Manejar nivel negativo
    try:
        nivel_value = float(data["value"])
    except (ValueError, TypeError):
        nivel_value = 0

    if nivel_value < 0:
        # Buscar nivel más alto registrado en V3
        last_valid = (
            TelemetryRecord.objects.filter(point_id=point_catchment["id"])
            .order_by("-timestamp")
            .first()
        )

        if last_valid and "level" in last_valid.data:
            nivel_value = float(last_valid.data["level"])
            telemetry_logger.info(
                f"Nivel negativo corregido usando último valor V3: {nivel_value}"
            )
        else:
            nivel_value = 0

    # Aplicar offset si existe (reemplaza lógica hardcodeada antigua)
    offset = variable.get("offset", 0.0)
    if offset:
        nivel_value = float(nivel_value) + float(offset)

    # Priorizar d3 de la variable, fallback al perfil global
    config = variable.get("configuration", {})
    d3 = config.get("d3")
    if d3 is None:
        d3 = point_catchment["profile_data_config"].get("d3", 0)

    created_register["nivel"] = FormulaEngine.nivel_mt(
        nivel_value,
        variable.get("calculate_nivel"),
        point_catchment["id"],
        d3,
    )

    # Validar d3 antes de calcular nivel freático
    if not d3 or float(d3 if d3 else 0) <= 0:
        telemetry_logger.warning(
            f"Error: d3 no válido para punto {point_catchment['id']}"
        )
        d3 = 0

    created_register["water_table"] = FormulaEngine.water_table(created_register["nivel"], d3)
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
    from api.telemetry.processing import FormulaEngine

    created_register["flow"] = FormulaEngine.instantaneous_flow(
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

    NOTA: Esta función NO guarda el flow en created_register.
    El flow se calcula dinámicamente en serializers y cron_dga.

    Args:
        date_time_last_logger_total: Timestamp del último totalizado
        created_register: Registro en construcción
        point_catchment: Datos del punto de captación

    Returns:
        created_register actualizado (sin flow asignado)
    """
    # ✅ NO GUARDAR: Se calcula dinámicamente en serializers y cron_dga
    # Esto asegura que siempre use la lógica más actualizada
    # y no haya que reprocesar datos históricos si cambia la escala

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
    Procesar variable de forma segura con manejo de errores.
    
    NUEVO: Intenta usar FormulaEngine si la variable tiene type_definition o formula.
    Fallback a procesadores legacy si no está disponible.

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
    min_val = variable.get("min_value")
    max_val = variable.get("max_value")
    operation = variable.get("operation", "PHYSICAL")

    # 1. Obtener Valor Base (Fórmula Dinámica o Dato Físico)
    if operation == "FORMULA":
        formula = variable.get("formula")
        current_val = evaluate_dynamic_formula(formula, created_register)
        telemetry_logger.info(
            f"Punto {point_catchment['id']} - Fórmula '{formula}' evaluada: {current_val}"
        )
    else:
        try:
            current_val = float(data.get("value", 0))
        except (ValueError, TypeError):
            current_val = 0.0

    # 2. Aplicar Factor de Escala y Offset Centralizado
    scale = variable.get("scale_factor", 1.0)
    offset = variable.get("offset", 0.0)
    current_val = (current_val * scale) + offset

    # 3. Validar valor contra límites configurados
    if min_val is not None and current_val < float(min_val):
        telemetry_logger.warning(
            f"Punto {point_catchment['id']} - Valor {current_val} < min {min_val}. Ignorando."
        )
        return date_time_last_logger_total, created_register
    if max_val is not None and current_val > float(max_val):
        telemetry_logger.warning(
            f"Punto {point_catchment['id']} - Valor {current_val} > max {max_val}. Ignorando."
        )
        return date_time_last_logger_total, created_register

    # Sincronizar value procesado para que lo usen los procesadores especializados
    data["value"] = current_val

    # Registrar el valor en el acumulador para que otras fórmulas puedan usarlo
    if variable.get("internal_code"):
        created_register[variable["internal_code"]] = current_val

    # Intentar usar FormulaEngine si está disponible
    try:
        from api.telemetry.processing import FormulaEngine
        from api.telemetry.models import CoreVariable
        
        # Buscar CoreVariable si tenemos el ID o internal_code
        point_id = point_catchment.get("id")
        var_code = variable.get("internal_code") or variable.get("str_variable")
        
        if point_id and var_code:
            try:
                core_var = CoreVariable.objects.filter(
                    point_id=point_id,
                    internal_code=var_code
                ).select_related('type_definition').first()
                
                if core_var:
                    # Usar FormulaEngine
                    engine = FormulaEngine(point_id)
                    raw_value = data.get("value", 0)
                    
                    # Preparar valores actuales
                    current_values = created_register.copy()
                    current_values[var_code] = raw_value
                    
                    # Obtener timestamp actual
                    current_timestamp = None
                    if data.get("date_time"):
                        try:
                            current_timestamp = datetime.strptime(
                                data["date_time"], "%Y-%m-%dT%H:%M:%S"
                            )
                        except ValueError:
                            current_timestamp = datetime.now()
                    else:
                        current_timestamp = datetime.now()
                    
                    # Procesar con FormulaEngine
                    processed_value = engine.process_variable(
                        core_var,
                        raw_value,
                        current_values,
                        current_timestamp
                    )
                    
                    # Guardar resultado según tipo
                    if type_variable == "TOTALIZADO":
                        created_register["total"] = processed_value
                        created_register["pulses"] = raw_value
                        # Calcular diferencias usando engine
                        if current_timestamp:
                            prev_values = engine.prev
                            if "total" in prev_values:
                                diff = processed_value - prev_values["total"]
                                created_register["total_diff"] = diff
                            time_diff = engine.time.get("diff_seconds", 3600)
                            if time_diff > 0:
                                created_register["total_today_diff"] = (
                                    diff / time_diff * 3600 if diff else 0
                                )
                    
                    elif type_variable == "NIVEL":
                        created_register["nivel"] = processed_value
                        # Calcular nivel freático si hay d3
                        config = engine.config
                        d3 = config.get("d3", 0)
                        if d3:
                            created_register["water_table"] = float(d3) - processed_value
                    
                    elif type_variable == "CAUDAL":
                        created_register["flow"] = processed_value
                    
                    # Asignar timestamp del logger
                    if data.get("date_time"):
                        created_register["date_time_last_logger"] = data["date_time"]
                        if type_variable == "TOTALIZADO":
                            date_time_last_logger_total = data["date_time"]
                    
                    # Calcular días sin conexión
                    created_register = calculate_days_not_connection(
                        created_register, chile_tz, point_catchment
                    )
                    
                    telemetry_logger.info(
                        f"Punto {point_id} - Variable '{var_code}' procesada con FormulaEngine: {processed_value}"
                    )
                    
                    return date_time_last_logger_total, created_register
                    
            except Exception as e:
                telemetry_logger.debug(
                    f"FormulaEngine no disponible para punto {point_id}, usando legacy: {e}"
                )
    except ImportError:
        telemetry_logger.debug("FormulaEngine no disponible, usando procesadores legacy")

    # Fallback a procesadores legacy
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
    created_register: Dict[str, Any],
    chile_tz: Any,
    point_catchment: Dict[str, Any] = None,
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

    elif point_catchment and point_catchment.get("id"):
        # CASO 2: No hay timestamp, buscar último registro V3
        try:
            ultimo_valido = (
                TelemetryRecord.objects.filter(point_id=point_catchment["id"])
                .order_by("-timestamp")
                .first()
            )

            if ultimo_valido:
                # Calcular días desde ese último registro válido
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




def should_submit_compliance(
    point_id: int,
    provider_name: str,
    record_timestamp: datetime,
    telemetry_record_id: Optional[int] = None
) -> bool:
    """
    Determinar si debe enviar datos a un proveedor de compliance (DGA, SMA, etc.) - Sistema Dinámico V3.

    Esta función reemplaza determine_dga_send() y valida_frequency() con lógica dinámica
    que funciona para CUALQUIER proveedor de compliance configurado en la BD.

    Args:
        point_id: ID del punto de captación
        provider_name: Nombre del proveedor (ej: 'dga', 'sma', 'indh')
        record_timestamp: Timestamp del registro de telemetría
        telemetry_record_id: ID del TelemetryRecord (opcional, para validaciones adicionales)

    Returns:
        True si debe enviar, False si no

    Ejemplos:
        >>> should_submit_compliance(123, 'dga', datetime.now())
        True  # Si está configurado y corresponde la frecuencia

        >>> should_submit_compliance(456, 'sma', datetime.now())
        False  # Si no está configurado o no corresponde enviar
    """
    try:
        from api.telemetry.providers.compliance_models import PointComplianceConfig
        from api.telemetry.services.compliance_service import get_compliance_service

        # 1. Buscar configuración activa para este punto + proveedor
        # Se incluye select_related para optimizar la consulta del estándar y el proveedor
        config = PointComplianceConfig.objects.filter(
            point_id=point_id,
            provider__name=provider_name,
            is_active=True,
            send_compliance=True  # Debe tener envío habilitado
        ).select_related('provider', 'compliance_standard').first()

        if not config:
            telemetry_logger.debug(
                f"Punto {point_id} no tiene configuración activa para proveedor '{provider_name}'"
            )
            return False

        # 2. Validar contra el estándar de cumplimiento usando el servicio centralizado (V3 Dinámico)
        service = get_compliance_service()
        return service.should_submit(config, record_timestamp)

    except Exception as e:
        telemetry_logger.error(
            f"Error determinando envío de compliance para {provider_name} en pto {point_id}: {e}", 
            exc_info=True
        )
        return False


def get_compliance_configs_for_record(
    point_id: int,
    record_timestamp: datetime
) -> list:
    """
    Obtener todas las configuraciones de compliance que deben procesar este registro.

    Esta función centraliza la lógica para determinar qué proveedores de compliance
    deben recibir este registro de telemetría.

    Args:
        point_id: ID del punto de captación
        record_timestamp: Timestamp del registro

    Returns:
        Lista de PointComplianceConfig que deben procesar el registro

    Ejemplo:
        >>> configs = get_compliance_configs_for_record(123, datetime.now())
        >>> for config in configs:
        >>>     # Enviar a este proveedor de compliance
        >>>     send_compliance_data.delay(record_id, config.id)
    """
    try:
        from api.telemetry.providers.compliance_models import PointComplianceConfig

        # Obtener todas las configs activas con envío habilitado
        all_configs = PointComplianceConfig.objects.filter(
            point_id=point_id,
            is_active=True,
            send_compliance=True
        ).select_related('provider')

        # Filtrar por frecuencia
        configs_to_submit = []

        for config in all_configs:
            if should_submit_compliance(
                point_id,
                config.provider.name,
                record_timestamp
            ):
                configs_to_submit.append(config)

        if configs_to_submit:
            provider_names = [c.provider.display_name for c in configs_to_submit]
            telemetry_logger.info(
                f"Punto {point_id} - Enviar a {len(configs_to_submit)} proveedor(es): "
                f"{', '.join(provider_names)}"
            )

        return configs_to_submit

    except Exception as e:
        telemetry_logger.error(
            f"Error obteniendo configuraciones de compliance para punto {point_id}: {e}",
            exc_info=True
        )
        return []
