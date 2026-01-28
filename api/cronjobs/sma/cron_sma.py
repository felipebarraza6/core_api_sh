"""Cron SEND DATA SMA."""

import json
from typing import Optional

import pytz
import requests

from api.core.models import DgaDataConfigCatchment, InteractionDetail


def run():
    """Ejecutar cronjob SMA"""
    print("🚀 Iniciando cronjob SMA...")

    # Lista de IDs de puntos de captación para SMA
    # Agregar aquí los IDs que quieres que envíen a SMA
    sma_catchment_points = [1]  # Por ahora solo ID 1, agregar más según necesites

    # Obtener token de autenticación
    token = _get_sma_token()
    if not token:
        print("❌ No se pudo obtener token de SMA")
        return

    # Obtener registros recientes sin voucher (no enviados) para SMA
    from datetime import datetime, timedelta

    import pytz

    chile = pytz.timezone("America/Santiago")
    ahora = datetime.now(chile)
    hace_10_minutos = ahora - timedelta(hours=2)

    data_for_send = InteractionDetail.objects.filter(
        catchment_point_id__in=sma_catchment_points,
        created__gte=hace_10_minutos,
        # send_dga=True,  # REMOVIDO - SMA funciona independiente
        n_voucher__isnull=True,  # Solo registros sin voucher (no enviados aún)
    ).order_by("-created")[:10]

    # Filtrar solo registros con date_time_medition en minutos 5
    filtered_data = []
    for register in data_for_send:
        try:
            # Parsear date_time_medition
            if register.date_time_medition:
                dt = register.date_time_medition if isinstance(register.date_time_medition, datetime) else datetime.strptime(register.date_time_medition, "%Y-%m-%dT%H:%M:%S")
                if dt.minute % 5 == 0:  # Solo minutos múltiplos de 5 (0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55)
                    filtered_data.append(register)
                    print(
                        f"✅ Registro {register.id} válido (minuto {dt.minute}): {register.date_time_medition}"
                    )
                else:
                    print(
                        f"❌ Registro {register.id} descartado (minuto {dt.minute}): {register.date_time_medition}"
                    )
        except Exception as e:
            print(
                f"❌ Error parseando date_time_medition del registro {register.id}: {e}"
            )

    print(f"📊 Registros con registros encontrados: {len(filtered_data)}")

    for register in filtered_data:
        try:
            print(
                f"📋 Procesando registro ID: {register.id} - Punto: {register.catchment_point_id}"
            )

            # Obtener configuración DGA para este punto
            dga_config = DgaDataConfigCatchment.objects.get(
                point_catchment_id=register.catchment_point_id
            )

            # Validar registro
            if not _validate_register(register):
                print(f"❌ Registro {register.id} no válido, saltando...")
                continue

            # Preparar datos para SMA
            response_data = _prepare_response_data(register, dga_config)
            if not response_data:
                print(f"❌ No se pudieron preparar datos para registro {register.id}")
                continue

            # Enviar a SMA
            success, message, id_verificacion = _send_to_sma(
                response_data, token, dga_config
            )

            # Actualizar registro
            register.return_dga = message
            register.n_voucher = id_verificacion

            if success:
                register.send_dga = False  # Ya enviado exitosamente
                register.is_error = False
                print(f"✅ Registro {register.id} enviado exitosamente a SMA")
            else:
                register.send_dga = True  # Mantener en cola para reintento
                register.is_error = True
                print(f"❌ Error enviando registro {register.id} a SMA: {message}")

            register.save()

        except Exception as e:
            print(f"❌ Error procesando registro {register.id}: {e}")
            # Marcar como error pero mantener en cola
            register.return_dga = f"Error: {e}"
            register.is_error = True
            register.send_dga = True
            register.save()

    print("🏁 Cronjob SMA completado")


def _get_sma_token() -> Optional[str]:
    """
    Obtiene el token de autenticación de SMA.

    Returns:
        str: Token de autenticación o None si hay error
    """
    try:
        url = "https://conexiones.sma.gob.cl/api/v1/auth"

        payload = {"usuario": "76006727-K", "password": "{O=+b_k_aD"}

        headers = {"Content-Type": "application/json"}

        print("Obteniendo token de autenticación SMA...")

        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()

        response_data = response.json()
        token = response_data.get("token")

        if token:
            print("✅ Token obtenido exitosamente")
            return token
        else:
            print("❌ No se encontró token en la respuesta")
            return None

    except requests.RequestException as e:
        print(f"Error obteniendo token SMA: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"Error parseando respuesta del token: {e}")
        return None
    except Exception as e:
        print(f"Error inesperado obteniendo token: {e}")
        return None


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
        if not dga_config.code_dga or not dga_config.flow_granted_dga:
            print(
                f"Configuración DGA incompleta para punto "
                f"{register.catchment_point.id}"
            )
            return None

        return dga_config

    except Exception as e:
        print(
            f"Error obteniendo configuración DGA para registro "
            f"{register.id}: {str(e)}"
        )
        return None


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
                f"Error: No hay datos de caudal o total para enviar en registro "
                f"{register.id}"
            )
            return False

        return True

    except Exception as e:
        print(f"Error validando registro {register.id}: {str(e)}")
        return False


