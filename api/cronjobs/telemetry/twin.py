"""Twin 1/hour - UNIFICADO Y MEJORADO"""

import time
from datetime import datetime

import pytz

from api.core.models import CatchmentPoint, DgaDataConfigCatchment, InteractionDetail
from api.core.serializers import CatchmentPointSerializerDetailCron

# CONTROLADORES UNIFICADOS (mismos que twin_f1.py)
from .controllers.flow import (
    average_flow,
    instantaneous_flow,
    instantaneous_flow_calculate,
)
from .controllers.nivel import nivel_mt, water_table
from .controllers.total import total_day, total_hour, total_m3

# GETTERS UNIFICADOS
from .getters.tago import get_data_tago
from .getters.tdata import get_data_tdata
from .getters.thingsio import get_data_thethings


def run():
    """Punto de inicio de la ejecución frecuencia 1/h"""
    get_data = CatchmentPoint.objects.filter(
        is_tdata=True, data_config_profiles__is_telemetry=True, frecuency="60"
    )

    serializer = CatchmentPointSerializerDetailCron(get_data, many=True)

    for data in serializer.data:
        try:
            profile_data_config = data["profile_data_config"]
            if (
                "scheme" not in profile_data_config
                or "token_service" not in profile_data_config
            ):
                print("Missing key in profile_data_config")
                continue

            variables = profile_data_config["scheme"].get("variables")
            if variables is None:
                print(data)
                print("Missing key 'variables' in scheme")
                continue

            token = profile_data_config["token_service"]
            point_catchment = data
            get_data_twin(variables, token, point_catchment)
        except KeyError as e:
            print(f"Missing key in data dictionary: {e}")


def get_data_with_retry(getter_func, *args, max_retries=3, backoff_factor=2):
    """Retry inteligente con backoff exponencial"""
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
    point_catchment_id, variable_name, variable_type, success=True, error_msg=None
):
    """Logging estructurado para debugging"""
    if success:
        print(
            f"✅ Punto {point_catchment_id} - {variable_type} '{variable_name}' procesada"
        )
    else:
        print(
            f"❌ Punto {point_catchment_id} - Error en {variable_type} '{variable_name}': {error_msg}"
        )


def validate_frequency(point_catchment, current_time):
    """Validar si debe procesar según estándar"""
    try:
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


