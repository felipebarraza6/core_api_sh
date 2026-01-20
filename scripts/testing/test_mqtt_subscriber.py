#!/usr/bin/env python
"""
Script de testing para MQTT Subscriber.

Simula dispositivos NXTRA/Novus enviando datos al broker.
"""

import json
import time
import paho.mqtt.client as mqtt
from datetime import datetime


class MQTTTestPublisher:
    """Publicador de mensajes de prueba."""

    def __init__(self, broker_host='localhost', broker_port=1883):
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.client = mqtt.Client(client_id="test_publisher")

    def connect(self):
        """Conectar al broker."""
        print(f"🔌 Conectando a {self.broker_host}:{self.broker_port}...")
        self.client.connect(self.broker_host, self.broker_port, keepalive=60)
        self.client.loop_start()
        print("✅ Conectado exitosamente")

    def disconnect(self):
        """Desconectar del broker."""
        self.client.loop_stop()
        self.client.disconnect()
        print("👋 Desconectado")

    def publish_nxtra_message(self, device_id="sensor01", flow=12.5, total=1234.56, nivel=2.3):
        """
        Publicar mensaje NXTRA formato JSON estándar.

        Args:
            device_id: ID del dispositivo
            flow: Caudal en L/s
            total: Total en m³
            nivel: Nivel en metros
        """
        topic = f"nxtra/{device_id}/data"

        payload = {
            "device_id": device_id,
            "timestamp": datetime.now().isoformat(),
            "data": {
                "flow": flow,
                "total_m3": total,
                "water_level": nivel
            }
        }

        payload_str = json.dumps(payload)

        print(f"\n📤 Publicando en topic: {topic}")
        print(f"   Payload: {payload_str}")

        result = self.client.publish(topic, payload_str, qos=1)

        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            print("   ✅ Mensaje publicado exitosamente")
        else:
            print(f"   ❌ Error publicando mensaje: {result.rc}")

        return result

    def publish_novus_message(self, device_id="novus_sensor02", pulses=123456, temp=25.3):
        """
        Publicar mensaje Novus formato JSON.

        Args:
            device_id: ID del dispositivo
            pulses: Pulsos totales
            temp: Temperatura
        """
        topic = f"novus/{device_id}/telemetry"

        payload = {
            "deviceId": device_id,
            "timestamp": int(datetime.now().timestamp()),
            "values": {
                "pulses": pulses,
                "temperature": temp,
                "battery": 95
            }
        }

        payload_str = json.dumps(payload)

        print(f"\n📤 Publicando en topic: {topic}")
        print(f"   Payload: {payload_str}")

        result = self.client.publish(topic, payload_str, qos=1)

        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            print("   ✅ Mensaje publicado exitosamente")
        else:
            print(f"   ❌ Error publicando mensaje: {result.rc}")

        return result

    def publish_nettra_message(self, device_id="nettra_001", flow=15.2, pressure=2.5):
        """
        Publicar mensaje NXTRA Nettra formato JSON custom.

        Args:
            device_id: ID del dispositivo
            flow: Caudal
            pressure: Presión
        """
        topic = f"nxtra/nettra/{device_id}/sensors"

        payload = {
            "deviceId": device_id,
            "timestamp": int(datetime.now().timestamp()),
            "sensors": {
                "flow_sensor": {
                    "value": flow,
                    "unit": "L/s"
                },
                "pressure_sensor": {
                    "value": pressure,
                    "unit": "bar"
                }
            }
        }

        payload_str = json.dumps(payload)

        print(f"\n📤 Publicando en topic: {topic}")
        print(f"   Payload: {payload_str}")

        result = self.client.publish(topic, payload_str, qos=1)

        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            print("   ✅ Mensaje publicado exitosamente")
        else:
            print(f"   ❌ Error publicando mensaje: {result.rc}")

        return result

    def simulate_continuous_data(self, device_type='nxtra', interval=5, count=10):
        """
        Simular envío continuo de datos.

        Args:
            device_type: Tipo de dispositivo (nxtra, novus, nettra)
            interval: Intervalo entre mensajes en segundos
            count: Cantidad de mensajes a enviar
        """
        print(f"\n🔄 Simulando {count} mensajes de tipo '{device_type}' cada {interval}s")
        print("   (Ctrl+C para detener)\n")

        try:
            for i in range(count):
                if device_type == 'nxtra':
                    # Simular valores variables
                    flow = 10 + (i % 5) * 2.5
                    total = 1000 + i * 5.2
                    nivel = 2.0 + (i % 3) * 0.5
                    self.publish_nxtra_message(flow=flow, total=total, nivel=nivel)

                elif device_type == 'novus':
                    pulses = 100000 + i * 100
                    temp = 20 + (i % 10) * 0.5
                    self.publish_novus_message(pulses=pulses, temp=temp)

                elif device_type == 'nettra':
                    flow = 12 + (i % 7) * 1.5
                    pressure = 2.0 + (i % 4) * 0.3
                    self.publish_nettra_message(flow=flow, pressure=pressure)

                if i < count - 1:
                    print(f"\n⏳ Esperando {interval}s...\n")
                    time.sleep(interval)

            print(f"\n✅ Simulación completada: {count} mensajes enviados")

        except KeyboardInterrupt:
            print("\n\n⚠️  Simulación interrumpida por el usuario")


def main():
    """Función principal de testing."""
    import argparse

    parser = argparse.ArgumentParser(description='Test MQTT Subscriber')
    parser.add_argument('--host', default='localhost', help='Broker MQTT host')
    parser.add_argument('--port', type=int, default=1883, help='Broker MQTT port')
    parser.add_argument('--type', choices=['nxtra', 'novus', 'nettra', 'all'],
                        default='nxtra', help='Tipo de dispositivo a simular')
    parser.add_argument('--simulate', action='store_true',
                        help='Simular envío continuo')
    parser.add_argument('--interval', type=int, default=5,
                        help='Intervalo entre mensajes (segundos)')
    parser.add_argument('--count', type=int, default=10,
                        help='Cantidad de mensajes a enviar')

    args = parser.parse_args()

    # Crear publicador
    publisher = MQTTTestPublisher(args.host, args.port)

    try:
        publisher.connect()
        time.sleep(1)  # Esperar conexión

        if args.simulate:
            if args.type == 'all':
                print("\n🎯 Simulando TODOS los tipos de dispositivos\n")
                for device_type in ['nxtra', 'novus', 'nettra']:
                    publisher.simulate_continuous_data(
                        device_type=device_type,
                        interval=args.interval,
                        count=args.count
                    )
                    time.sleep(2)
            else:
                publisher.simulate_continuous_data(
                    device_type=args.type,
                    interval=args.interval,
                    count=args.count
                )
        else:
            # Enviar un solo mensaje
            if args.type == 'nxtra':
                publisher.publish_nxtra_message()
            elif args.type == 'novus':
                publisher.publish_novus_message()
            elif args.type == 'nettra':
                publisher.publish_nettra_message()
            elif args.type == 'all':
                publisher.publish_nxtra_message()
                time.sleep(1)
                publisher.publish_novus_message()
                time.sleep(1)
                publisher.publish_nettra_message()

        time.sleep(2)  # Esperar envío

    except Exception as e:
        print(f"\n❌ Error: {e}")

    finally:
        publisher.disconnect()


if __name__ == '__main__':
    main()
