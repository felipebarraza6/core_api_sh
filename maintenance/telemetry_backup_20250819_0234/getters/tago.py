from datetime import datetime
import time
import requests


def get_data_tago(token_service, str_variable):
    """Obtener datos de THETHINGS."""

    token = token_service  # Reemplazar "YOUR_TOKEN" con el valor real del token
    url = f"https://api.tago.io/data/?variable={str_variable}&query=last_item"
    for _ in range(3):  # Intentar hasta 3 veces
        try:
            response = requests.request("GET", url, timeout=5, headers={
                                        "authorization": token})
            response.raise_for_status()
            data = response.json()
            if data and data['result'] and len(data['result']) > 0:
                item = data['result'][0]
                ts = datetime.strptime(
                    item.get('time'), "%Y-%m-%dT%H:%M:%S.%fZ")
                formatted_ts = ts.strftime("%Y-%m-%dT%H:%M:%S")
                value = item.get("value", 0)
                if isinstance(value, int) and value < 0:
                    value = 0
                elif isinstance(value, float):
                    value = round(value, 2)
                return {"date_time": formatted_ts, "value": value}
            else:
                return {"date_time": None, "value": 0}
        except requests.RequestException as e:
            print(f"Error al obtener datos: {e}")
            time.sleep(1)  # Esperar 1 segundo antes de reintentar (retry)
    return {"date_time": None, "value": 0}
