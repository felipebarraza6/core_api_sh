# TIMESTAMP FIX APPLIED - Version 2025-08-06-04:36 - No Z in timestamp
"""Cron SEND DATA DGA."""

from typing import Optional

import pytz

from api.core.models import DgaDataConfigCatchment, InteractionDetail

from .send_data_dga import send


def run():
    # Fix aplicado para detectar fallos en DGA - Versión actualizada
    """
    Ejecuta el envío de datos a DGA de forma continua y robusta.
    Minimiza errores y maneja excepciones para ejecución continua.
    """
    try:
        # Obtener registros pendientes de envío (máximo 10 por ejecución)
        
        
        data_for_send = InteractionDetail.objects.filter(send_dga=True).exclude(catchment_point=1).order_by(
            "created"
        )

        if not data_for_send.exists():
            print("No hay registros pendientes de envío a DGA")
            return

        print(f"Procesando {data_for_send.count()} registros para envío a DGA")

        success_count = 0
        error_count = 0

        for register in data_for_send:
            try:
                # Validar que el registro tenga datos necesarios
                if not _validate_register(register):
                    continue

                # Obtener configuración DGA
                dga_config = _get_dga_config(register)
                if not dga_config:
                    print(
                        f"Error: No se encontró configuración DGA para registro {register.id}"
                    )
                    error_count += 1
                    continue

                # Preparar datos para envío
                response_data = _prepare_response_data(register, dga_config)
                if not response_data:
                    error_count += 1
                    continue

                # Enviar datos a DGA
                print(f"Enviando registro {register.id} a DGA: {dga_config.code_dga}")
                send_result = send(response_data)  # MODIFICADO: Capturar resultado
                print(f"DEBUG: send() retornó: {send_result}, tipo: {type(send_result)}")

                # MODIFICADO: Verificar el resultado del envío
                if send_result:
                    success_count += 1
                    print(f"Registro {register.id} procesado exitosamente")
                else:
                    error_count += 1
                    print(f"Error: Fallo al enviar registro {register.id} a DGA")

            except Exception as e:
                error_count += 1
                error_msg = f"Error procesando registro {register.id}: {str(e)}"
                print(f"ERROR: {error_msg}")

        print(f"Proceso completado: {success_count} exitosos, {error_count} errores")

    except Exception as e:
        print(f"Error general en cron DGA: {str(e)}")


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
            print(f"Error: Fecha de medición no disponible para registro {register.id}")
            return False

        # Validar que tenga punto de captación
        if not register.catchment_point:
            print(
                f"Error: Punto de captación no disponible para registro {register.id}"
            )
            return False

        # Validar que tenga datos de caudal o total
        if not register.flow and not register.total:
            print(
                f"Error: No hay datos de caudal o total para enviar en registro {register.id}"
            )
            return False

        return True

    except Exception as e:
        print(f"Error validando registro {register.id}: {str(e)}")
        return False


def _get_dga_config(register: InteractionDetail) -> Optional[DgaDataConfigCatchment]:
    """
    Obtiene la configuración DGA para el punto de captación.

    Args:
        register: Registro de InteractionDetail

    Returns:
        DgaDataConfigCatchment o None si no se encuentra
    """
    try:
        dga_config = DgaDataConfigCatchment.objects.filter(
            point_catchment=register.catchment_point.id
        ).last()

        if not dga_config:
            return None

        # Validar que tenga los datos mínimos necesarios
        required_fields = [
            dga_config.code_dga,
            dga_config.rut_report_dga,
            dga_config.password_dga_software,
        ]

        if not all(required_fields):
            print(
                f"Configuración DGA incompleta para punto {register.catchment_point.id}"
            )
            return None

        return dga_config

    except Exception as e:
        print(
            f"Error obteniendo configuración DGA para registro {register.id}: {str(e)}"
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

        response_data = {
            "catchment_point": register.catchment_point.title,
            # Redondear a hora cerrada (minutos y segundos = 00) para API DGA
            "date_time_medition": date_time_medition_chile.replace(minute=0, second=0, microsecond=0).strftime(
                "%Y-%m-%dT%H:00:00"
            ),
            "total": register.total or "0",
            "flow": register.flow or 0.0,
            "water_table": register.water_table or 0.0,
            "type_dga": dga_config.type_dga,
            "code_dga": dga_config.code_dga,
            "id_data": register.id,
            "rut": dga_config.rut_report_dga,
            "password": dga_config.password_dga_software,
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
            print(f"Error: Configuración DGA incompleta para registro {register.id}")
            return None

        return response_data

    except Exception as e:
        error_msg = f"Error preparando datos para registro {register.id}: {str(e)}"
        print(f"ERROR: {error_msg}")
        return None
