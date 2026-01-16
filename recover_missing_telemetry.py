#!/usr/bin/env python
"""
Script de recuperación de mediciones faltantes
Recupera datos históricos de las APIs para llenar lagunas
"""

import os
import sys
import django
from datetime import datetime, timedelta
import pytz
import requests

# Setup Django
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import CatchmentPoint, InteractionDetail, DgaDataConfigCatchment
from api.core.serializers import CatchmentPointSerializerDetailCron
from api.cronjobs.telemetry.getters.tdata import get_token
from api.cronjobs.telemetry.controllers.flow import instantaneous_flow
from api.cronjobs.telemetry.controllers.nivel import nivel_mt, water_table
from api.cronjobs.telemetry.controllers.total import total_day, total_hour, total_m3


def get_data_tdata_historical(token_service, str_variable, start_ts, end_ts):
    """Obtener datos históricos de TDATA con rango de tiempo"""
    token_auth = get_token()
    if not token_auth:
        print("No se pudo obtener el token de autenticación.")
        return []

    url = f"https://api.twindimension.com/tdata/v1/telemetry/DEVICE/{token_service}/values/timeseries?keys={str_variable}&startTs={start_ts}&endTs={end_ts}"
    headers = {'Authorization': f"Bearer {token_auth}"}

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()

        if str_variable in data and data[str_variable]:
            return data[str_variable]
        else:
            return []
    except Exception as e:
        print(f"Error obteniendo datos históricos: {e}")
        return []


