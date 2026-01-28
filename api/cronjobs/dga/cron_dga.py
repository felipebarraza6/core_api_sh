# TIMESTAMP FIX APPLIED - Version 2025-08-06-04:36 - No Z in timestamp
"""Cron SEND DATA DGA."""

from datetime import datetime
from typing import Optional

import pytz

from api.core.models import (
    DgaDataConfigCatchment, 
    InteractionDetail, 
    Variable, 
    SchemesCatchment
)

# Importar función de cálculo de caudal promedio
from api.cronjobs.telemetry.controllers.flow import average_flow

# ✅ Logging estructurado
from api.cronjobs.utils.logging_config import dga_logger

from .send_data_dga import send


def _has_average_flow_variable(catchment_point_id: int) -> bool:
    """
    Verifica si un punto de captación tiene configurada una variable de CAUDAL_PROMEDIO.
    
    Args:
        catchment_point_id: ID del punto de captación
        
    Returns:
        bool: True si tiene variable CAUDAL_PROMEDIO configurada
    """
    try:
        # Buscar si el punto tiene esquemas con variables CAUDAL_PROMEDIO
        has_caudal_promedio = Variable.objects.filter(
            scheme_catchment__points_catchment__id=catchment_point_id,
            type_variable="CAUDAL_PROMEDIO"
        ).exists()
        
        return has_caudal_promedio
    except Exception as e:
        dga_logger.error(f"Error verificando variable CAUDAL_PROMEDIO para punto {catchment_point_id}: {e}")
        return False


def _calculate_dynamic_flow(register: InteractionDetail) -> float:
    """
    Calcula el caudal promedio dinámicamente usando la función average_flow.
    
    Args:
        register: Registro de InteractionDetail
        
    Returns:
        float: Caudal calculado dinámicamente o 0.0 si falla
    """
    try:
        # Buscar el registro anterior para calcular caudal promedio
        previous_register = InteractionDetail.objects.filter(
            catchment_point=register.catchment_point,
            date_time_medition__lt=register.date_time_medition
        ).order_by('-date_time_medition').first()
        
        if not previous_register:
            dga_logger.warning(f"No hay registro anterior para punto {register.catchment_point.id}, retornando 0.0")
            return 0.0
        
        # Preparar datos para average_flow (como en los cronjobs)
        point_catchment = {"id": register.catchment_point.id}
        total_actual = register.total or 0
        
        # Usar la función average_flow existente
        calculated_flow = average_flow(
            point_catchment=point_catchment,
            total=total_actual,
            date_lg=register.date_time_medition
        )
        
        dga_logger.info(f"Caudal calculado dinámicamente para punto {register.catchment_point.id}: {calculated_flow}")
        return calculated_flow
        
    except Exception as e:
        dga_logger.error(f"Error calculando caudal dinámico para registro {register.id}: {e}")
        return 0.0