def get_data_twin(variables, token, point_catchment):
    """Get data by father twin - UNIFICADO Y MEJORADO"""
    chile = pytz.timezone("America/Santiago")
    created_register = {}
    date_time_last_logger_total = None
    created_register["date_time_medition"] = datetime.now(chile).strftime(
        "%Y-%m-%dT%H:00:00"
    )

    max_days_not_conection = 0  # ✅ TRACK WORST CASE (MAXIMUM)
    best_date_time_last_logger = None
    variable_details = [] # ✅ TRACK INDIVIDUAL VARIABLE STATUS

    # DISABLED: Validación de frecuencia (mantener comentada como en twin_f1.py)
    # current_time = datetime.now(chile)
    # if not validate_frequency(point_catchment, current_time):
    #     print(f"Punto {point_catchment['id']} no corresponde a frecuencia actual")
    #     return

    for variable in variables:
        data = None  # Inicializar data

        if variable.get("token_service"):
            if (
                variable.get("service") == "TWIN"
                and variable.get("type_variable") != "CAUDAL_PROMEDIO"
            ):
                token_twin = variable.get("token_service")
                data = get_data_with_retry(
                    get_data_tdata, 
                    token_twin, 
                    variable.get("str_variable")
                )
            elif (
                variable.get("service") == "NETTRA"
                and variable.get("type_variable") != "CAUDAL_PROMEDIO"
            ):
                token_nettra = variable.get("token_service")
                data = get_data_with_retry(
                    get_data_thethings, 
                    token_nettra, 
                    variable.get("str_variable")
                )
            elif (
                variable.get("service") == "NOVUS"
                and variable.get("type_variable") != "CAUDAL_PROMEDIO"
            ):
                token_novus = variable.get("token_service")
                data = get_data_with_retry(
                    get_data_tago, 
                    token_novus, 
                    variable.get("str_variable")
                )
        else:
            data = get_data_with_retry(
                get_data_tdata, 
                token, 
                variable.get("str_variable")
            )

        # Corregir error crítico: NO hacer continue, procesar con valor por defecto
        if data is None:
            if variable.get("type_variable") == "TOTALIZADO":
                data = {"value": 0, "date_time": None}
            else:
                data = {"value": 0.00, "date_time": None}
            # ✅ SE PROCESA CON VALOR 0 - NO SE PIERDE EL REGISTRO

        # Validar datos antes de procesar
        if not data.get("value") and data.get("value") != 0:
            print(f"Error: valor no válido para {variable.get('str_variable')}")
            data["value"] = 0

        type_variable = variable.get("type_variable")

        try:
            if type_variable == "TOTALIZADO":
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
                    point_catchment, None, created_register["total"]
                )
                created_register["date_time_last_logger"] = data["date_time"]
                date_time_last_logger_total = data["date_time"]

                log_variable_processing(
                    point_catchment["id"],
                    variable.get("str_variable"),
                    "TOTALIZADO",
                    True,
                )

            elif type_variable == "NIVEL":
                # Manejar nivel negativo
                try:
                    nivel_value = float(data["value"])
                except (ValueError, TypeError):
                    nivel_value = 0
                if nivel_value < 0:
                    # Buscar nivel más alto registrado
                    nivel_mas_alto = (
                        InteractionDetail.objects.filter(
                            catchment_point_id=point_catchment["id"]
                        )
                        .exclude(nivel__isnull=True)
                        .order_by("-nivel")
                        .first()
                    )

                    if nivel_mas_alto:
                        nivel_value = nivel_mas_alto.nivel
                        print(
                            f"Nivel negativo corregido usando valor más alto: {nivel_value}"
                        )
                    else:
                        nivel_value = 0

                # Caso especial para punto 149
                if point_catchment["id"] == 149:
                    created_register["nivel"] = nivel_mt(
                        float(nivel_value) - 17.0,
                        variable.get("calculate_nivel"),
                        point_catchment["id"],
                        point_catchment["profile_data_config"].get("d3", 0)
                    )
                else:
                    created_register["nivel"] = nivel_mt(
                        nivel_value,
                        variable.get("calculate_nivel"),
                        point_catchment["id"],
                        point_catchment["profile_data_config"].get("d3", 0)
                    )

                # Validar d3 antes de calcular nivel freático
                d3 = point_catchment["profile_data_config"].get("d3", 0)
                if not d3 or float(d3 if d3 else 0) <= 0:
                    print(f"Error: d3 no válido para punto {point_catchment['id']}")
                    d3 = 0

                created_register["water_table"] = water_table(
                    created_register["nivel"], d3
                )
                created_register["date_time_last_logger"] = data["date_time"]

                log_variable_processing(
                    point_catchment["id"], variable.get("str_variable"), "NIVEL", True
                )

            elif type_variable == "CAUDAL":
                created_register["flow"] = instantaneous_flow(
                    data["value"],
                    variable.get("convert_to_lt"),
                    variable.get("calculate_nivel"),
                )
                created_register["date_time_last_logger"] = data["date_time"]

                log_variable_processing(
                    point_catchment["id"], variable.get("str_variable"), "CAUDAL", True
                )

            elif type_variable == "CAUDAL_PROMEDIO":
                if date_time_last_logger_total:
                    created_register["flow"] = average_flow(
                        point_catchment,
                        created_register["total"],
                        datetime.strptime(
                            date_time_last_logger_total, "%Y-%m-%dT%H:%M:%S"
                        ),
                    )

                log_variable_processing(
                    point_catchment["id"],
                    variable.get("str_variable"),
                    "CAUDAL_PROMEDIO",
                    True,
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

        days_not_conection = 9999 # Default if no timestamp
        if created_register.get("date_time_last_logger"):
            date_time_medition = datetime.strptime(
                created_register["date_time_medition"], "%Y-%m-%dT%H:00:00"
            )
            date_time_last_logger = datetime.strptime(
                created_register["date_time_last_logger"], "%Y-%m-%dT%H:%M:%S"
            )
            days_not_conection = (date_time_medition - date_time_last_logger).days
            if days_not_conection < 0:
                days_not_conection = 0
            
            # ✅ TRACK MAXIMUM DISCONNECTION (Worst case scenario)
            if days_not_conection > max_days_not_conection:
                max_days_not_conection = days_not_conection
            
            # ✅ TRACK BEST HEARTBEAT (Most recent data)
            if best_date_time_last_logger is None or days_not_conection == 0:
                 best_date_time_last_logger = date_time_last_logger
        
        # ✅ COLLECT INDIVIDUAL STATUS (Always)
        variable_details.append({
            "name": variable.get("str_variable", "Var " + type_variable),
            "type": type_variable,
            "days": days_not_conection,
            "timestamp": created_register.get("date_time_last_logger")
        })

    # ✅ NOTIFICACIÓN DE RECONEXIÓN / DESCONEXIÓN (FUERA DEL LOOP)
    if best_date_time_last_logger or variable_details:
        created_register["days_not_conection"] = max_days_not_conection
        if best_date_time_last_logger:
            if isinstance(best_date_time_last_logger, str):
                created_register["date_time_last_logger"] = best_date_time_last_logger
            else:
                created_register["date_time_last_logger"] = best_date_time_last_logger.strftime("%Y-%m-%dT%H:%M:%S")
        
        # ✅ CALCULATE is_partial: True if some vars OK and some not
        ok_vars = sum(1 for v in variable_details if v.get('days', 9999) == 0)
        failing_vars = sum(1 for v in variable_details if v.get('days', 9999) > 0)
        created_register["is_partial"] = (ok_vars > 0 and failing_vars > 0)
        created_register["variable_details"] = variable_details # ✅ SAVE JSON

        try:
            from api.core.utils.google_chat import check_and_notify_reconnection, check_and_notify_disconnection
            
            date_time_medition = datetime.strptime(
                created_register["date_time_medition"], "%Y-%m-%dT%H:00:00"
            )
            
            check_and_notify_reconnection(
                point_id=point_catchment["id"],
                new_days_not_conection=max_days_not_conection,
                point_name=point_catchment.get("title", "Sin nombre"),
                client_name=point_catchment.get("project_info", {}).get("client_name", "N/A"),
                flow=created_register.get("flow"),
                nivel=created_register.get("nivel"),
                total=created_register.get("total"),
                date_time_medition=date_time_medition,
                date_time_last_logger=best_date_time_last_logger,
                variable_details=variable_details # ✅ PASS DETAILS
            )
            check_and_notify_disconnection(
                point_id=point_catchment["id"],
                new_days_not_conection=max_days_not_conection,
                point_name=point_catchment.get("title", "Sin nombre"),
                client_name=point_catchment.get("project_info", {}).get("client_name", "N/A"),
                date_time_medition=date_time_medition,
                variable_details=variable_details # ✅ PASS DETAILS
            )
        except Exception as e:
            print(f"Error en alerta reconexión/desconexión: {e}")

    get = DgaDataConfigCatchment.objects.get(point_catchment__id=point_catchment["id"])

    # Usar la hora del registro, no la hora actual del sistema
    record_time = datetime.strptime(created_register["date_time_medition"], "%Y-%m-%dT%H:00:00")

    # Solo enviar a DGA si está habilitado Y corresponde la frecuencia
    if get.send_dga and validate_frequency(point_catchment, record_time):
        created_register["send_dga"] = True
    else:
        created_register["send_dga"] = False

    # ✅ Crear o actualizar registro de forma atómica (previene duplicados)
    InteractionDetail.objects.update_or_create(
        catchment_point_id=point_catchment["id"],
        date_time_medition=created_register["date_time_medition"],
        defaults=created_register
    )
