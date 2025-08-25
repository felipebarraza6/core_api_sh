"""Nettra 5/min."""
from datetime import datetime
import pytz
from api.core.models import CatchmentPoint, InteractionDetail, DgaDataConfigCatchment
from api.core.serializers import CatchmentPointSerializerDetailCron
from .getters.tdata import get_data_tdata
from .controllers.total import total_m3, total_hour, total_day
from .controllers.nivel import nivel_mt, water_table
from .controllers.flow import instantaneous_flow, average_flow
from django.utils.timezone import make_aware
from .getters.thingsio import get_data_thethings
from .getters.tago import get_data_tago


def run():
    """Punto de inicio de la ejecución frecuencia 1/m"""
    get_data = CatchmentPoint.objects.filter(
        is_thethings=True, data_config_profiles__is_telemetry=True, frecuency="5")

    serializer = CatchmentPointSerializerDetailCron(get_data, many=True)

    for data in serializer.data:
        try:
            profile_data_config = data["profile_data_config"]
            if "scheme" not in profile_data_config or "token_service" not in profile_data_config:
                print("Missing key in profile_data_config")
                continue

            variables = profile_data_config["scheme"].get("variables")
            if variables is None:
                print("Missing key 'variables' in scheme")
                continue

            token = profile_data_config["token_service"]
            point_catchment = data
            get_data_nettra(variables, token, point_catchment)
        except KeyError as e:
            print(f"Missing key in data dictionary: {e}")


def get_data_nettra(variables, token, point_catchment):
    """Get data by father netra"""
    chile = pytz.timezone("America/Santiago")
    created_register = {}
    date_time_last_logger_total = None
    created_register["date_time_medition"] = datetime.now(
        chile).strftime("%Y-%m-%dT%H:%M:00")

    for variable in variables:
        data = None  # Inicializar data

        if variable.get("token_service"):

            if variable.get("service") == "TWIN" and variable.get("str_variable") != "type_variable":
                token_twin = variable.get("token_service")
                data = get_data_tdata(token_twin, variable.get("str_variable"))
            elif variable.get("service") == "NETTRA" and variable.get("str_variable") != "type_variable":
                token_nettra = variable.get("token_service")
                data = get_data_thethings(
                    token_nettra, variable.get("str_variable"))
            elif variable.get("service") == "NOVUS" and variable.get("str_variable") != "type_variable":
                token_novus = variable.get("token_service")
                data = get_data_tago(token_novus, variable.get("str_variable"))
        else:
            data = get_data_thethings(
                token, variable.get("str_variable"))

        if data is None:
            if variable.get("type_variable") == "TOTALIZADO":
                data = {"value": 0, "date_time": None}
            else:
                data = {"value": 0.00, "date_time": None}
            continue

        type_variable = variable.get("type_variable")

        if type_variable == "TOTALIZADO":
            try:
                value = int(float(data['value']))

                created_register["pulses"] = value
            except Exception as e:
                value = 0

            created_register["total"] = total_m3(variable.get(
                "pulses_factor"), value, point_catchment)
            created_register["total_diff"] = total_hour(
                created_register["total"], point_catchment)
            created_register["total_today_diff"] = total_day(
                created_register["total"], point_catchment)
            created_register["date_time_last_logger"] = data["date_time"]
            date_time_last_logger_total = data["date_time"]

        elif type_variable == "NIVEL":
            created_register["nivel"] = nivel_mt(
                data["value"], variable.get("calculate_nivel"))
            created_register["water_table"] = water_table(
                created_register["nivel"], point_catchment["profile_data_config"]['d3'])
            created_register["date_time_last_logger"] = data["date_time"]

        elif type_variable == "CAUDAL":
            created_register["flow"] = instantaneous_flow(
                data["value"], variable.get("convert_to_lt"), variable.get("calculate_nivel")
            )

        elif type_variable == "CAUDAL_PROMEDIO":
            if date_time_last_logger_total:
                created_register["flow"] = average_flow(
                    point_catchment, created_register['total'], datetime.strptime(date_time_last_logger_total, "%Y-%m-%dT%H:%M:%S"))

        else:
            print("Invalid type_variable")

        if created_register.get('date_time_last_logger'):
            date_time_medition = datetime.strptime(
                created_register['date_time_medition'], "%Y-%m-%dT%H:%M:00")
            date_time_last_logger = datetime.strptime(
                created_register['date_time_last_logger'], "%Y-%m-%dT%H:%M:%S")
            days_not_conection = (date_time_medition -
                                  date_time_last_logger).days
            created_register['days_not_conection'] = max(days_not_conection, 0)

    get = DgaDataConfigCatchment.objects.get(
        point_catchment__id=point_catchment["id"])

    current_minute = datetime.now(chile).minute
    if current_minute == 0:
        if get.standard == "MAYOR":
            created_register["send_dga"] = get.send_dga
        
        if get.standard == "MEDIO":
            today = datetime.now(chile).strftime("%Y-%m-%d")
            last_interaction = InteractionDetail.objects.filter(
                catchment_point_id=point_catchment["id"], 
                date_time_medition__date=today, 
                send_dga=True
            ).exists()
            
            if not last_interaction:
                created_register["send_dga"] = get.send_dga
                
        if get.standard == "MENOR":
            created_register["send_dga"] = get.send_dga
            
        if get.standard == "CAUDALES_MUY_PEQUENOS":
            created_register["send_dga"] = get.send_dga

    InteractionDetail.objects.create(
        catchment_point_id=point_catchment["id"], **created_register)