def run():
    # Fix aplicado para detectar fallos en DGA - Versión actualizada
    """
    Ejecuta el envío de datos a DGA de forma continua y robusta.
    Minimiza errores y maneja excepciones para ejecución continua.
    """
    try:
        # Obtener registros pendientes de envío
        data_for_send = InteractionDetail.objects.filter(send_dga=True).exclude(catchment_point=1).order_by(
            "created"
        )

        if not data_for_send.exists():
            dga_logger.info("No hay registros pendientes de envío a DGA")
            return

        # Aumentado a 30 registros por ejecución para procesar backlog más rápido
        # Con rate limit de 12s, son ~6 min por batch (aceptable para cron de 3 min)
        data_for_send = data_for_send[:30]

        dga_logger.info(f"Procesando {len(data_for_send)} registros para envío a DGA")

        # Contadores para el reporte final
        success_count = 0
        error_count = 0

        for register in data_for_send:
            try:
                # Validar el registro antes de procesarlo
                if not _validate_register(register):
                    dga_logger.warning(f"Registro {register.id} no válido, omitiendo")
                    error_count += 1
                    continue

                # Obtener configuración DGA
                dga_config = _get_dga_config(register)
                if not dga_config:
                    dga_logger.warning(
                        f"No se pudo obtener configuración DGA para registro {register.id}"
                    )
                    error_count += 1
                    continue

                # Preparar datos para envío
                response_data = _prepare_response_data(register, dga_config)
                if not response_data:
                    error_count += 1
                    continue

                # Enviar datos a DGA
                dga_logger.info(f"Enviando registro {register.id} a DGA: {dga_config.code_dga}")
                send_result = send(response_data)  # MODIFICADO: Capturar resultado
                dga_logger.debug(f"send() retornó: {send_result}, tipo: {type(send_result)}")

                # MODIFICADO: Verificar el resultado del envío
                if send_result:
                    success_count += 1
                    dga_logger.info(f"Registro {register.id} procesado exitosamente")
                else:
                    error_count += 1
                    dga_logger.error(f"Error: Fallo al enviar registro {register.id} a DGA")

            except Exception as e:
                error_count += 1
                error_msg = f"Error procesando registro {register.id}: {str(e)}"
                dga_logger.error(f"ERROR: {error_msg}", exc_info=True)

        dga_logger.info(f"Proceso completado: {success_count} exitosos, {error_count} errores")

    except Exception as e:
        dga_logger.error(f"Error general en cron DGA: {str(e)}", exc_info=True)


def _validate_register(register: InteractionDetail) -> bool:
    """
    Valida que el registro tenga todos los datos necesarios.

    Args:
        register: Registro de InteractionDetail

    Returns:
        bool: True si el registro es válido
    """
    try:
        # Validar que tenga fecha de medición
        if not register.date_time_medition:
            dga_logger.error(f"Error: Fecha de medición no disponible para registro {register.id}")
            return False

        # Validar que tenga punto de captación
        if not register.catchment_point:
            dga_logger.error(
                f"Error: Punto de captación no disponible para registro {register.id}"
            )
            return False

        return True

    except Exception as e:
        dga_logger.error(f"Error validando registro {register.id}: {str(e)}", exc_info=True)
        return False


def _get_dga_config(register: InteractionDetail) -> Optional[DgaDataConfigCatchment]:
    """
    Obtiene la configuración DGA para un registro.

    Args:
        register: Registro de InteractionDetail

    Returns:
        Configuración DGA o None si no se encuentra
    """
    try:
        # Obtener configuración DGA para el punto de captación
        dga_config = DgaDataConfigCatchment.objects.filter(
            point_catchment=register.catchment_point
        ).first()

        if not dga_config:
            dga_logger.warning(
                f"No se encontró configuración DGA para punto {register.catchment_point.id}"
            )
            return None

        return dga_config

    except Exception as e:
        dga_logger.error(
            f"Error obteniendo configuración DGA para registro {register.id}: {str(e)}",
            exc_info=True
        )
        return None


