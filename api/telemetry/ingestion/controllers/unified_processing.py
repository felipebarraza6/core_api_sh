"""
CONTROLADORES UNIFICADOS PARA CRONJOBS DE TELEMETRÍA
=====================================================

Este archivo centraliza toda la lógica de procesamiento de variables para que
todos los cronjobs (twin.py, twin_f1.py, twin_f5.py, nettra.py, novus.py)
usen exactamente la misma lógica robusta.

IMPORTANTE: Todos los cronjobs deben importar y usar estas funciones.
"""

from datetime import datetime
from typing import Any, Dict, Optional

from api.telemetry.models import CoreVariable, TelemetryRecord
    calculate_days_not_connection,
    determine_dga_send,
    evaluate_dynamic_formula,
)
from .processing.totalized import process_totalizado_variable
from .processing.nivel import process_nivel_variable
from .processing.caudal import process_caudal_variable, process_caudal_promedio_variable


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

        # 4. Crear el registro
        v3_record = TelemetryRecord.objects.create(
            point_id=point_id,
            timestamp=dt_medition,
            data=v3_data,
            send_dga=created_register.get("send_dga", False),
            is_error=created_register.get("is_error", False),
            is_partial=created_register.get("is_partial", False),
            metadata=metadata,
        )

        telemetry_logger.info(
            f"Punto {point_id} - Datos guardados en sistema dinámico "
            f"(ID: {v3_record.id}, device: {device_id or 'N/A'})"
        )
        return v3_record

    except Exception as e:
        telemetry_logger.error(
            f"Error crítico guardando telemetría para punto {point_id}: {e}",
            exc_info=True,
        )
        return None


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
