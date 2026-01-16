import json
import time

import requests

from api.core.models import InteractionDetail


def send(response):
    """Envio DGA via API REST."""

    def convertir_a_int(cadena):
        total1 = cadena
        total2 = 0
        total3 = 0
        if response["catchment_point"] == 83:
            total2 = InteractionDetail.objects.filter(catchment_point=84).last().total
            total3 = InteractionDetail.objects.filter(catchment_point=85).last().total
            cadena = int(total1 + total2 + total3)

        try:
            return int(cadena)
        except ValueError:
            try:
                return int(float(cadena))
            except ValueError:
                return 0

    # URL base para la API REST de DGA
    base_url = "https://apimee.mop.gob.cl/api/v1"

    codigo_obra = response["code_dga"]
    time_stamp_origen = response["date_time_medition"]  # Sin Z - formato DGA
    fecha_medicion = (
        f"{response['date_time_medition'][0:4]}-"
        f"{response['date_time_medition'][5:7]}-"
        f"{response['date_time_medition'][8:10]}"
    )
    hora_medicion = response["date_time_medition"][11:19]
    totalizador = convertir_a_int(response["total"])
    caudal = float(response["flow"]) if response["flow"] is not None else 0.0
    rut = response["rut"]
    password = response["password"]
    id_interaction = response["id_data"]
    nivel_freatico_del_pozo = (
        float(response["water_table"]) if response["water_table"] is not None else 0.0
    )
    catchment_point = response["catchment_point"]
    type_dga = response["type_dga"]

    # Validaciones de caudal y nivel freatico
    if caudal < 0 or caudal is None:
        caudal = 0.0

    if nivel_freatico_del_pozo < 0 or nivel_freatico_del_pozo is None:
        nivel_freatico_del_pozo = 0.0

    print(
        f"Enviando datos a DGA: {catchment_point}: {codigo_obra} - "
        f"{fecha_medicion} {hora_medicion} - {totalizador} - "
        f"{caudal} - {nivel_freatico_del_pozo}"
    )

    # Obtener rutEmpresa desde la configuración DGA (nuevo campo)
    rut_empresa = getattr(response.get("dga_config", {}), "rut_empresa", "76944359-2")

    if type_dga == "SUBTERRANEO":
        url = f"{base_url}/mediciones/subterraneas"

        payload = json.dumps(
            {
                "autenticacion": {
                    "password": password,
                    "rutUsuario": rut,
                    "rutEmpresa": rut_empresa,
                },
                "medicionSubterranea": {
                    "caudal": str(caudal),
                    "fechaMedicion": fecha_medicion,
                    "horaMedicion": hora_medicion,
                    "totalizador": str(totalizador),
                    "nivelFreaticoDelPozo": str(nivel_freatico_del_pozo),
                },
            }
        )

        headers = {
            "codigoObra": codigo_obra,
            "timeStampOrigen": time_stamp_origen,
            "Content-Type": "application/json",
        }

    else:
        # Endpoint para SUPERFICIAL
        url = f"{base_url}/mediciones/superficiales/flujometro"

        payload = json.dumps(
            {
                "autenticacion": {
                    "password": password,
                    "rutUsuario": rut,
                    "rutEmpresa": rut_empresa,
                },
                "medicionSuperficialFlujometro": {
                    "caudal": str(caudal),
                    "fechaMedicion": fecha_medicion,
                    "horaMedicion": hora_medicion,
                    "totalizador": str(totalizador),
                },
            }
        )

        headers = {
            "codigoObra": codigo_obra,
            "timeStampOrigen": time_stamp_origen,
            "Content-Type": "application/json",
        }

    for _ in range(3):  # Intentar hasta 3 veces
        try:
            response_api = requests.post(url, headers=headers, data=payload, timeout=10)
            # Comentamos raise_for_status para manejar 400 manualmente

            # Manejar respuesta 400 para duplicados
            if response_api.status_code == 400:
                try:
                    error_data = response_api.json()
                    error_message = error_data.get("message", "Error 400")
                    
                    # Verificar si es registro duplicado
                    if "Ya existe un registro" in error_message and "Comprobante:" in error_message:
                        # Extraer comprobante
                        import re
                        comprobante_match = re.search(r'Comprobante: ([a-zA-Z0-9]+)', error_message)
                        numero_comprobante = comprobante_match.group(1) if comprobante_match else "Duplicado"
                        
                        print(f"REGISTRO DUPLICADO - Ya enviado: {numero_comprobante}")
                        
                        # Marcar como enviado exitosamente
                        InteractionDetail.objects.filter(id=id_interaction).update(
                            return_dga=f"Duplicado: {error_message}",
                            send_dga=False,  # Ya no pendiente
                            n_voucher=numero_comprobante,
                            is_error=False,  # Es éxito (ya estaba enviado)
                        )
                        
                        time.sleep(12)  # Rate limit
                        print("DEBUG: Retornando True por duplicado exitoso")
                        return True
                    else:
                        # 🔴 ERRORES ESPECÍFICOS PARA NO REINTENTAR
                        if "Usuario no es el informante registrado en la Obra" in error_message:
                            print(f"ERROR IRRECUPERABLE: {error_message}")
                            InteractionDetail.objects.filter(id=id_interaction).update(
                                return_dga=f"Error DGA Irrecuperable: {error_message}",
                                send_dga=False,  # 🛑 Detener envíos para este registro
                                is_error=True,
                            )
                            return False

                        print(f"ERROR 400 REAL: {error_message}")
                        # Continuar con reintentos para errores 400 reales
                        continue
                        
                except json.JSONDecodeError:
                    print("Error 400 sin JSON válido")
                    continue
            
            # Si llegamos aquí y no es código 200, continuar con reintentos
            elif response_api.status_code != 200:
                print(f"Error HTTP {response_api.status_code}: {response_api.text}")
                continue


            print(f"Respuesta DGA: {response_api.status_code}")
            print(f"Contenido: {response_api.text}")

            # Parsear respuesta JSON
            try:
                response_data = response_api.json()
                status = response_data.get("status")
                message = response_data.get("message", "Sin mensaje")
                data = response_data.get("data", {})

                is_send = False
                is_error = False
                numero_comprobante = None

                if status == "00":  # Éxito
                    is_send = True
                    numero_comprobante = data.get("numeroComprobante")
                    print(f"Éxito: {message} - Comprobante: {numero_comprobante}")
                else:
                    is_error = True
                    print(f"Error: {message}")

                # Actualizar registro en la base de datos
                InteractionDetail.objects.filter(id=id_interaction).update(
                    return_dga=message,
                    # Si se envió correctamente, marcar como no pendiente
                    send_dga=not is_send,
                    n_voucher=numero_comprobante,
                    is_error=is_error,
                )

                if is_send:
                    time.sleep(12)  # Esperar 12 segundos antes de continuar (rate limit DGA)
                print(f"DEBUG: Retornando is_send={is_send}")
                return is_send

            except json.JSONDecodeError as e:
                print(f"Error al parsear respuesta JSON: {e}")
                error_msg = (
                    f"Error: Respuesta inválida del servidor DGA - "
                    f"{response_api.text}"
                )
                InteractionDetail.objects.filter(id=id_interaction).update(
                    return_dga=error_msg,
                    n_voucher="No se pudo obtener el comprobante",
                    send_dga=True,
                    is_error=True,
                )
                print("DEBUG: Retornando False por error JSON")
                return False

        except requests.RequestException as e:
            print(f"ERROR de conexión - Exception: {e}")
            time.sleep(12)  # Esperar 12 segundos antes de reintentar (rate limit DGA)
        except Exception as e:
            print(f"Error inesperado: {e}")
            break

    # Si llegamos aquí, es porque fallaron los 3 intentos
    InteractionDetail.objects.filter(id=id_interaction).update(
        return_dga="Error: El servidor DGA no está respondiendo.",
        n_voucher="No se pudo obtener el comprobante",
        send_dga=True,
        is_error=True,
    )
    print("DEBUG: Retornando False por fallos en intentos")
    return False  # MODIFICADO: Retornar False cuando fallan todos los intentos