def _prepare_response_data(
    register: InteractionDetail, dga_config: DgaDataConfigCatchment
) -> Optional[dict]:
    """
    Prepara los datos para envío a DGA.

    Args:
        register: Registro de InteractionDetail
        dga_config: Configuración DGA

    Returns:
        dict con los datos preparados o None si hay error
    """
    try:
        # Convertir la fecha a zona horaria chilena
        chile_tz = pytz.timezone("America/Santiago")
        date_time_medition_chile = register.date_time_medition.astimezone(chile_tz)

        # NUEVA LÓGICA: Determinar caudal según tipo de variable y estándar DGA
        flow_value = register.flow or 0.0
        
        # ✅ NUEVO: Priorizar cálculo según estándar (especialmente para MEDIO)
        from django.conf import settings
        use_new_calculation = getattr(settings, 'USE_NEW_CAUDAL_CALCULATION_MEDIO', False)
        
        if use_new_calculation and dga_config.standard == "MEDIO":
            try:
                from api.cronjobs.dga.caudal_calculations import calculate_flow_by_standard
                calculated_flow = calculate_flow_by_standard(register, dga_config)
                # Para MEDIO, siempre usamos el promedio diario si es válido
                flow_value = calculated_flow
                dga_logger.info(f"[NUEVO] Usando caudal medio diario para MEDIO: {flow_value} L/s")
            except Exception as e:
                dga_logger.warning(f"[NUEVO] Error en cálculo medio diario: {e}, usando cálculo actual", exc_info=True)
        else:
            # FIX APLICADO: Si no hay consumo (total_diff = 0), el caudal debe ser 0
            # (Solo para estándares que no sean MEDIO, ya que MEDIO reporta promedio diario)
            if register.total_diff == 0:
                flow_value = 0.0
                dga_logger.info(f"Sin consumo (total_diff=0), caudal corregido a: {flow_value}")
            else:
                # Si hay consumo, verificar si el punto tiene variable CAUDAL_PROMEDIO
                if _has_average_flow_variable(register.catchment_point.id):
                    calculated_flow = _calculate_dynamic_flow(register)
                    if calculated_flow > 0:
                        flow_value = calculated_flow
                        dga_logger.info(f"Usando caudal calculado dinámicamente: {flow_value}")
                    else:
                        dga_logger.warning(f"Cálculo dinámico falló, usando valor guardado: {flow_value}")
                else:
                    dga_logger.debug(f"Punto sin CAUDAL_PROMEDIO, usando valor guardado: {flow_value}")

        # ✅ CORRECCIÓN NORMATIVA DGA: Enviar total SIN offset (solo escala)
        # DGA requiere: (pulsos * pulses_factor) / 1000
        # NO debe incluir el offset/addition del perfil
        total_para_dga = register.total or "0"

        try:
            # Obtener el offset actual del perfil
            from api.core.models import ProfileDataConfigCatchment
            profile = ProfileDataConfigCatchment.objects.filter(
                point_catchment_id=register.catchment_point.id
            ).first()

            offset = 0
            if profile and profile.addition:
                offset = profile.addition

            # Si hay offset, restarlo del total guardado para obtener el valor RAW
            if offset > 0 and register.total:
                total_con_offset = float(register.total)
                total_sin_offset = total_con_offset - offset
                total_para_dga = str(int(total_sin_offset))
                dga_logger.info(
                    f"Total corregido para DGA (punto {register.catchment_point.id}): "
                    f"{total_con_offset} - {offset} = {total_para_dga}"
                )
            else:
                # Sin offset, usar el total directamente
                total_para_dga = register.total or "0"

        except Exception as e:
            dga_logger.warning(f"Error calculando total sin offset: {e}, usando total directo")
            total_para_dga = register.total or "0"

        response_data = {
            "catchment_point": register.catchment_point.title,
            # Redondear a hora cerrada (minutos y segundos = 00) para API DGA
            "date_time_medition": date_time_medition_chile.replace(minute=0, second=0, microsecond=0).strftime(
                "%Y-%m-%dT%H:00:00"
            ),
            "total": total_para_dga,  # ✅ CORREGIDO: Total SIN offset (solo escala)
            "flow": flow_value,  # MODIFICADO: Usar valor calculado dinámicamente si corresponde
            "water_table": register.water_table or 0.0,
            "type_dga": dga_config.type_dga,
            "code_dga": dga_config.code_dga,
            "id_data": register.id,
            "rut": dga_config.rut_report_dga,
            "password": dga_config.get_dga_password(),  # Usa método que fallback a settings
            "dga_config": {
                "rut_empresa": getattr(dga_config, "rut_empresa", "76944359-2")
            },
        }

        # Validar datos críticos
        critical_fields = [
            response_data["code_dga"],
            response_data["rut"],
            response_data["password"],
        ]

        if not all(critical_fields):
            dga_logger.error(f"Error: Configuración DGA incompleta para registro {register.id}")
            return None

        return response_data

    except Exception as e:
        dga_logger.error(f"Error preparando datos para registro {register.id}: {str(e)}", exc_info=True)
        return None