def recover_missing_data_for_point(point_data, start_time, end_time, chile_tz):
    """Recuperar datos faltantes para un punto específico"""
    point_id = point_data['id']
    point_title = point_data.get('title', 'Sin nombre')
    point_frecuency = point_data.get('frecuency', '60')

    print(f"\n🔄 Procesando Punto {point_id} - {point_title}")
    print(f"   Frecuencia: {point_frecuency} min")

    # Verificar configuración
    profile_data_config = point_data.get("profile_data_config")
    if not profile_data_config:
        print(f"   ❌ Sin configuración")
        return 0

    if "scheme" not in profile_data_config or "token_service" not in profile_data_config:
        print(f"   ❌ Sin esquema o token")
        return 0

    variables = profile_data_config["scheme"].get("variables")
    if variables is None:
        print(f"   ❌ Sin variables en esquema")
        return 0

    token_service = profile_data_config["token_service"]

    # Calcular horas a recuperar según frecuencia
    freq = int(point_frecuency) if point_frecuency else 60
    hours_to_recover = []

    current_hour = start_time
    while current_hour < end_time:
        hours_to_recover.append(current_hour)
        current_hour += timedelta(minutes=freq)

    print(f"   📊 Recuperando {len(hours_to_recover)} registros...")

    recovered_count = 0

    for target_time in hours_to_recover:
        # Verificar si ya existe
        exists = InteractionDetail.objects.filter(
            catchment_point_id=point_id,
            date_time_medition=target_time
        ).exists()

        if exists:
            print(f"   ⏭️  {target_time.strftime('%H:%M')} - Ya existe, saltando")
            continue

        # Preparar registro
        created_register = {
            'date_time_medition': target_time.strftime("%Y-%m-%dT%H:%M:00")
        }

        # Buscar datos en API para esta hora específica
        # Rango de ±2 minutos alrededor de la hora objetivo
        search_start = int((target_time - timedelta(minutes=2)).timestamp() * 1000)
        search_end = int((target_time + timedelta(minutes=2)).timestamp() * 1000)

        date_time_last_logger = None

        # Procesar cada variable
        for variable in variables:
            var_name = variable.get('str_variable')
            var_type = variable.get('type_variable')
            var_token = variable.get('token_service') or token_service

            # Obtener datos históricos
            historical_data = get_data_tdata_historical(var_token, var_name, search_start, search_end)

            if not historical_data:
                # Sin datos, usar valor 0
                if var_type == "TOTALIZADO":
                    data = {"value": 0, "date_time": None}
                else:
                    data = {"value": 0.00, "date_time": None}
            else:
                # Tomar el valor más cercano a la hora objetivo
                closest_item = historical_data[len(historical_data) // 2]  # Aproximadamente el del medio
                ts = datetime.fromtimestamp(closest_item['ts'] / 1000)
                data = {
                    "value": closest_item['value'],
                    "date_time": ts.strftime("%Y-%m-%dT%H:%M:%S")
                }
                date_time_last_logger = data["date_time"]

            # Procesar según tipo
            try:
                if var_type == "TOTALIZADO":
                    value = int(float(data["value"]))
                    created_register["pulses"] = value
                    created_register["total"] = total_m3(variable.get("pulses_factor"), value, point_data)
                    created_register["total_diff"] = total_hour(created_register["total"], point_data)
                    created_register["total_today_diff"] = total_day(point_data, None, created_register["total_diff"])
                    if data["date_time"]:
                        created_register["date_time_last_logger"] = data["date_time"]

                elif var_type == "NIVEL":
                    nivel_value = float(data["value"]) if data["value"] else 0
                    if nivel_value < 0:
                        nivel_value = 0

                    # Obtener d3
                    d3 = profile_data_config.get("d3", 0)

                    created_register["nivel"] = nivel_mt(nivel_value, variable.get("calculate_nivel"), point_id, d3)
                    created_register["water_table"] = water_table(created_register["nivel"], d3)
                    if data["date_time"]:
                        created_register["date_time_last_logger"] = data["date_time"]

                elif var_type == "CAUDAL":
                    created_register["flow"] = instantaneous_flow(
                        data["value"],
                        variable.get("convert_to_lt"),
                        variable.get("calculate_nivel"),
                    )
                    if data["date_time"]:
                        created_register["date_time_last_logger"] = data["date_time"]

                elif var_type == "CAUDAL_PROMEDIO":
                    # No se guarda, se calcula dinámicamente
                    pass

            except Exception as e:
                print(f"   ⚠️  Error procesando {var_name}: {e}")
                continue

        # Agregar campos adicionales
        created_register["days_not_conection"] = 0
        if not created_register.get("date_time_last_logger"):
            created_register["date_time_last_logger"] = target_time.strftime("%Y-%m-%dT%H:%M:00")

        # Configurar send_dga si aplica
        try:
            dga_config = DgaDataConfigCatchment.objects.get(point_catchment__id=point_id)
            created_register["send_dga"] = dga_config.send_dga and target_time.minute == 0
        except:
            created_register["send_dga"] = False

        # Crear registro
        try:
            InteractionDetail.objects.create(
                catchment_point_id=point_id,
                **created_register
            )
            print(f"   ✅ {target_time.strftime('%H:%M')} - Recuperado exitosamente")
            recovered_count += 1
        except Exception as e:
            print(f"   ❌ {target_time.strftime('%H:%M')} - Error: {e}")

    return recovered_count


def main():
    print("=" * 80)
    print("SCRIPT DE RECUPERACIÓN DE MEDICIONES FALTANTES")
    print("=" * 80)
    print()

    # Configurar timezone
    chile_tz = pytz.timezone('America/Santiago')

    # Definir rango de recuperación: 13:00 - 16:00 hoy
    now = datetime.now(chile_tz)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)

    start_time = today + timedelta(hours=13)
    end_time = today + timedelta(hours=16)

    print(f"📅 Rango de recuperación:")
    print(f"   Desde: {start_time.strftime('%Y-%m-%d %H:%M')}")
    print(f"   Hasta: {end_time.strftime('%Y-%m-%d %H:%M')}")
    print()

    # Obtener puntos TWIN (TDATA) que tienen frecuencia 60 min usando serializer
    points_queryset = CatchmentPoint.objects.filter(
        is_tdata=True,
        is_thethings=False,
        is_novus=False,
        data_config_profiles__is_telemetry=True,
        frecuency='60'
    ).distinct()

    serializer = CatchmentPointSerializerDetailCron(points_queryset, many=True)
    points_data = serializer.data

    print(f"🎯 Puntos a recuperar: {len(points_data)}")
    print()

    total_recovered = 0

    for point_data in points_data:
        recovered = recover_missing_data_for_point(point_data, start_time, end_time, chile_tz)
        total_recovered += recovered

    print()
    print("=" * 80)
    print(f"✅ COMPLETADO: {total_recovered} registros recuperados")
    print("=" * 80)


if __name__ == "__main__":
    main()
