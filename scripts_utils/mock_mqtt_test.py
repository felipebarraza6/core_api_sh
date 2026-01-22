import paho.mqtt.client as mqtt
import json
import time
import sys

def send_mock_data(host, port, topic, device_id):
    client = mqtt.Client(f"mock_sender_{device_id}")
    
    try:
        print(f"Connecting to {host}:{port}...")
        client.connect(host, port)
        
        data = {
            "device_id": device_id,
            "flow": 12.5,
            "pulses": 4500,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")
        }
        
        payload = json.dumps(data)
        print(f"Publishing to {topic}: {payload}")
        client.publish(topic, payload)
        
        client.disconnect()
        print("Done.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    # Usage: python mock_mqtt.py localhost 1883 smarthydro/POZO-01/data POZO-01
    h = sys.argv[1] if len(sys.argv) > 1 else "localhost"
    p = int(sys.argv[2]) if len(sys.argv) > 2 else 1883
    t = sys.argv[3] if len(sys.argv) > 3 else "smarthydro/mock/data"
    d = sys.argv[4] if len(sys.argv) > 4 else "MOCK-DEVICE"
    
    send_mock_data(h, p, t, d)
