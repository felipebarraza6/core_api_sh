import requests
from datetime import datetime
import time


def get_data_thethings(token_service, str_variable):
    """Obtener datos de THETHINGS´."""

    token = token_service  # Reemplazar "YOUR_TOKEN" con el valor real del token

    url = (f"https://api.thethings.io/v2/things/{token}/resources/{str_variable}")

    for _ in range(3):  # Intentar hasta 3 veces
        try:
            response = requests.request("GET", url, timeout=5)
            response.raise_for_status()
            data = response.json()
            print(token)
            print(data)
            if data and len(data) > 0:
                item = data[0]  # Obtener el último elemento
                ts = datetime.strptime(
                    item["datetime"], "%Y-%m-%dT%H:%M:%S.%fZ")
                formatted_ts = ts.strftime("%Y-%m-%dT%H:%M:%S")
                value = item.get("value", 0)
                print(value)
                print(formatted_ts)
                return {"value": value, "date_time": formatted_ts}
            else:
                return {"value": 0, "date_time": None}
        except requests.RequestException as e:
            print(f"Error al obtener datos: {e}")
            time.sleep(1)  # Esperar 1 segundo antes de reintentar
    return {"value": 0, "date_time": None}
