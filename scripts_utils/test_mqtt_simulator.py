import paho.mqtt.client as mqtt
import json
import time
from datetime import datetime

# Configuración del Broker (mqtt_broker para Docker, localhost para host)
import os
BROKER = os.environ.get("MQTT_HOST", "mqtt_broker")
PORT = 1883
USER = "smarthydro"
PASSWORD = "dev_mqtt_password"

# Configuración del Dispositivo Nettra Simulado
DEVICE_ID = "nettra_001"
PROVIDER = "nettra_mqtt"
TOPIC = f"telemetry/{PROVIDER}/{DEVICE_ID}/data"

def simulate_device():
    client = mqtt.Client(client_id=f"sim_{DEVICE_ID}")
    client.username_pw_set(USER, PASSWORD)
    
    print(f"Conectando a {BROKER}:{PORT}...")
    try:
        client.connect(BROKER, PORT, 60)
    except Exception as e:
        print(f"Error de conexión: {e}")
        return

    print(f"Simulando dispositivo {DEVICE_ID}...")
    print(f"Publicando en topic: {TOPIC}")

    try:
        count = 0
        while True:
            # Payload simulado de Nettra (usando 'f' y 'v' como keys)
            payload = {
                "f": 12.5 + (count % 5),  # Caudal variable
                "v": 1000 + count,       # Volumen acumulado
                "ts": datetime.now().isoformat()
            }
            
            client.publish(TOPIC, json.dumps(payload))
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Publicado: {payload}")
            
            count += 1
            time.sleep(10) # Enviar cada 10 segundos
    except KeyboardInterrupt:
        print("Simulación detenida por el usuario.")
    finally:
        client.disconnect()

if __name__ == "__main__":
    simulate_device()
