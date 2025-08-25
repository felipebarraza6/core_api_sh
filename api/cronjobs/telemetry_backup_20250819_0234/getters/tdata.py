"""Script TDATA."""
import json
import requests
from datetime import datetime
import time


def get_token():
    """Obtener token de autenticación."""
    url = "https://api.twindimension.com/tdata/v1/login"
    payload = json.dumps({
        "username": "sadmin.smarthydro@twindimension.io",
        "password": "Smart.1238"
    })
    headers = {
        'Content-Type': 'application/json'
    }
    response = requests.request(
        "POST", url, headers=headers, data=payload, timeout=5)
    response_data = response.json()
    return response_data["token"]


def get_data_tdata(token_service, str_variable):
    """Obtener datos de TDATA."""
    token_auth = get_token()
    if not token_auth:
        print("No se pudo obtener el token de autenticación.")
        return {"date_time": None, "value": 0}

    token = token_service  # Reemplazar "YOUR_TOKEN" con el valor real del token

    url = f"https://api.twindimension.com/tdata/v1/telemetry/DEVICE/{token}/values/timeseries?keys={str_variable}"
    headers = {
        'Authorization': f"Bearer {token_auth}"
    }
    print(str_variable)
    print(token)
    for _ in range(3):  # Intentar hasta 3 veces
        try:
            response = requests.request("GET", url, headers=headers, timeout=5)
            response.raise_for_status()
            data = response.json()
            print(data)
            if str_variable in data and data[str_variable]:
                item = data[str_variable][-1]  # Obtener el último elemento
                ts = datetime.fromtimestamp(item["ts"] / 1000)
                formatted_ts = ts.strftime("%Y-%m-%dT%H:%M:%S")
                value = item.get("value", 0)
                return {"date_time": formatted_ts, "value": value}
            else:
                return {"date_time": None, "value": 0}
        except requests.RequestException as e:
            print(f"Error al obtener datos: {e}")
            time.sleep(1)  # Esperar 1 segundo antes de reintentar
    return {"date_time": None, "value": 0}