def _prepare_response_data(
    register: InteractionDetail, dga_config: DgaDataConfigCatchment
) -> Optional[dict]:
    """
    Prepara los datos para envío a SMA.

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

        # Formatear fecha para SMA
        estampa_tiempo = date_time_medition_chile.strftime("%Y-%m-%dT%H:%M:%S")

        # Preparar parámetros
        parametros = []

        # Parámetro Q (caudal/flow) - usar siempre flow
        if register.flow is not None:
            parametros.append(
                {
                    "nombre": "Q",
                    "valor": str(register.flow),
                    "unidad": "l/s",
                    "estampaTiempo": estampa_tiempo,
                }
            )

        # Parámetro VA (acumulado/total)
        if register.total is not None:
            parametros.append(
                {
                    "nombre": "VA",
                    "valor": str(register.total),
                    "unidad": "m3",
                    "estampaTiempo": estampa_tiempo,
                }
            )

        if not parametros:
            print(f"Error: No hay parámetros válidos para registro {register.id}")
            return None

        response_data = [
            {
                "dispositivoId": "12180",  # ID fijo como especificaste
                "parametros": parametros,
            }
        ]

        return response_data

    except Exception as e:
        error_msg = f"Error preparando datos para registro {register.id}: {str(e)}"
        print(f"ERROR: {error_msg}")
        return None


def _send_to_sma(
    data: dict, token: str, dga_config: DgaDataConfigCatchment
) -> tuple[bool, str, str]:
    """
    Envía datos a SMA.

    Args:
        data: Datos a enviar
        token: Token de autenticación
        dga_config: Configuración DGA

    Returns:
        tuple: (success, message, id_verificacion)
    """
    try:
        # Construir endpoint dinámico basado en code_dga y total_granted_dga
        code_dga = dga_config.code_dga
        flow_granted_dga = dga_config.total_granted_dga

        if not code_dga:
            error_msg = "Error: No se encontró code_dga en la configuración"
            return False, error_msg, ""

        if not flow_granted_dga:
            error_msg = "Error: No se encontró total_granted_dga en la configuración"
            return False, error_msg, ""

        # Extraer el número del code_dga (ejemplo: "7511" de "OB-7511-123")
        import re

        numbers = re.findall(r"\d+", code_dga)
        if numbers:
            uf_id = numbers[0]  # Tomar el primer número encontrado
        else:
            error_msg = f"Error: No se pudo extraer UF ID del code_dga: {code_dga}"
            return False, error_msg, ""

        # Usar flow_granted_dga como ID del proceso
        proceso_id = str(int(flow_granted_dga))

        # Construir URL dinámica
        url = f"https://conexiones.sma.gob.cl/api/v1/ufs/{uf_id}/procesos/{proceso_id}/registros"

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }

        print(f"Enviando datos a SMA: {json.dumps(data, indent=2)}")
        print(f"URL: {url}")

        response = requests.post(url, headers=headers, json=data, timeout=30)
        response.raise_for_status()

        print(f"Respuesta SMA: {response.status_code}")
        print(f"Contenido: {response.text}")

        # Verificar respuesta
        try:
            response_data = response.json()
            if response.status_code == 200:
                # Extraer mensaje e ID de verificación
                mensaje = response_data.get("mensaje", "Datos enviados correctamente")
                id_verificacion = response_data.get("IdVerificacion", "")

                print("✅ Datos enviados correctamente a SMA")
                return True, mensaje, id_verificacion
            else:
                error_msg = f"Error enviando datos a SMA: {response_data}"
                return False, error_msg, ""
        except json.JSONDecodeError:
            error_msg = "Error parseando respuesta de SMA"
            return False, error_msg, ""

    except requests.RequestException as e:
        error_msg = f"Error enviando datos a SMA: {e}"
        return False, error_msg, ""
    except Exception as e:
        error_msg = f"Error inesperado enviando datos: {e}"
        return False, error_msg, ""
