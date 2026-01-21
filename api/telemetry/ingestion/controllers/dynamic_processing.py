"""
Procesamiento Dinámico de Telemetría usando FormulaEngine
==========================================================

Este módulo reemplaza TODA la lógica hardcodeada de procesamiento de variables.
TODO se procesa mediante FormulaEngine, haciendo el sistema 100% configurable.

VENTAJA COMPETITIVA:
- Un solo motor (FormulaEngine) para TODO el sistema
- Agregar variables = configuración, NO código
- El método se propaga a ingesta, reportes, alertas, compliance
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional, List

from django.db import transaction

from api.telemetry.models import CoreVariable, TelemetryRecord, CatchmentPoint
from api.telemetry.processing.formula_engine import FormulaEngine

logger = logging.getLogger(__name__)


def process_variable(
    variable: CoreVariable,
    raw_data: dict,
    context: dict,
    current_timestamp: Optional[datetime] = None
) -> Optional[float]:
    """
    Procesa UNA variable usando FormulaEngine.

    Este es el ÚNICO punto donde se procesa una variable.
    No existe lógica hardcodeada de caudal/nivel/totalizado.

    Args:
        variable: Instancia de CoreVariable con su configuración
        raw_data: Datos crudos del proveedor (parseados)
        context: Diccionario con todas las variables ya procesadas
        current_timestamp: Timestamp del registro actual

    Returns:
        Valor procesado de la variable, o None si hay error

    Ejemplo:
        >>> var = CoreVariable(
        ...     internal_code="volumen_m3",
        ...     operation="FORMULA",
        ...     formula="({pulsos} * {factor}) / 1000",
        ...     context={"factor": 0.5}
        ... )
        >>> raw_data = {"pulsos": 1500}
        >>> result = process_variable(var, raw_data, {})
        >>> # result = 0.75
    """
    try:
        # 1. PHYSICAL: Valor directo del sensor con transformación simple
        if variable.operation == "PHYSICAL":
            raw_value = raw_data.get(variable.provider_key)
            if raw_value is None:
                logger.warning(
                    f"Variable {variable.internal_code}: provider_key "
                    f"'{variable.provider_key}' no encontrado en raw_data"
                )
                return None

            try:
                value = float(raw_value)
                # Aplicar scale_factor y offset
                result = (value * (variable.scale_factor or 1.0)) + (variable.offset or 0.0)
                return result
            except (ValueError, TypeError) as e:
                logger.error(
                    f"Variable {variable.internal_code}: Error convirtiendo "
                    f"valor '{raw_value}' a float: {e}"
                )
                return None

        # 2. FORMULA: Evaluar expresión dinámica
        elif variable.operation == "FORMULA":
            if not variable.formula:
                logger.error(
                    f"Variable {variable.internal_code}: operation=FORMULA "
                    f"pero formula está vacía"
                )
                return None

            # Construir contexto completo
            full_context = {**context, **raw_data}

            # Agregar contexto de la variable (constantes, factores, etc.)
            if variable.context:
                full_context.update(variable.context)

            # Agregar valores de variables fuente
            for source_var in (variable.sources or []):
                if source_var not in full_context:
                    # Buscar en raw_data o context
                    if source_var in raw_data:
                        full_context[source_var] = raw_data[source_var]
                    elif source_var in context:
                        full_context[source_var] = context[source_var]

            # Evaluar fórmula usando FormulaEngine
            engine = FormulaEngine(variable.point_id)
            result = engine.evaluate(variable.formula, full_context, current_timestamp)
            return result

        # 3. Operaciones sobre variables fuente (SUM, DIFF, AVG, MUL, MIN, MAX)
        elif variable.operation in ["SUM", "DIFF", "AVG", "MUL", "MIN", "MAX"]:
            if not variable.sources:
                logger.error(
                    f"Variable {variable.internal_code}: operation={variable.operation} "
                    f"pero sources está vacío"
                )
                return None

            # Recolectar valores de las variables fuente
            source_values = []
            for source_var in variable.sources:
                # Buscar en contexto primero, luego en raw_data
                val = context.get(source_var) or raw_data.get(source_var)
                if val is not None:
                    source_values.append(val)
                else:
                    logger.warning(
                        f"Variable {variable.internal_code}: variable fuente "
                        f"'{source_var}' no encontrada"
                    )

            if not source_values:
                logger.warning(
                    f"Variable {variable.internal_code}: ninguna variable fuente "
                    f"tiene valor"
                )
                return None

            # Aplicar operación
            result = FormulaEngine.apply_operation(variable.operation, source_values)
            return result

        # 4. Operación no reconocida
        else:
            logger.error(
                f"Variable {variable.internal_code}: operación no soportada: "
                f"{variable.operation}"
            )
            return None

    except Exception as e:
        logger.error(
            f"Error procesando variable {variable.internal_code}: {e}",
            exc_info=True
        )
        return None


def validate_value(
    variable: CoreVariable,
    value: Optional[float]
) -> Optional[float]:
    """
    Valida que el valor esté dentro de los rangos configurados.

    Args:
        variable: CoreVariable con min_value y max_value
        value: Valor a validar

    Returns:
        Valor validado, o None si está fuera de rango
    """
    if value is None:
        return None

    try:
        # Validar rango mínimo
        if variable.min_value is not None and value < variable.min_value:
            logger.warning(
                f"Variable {variable.internal_code}: valor {value} < mínimo "
                f"{variable.min_value}. Retornando None."
            )
            return None

        # Validar rango máximo
        if variable.max_value is not None and value > variable.max_value:
            logger.warning(
                f"Variable {variable.internal_code}: valor {value} > máximo "
                f"{variable.max_value}. Retornando None."
            )
            return None

        return value

    except Exception as e:
        logger.error(f"Error validando valor de {variable.internal_code}: {e}")
        return None


def process_point_telemetry(
    point_id: int,
    raw_data: dict,
    current_timestamp: Optional[datetime] = None
) -> dict:
    """
    Procesa TODOS los datos de telemetría de un punto.

    Este es el punto de entrada principal para procesar datos de un punto.
    Obtiene todas las variables activas, las procesa en orden de prioridad,
    y retorna un diccionario con todos los resultados.

    Args:
        point_id: ID del punto de captación
        raw_data: Datos crudos del proveedor/equipo (ya parseados)
        current_timestamp: Timestamp del registro actual

    Returns:
        Diccionario con todas las variables procesadas

    Ejemplo:
        >>> raw_data = {
        ...     "pulsos": 1500,
        ...     "nivel_medido": 3.2,
        ...     "caudal_crudo": 12.5
        ... }
        >>> result = process_point_telemetry(123, raw_data)
        >>> # result = {
        >>> #     "volumen_m3": 0.75,
        >>> #     "nivel_freatico": 46.8,
        >>> #     "caudal_ls": 12.5,
        >>> #     ...
        >>> # }
    """
    try:
        # 1. Obtener variables activas ordenadas por prioridad
        variables = CoreVariable.objects.filter(
            point_id=point_id,
            is_active=True
        ).order_by('priority', 'id')

        if not variables.exists():
            logger.warning(f"Punto {point_id}: no tiene variables activas configuradas")
            return {}

        # 2. Contexto para almacenar resultados
        context = {}

        # 3. Procesar cada variable en orden
        for variable in variables:
            try:
                # Procesar variable
                value = process_variable(variable, raw_data, context, current_timestamp)

                # Validar rango
                validated_value = validate_value(variable, value)

                # Agregar al contexto (para variables dependientes)
                if validated_value is not None:
                    context[variable.internal_code] = validated_value
                else:
                    # Agregar como None si falló validación
                    context[variable.internal_code] = None

                logger.debug(
                    f"Variable {variable.internal_code} = {validated_value} "
                    f"(raw={value})"
                )

            except Exception as e:
                logger.error(
                    f"Error procesando variable {variable.internal_code}: {e}",
                    exc_info=True
                )
                context[variable.internal_code] = None

        return context

    except Exception as e:
        logger.error(
            f"Error procesando telemetría del punto {point_id}: {e}",
            exc_info=True
        )
        return {}


def save_telemetry_data(
    point_id: int,
    processed_data: dict,
    raw_data: dict,
    timestamp: datetime,
    device_metadata: Optional[dict] = None,
    errors: Optional[List[dict]] = None
) -> Optional[TelemetryRecord]:
    """
    Guarda los datos de telemetría en la base de datos.

    Args:
        point_id: ID del punto de captación
        processed_data: Datos ya procesados (resultado de process_point_telemetry)
        raw_data: Datos crudos originales (para trazabilidad)
        timestamp: Timestamp del registro
        device_metadata: Metadata del dispositivo (batería, señal, etc.)
        errors: Lista de errores del equipo/proveedor

    Returns:
        TelemetryRecord creado, o None si hay error
    """
    try:
        with transaction.atomic():
            # Verificar que el punto existe
            try:
                point = CatchmentPoint.objects.get(id=point_id)
            except CatchmentPoint.DoesNotExist:
                logger.error(f"Punto {point_id} no existe")
                return None

            # Preparar metadata
            metadata = device_metadata or {}
            metadata['processing_timestamp'] = datetime.now().isoformat()

            # Determinar si hay errores
            is_error = bool(errors) if errors is not None else False

            # Crear registro
            record = TelemetryRecord.objects.create(
                point=point,
                timestamp=timestamp,
                data=processed_data,
                metadata=metadata,
                is_error=is_error,
                is_partial=False,  # TODO: detectar registros parciales
                compliance_status={}  # Se llenará después por compliance service
            )

            logger.info(
                f"✅ Registro creado para punto {point_id}: "
                f"{len(processed_data)} variables procesadas"
            )

            return record

    except Exception as e:
        logger.error(
            f"Error guardando telemetría del punto {point_id}: {e}",
            exc_info=True
        )
        return None


def process_and_save_telemetry(
    point_id: int,
    raw_data: dict,
    timestamp: datetime,
    device_metadata: Optional[dict] = None,
    errors: Optional[List[dict]] = None
) -> Optional[TelemetryRecord]:
    """
    Función de conveniencia que procesa Y guarda en un solo paso.

    Args:
        point_id: ID del punto
        raw_data: Datos crudos del proveedor (parseados)
        timestamp: Timestamp del registro
        device_metadata: Metadata del dispositivo
        errors: Errores del equipo

    Returns:
        TelemetryRecord creado

    Ejemplo:
        >>> raw_data = {"pulsos": 1500, "nivel_medido": 3.2}
        >>> metadata = {"provider": "twin", "device_id": "TWN-123", "battery": 85}
        >>> record = process_and_save_telemetry(
        ...     point_id=123,
        ...     raw_data=raw_data,
        ...     timestamp=datetime.now(),
        ...     device_metadata=metadata
        ... )
    """
    # 1. Procesar variables
    processed_data = process_point_telemetry(point_id, raw_data, timestamp)

    if not processed_data:
        logger.warning(f"Punto {point_id}: no se procesaron variables")
        # Aún así guardamos el registro como error
        processed_data = {}

    # 2. Guardar en BD
    return save_telemetry_data(
        point_id=point_id,
        processed_data=processed_data,
        raw_data=raw_data,
        timestamp=timestamp,
        device_metadata=device_metadata,
        errors=errors
    )
