"""
Servicio MQTT para conexión directa de equipos IoT (V3)
Permite comunicación bidireccional y guardado en esquema dinámico V3
"""

import asyncio
import json
import logging
import ssl
import paho.mqtt.client as mqtt
from typing import Dict, List, Optional, Callable, Any

from django.conf import settings
from django.utils import timezone
from django.db import transaction

from ..models import (
    EquipmentProvider, IoTDevice, MQTTConnection, MQTTMessageLog,
    TelemetryRecord, CatchmentPoint
)
from api.telemetry.ingestion.controllers.unified_processing import save_telemetry_data

logger = logging.getLogger(__name__)


class MQTTService:
    """
    Servicio MQTT para gestión de conexiones y mensajes con equipos IoT (V3)
    """

    def __init__(self):
        self.clients: Dict[str, mqtt.Client] = {}
        self.message_handlers: Dict[str, Callable] = {}
        self._setup_message_handlers()

    def _setup_message_handlers(self):
        """Configurar handlers para diferentes tipos de mensajes"""
        self.message_handlers = {
            'telemetry': self._handle_telemetry_message,
            'status': self._handle_status_message,
            'configuration': self._handle_configuration_message,
            'command_response': self._handle_command_response,
        }

    async def initialize_connections(self):
        """Inicializar todas las conexiones MQTT activas"""
        active_connections = MQTTConnection.objects.filter(is_active=True)
        for connection in active_connections:
            try:
                await self.start_connection(connection)
            except Exception as exc:
                logger.error(f"Failed to initialize MQTT connection {connection.connection_name}: {exc}")

    async def start_connection(self, connection: MQTTConnection):
        """Iniciar una conexión MQTT específica"""
        client_id = connection.client_id
        client = mqtt.Client(client_id=client_id, clean_session=False)

        if connection.username:
            client.username_pw_set(connection.username, connection.password or "")

        if connection.use_tls:
            ssl_context = ssl.create_default_context()
            client.tls_set_context(ssl_context)

        client.on_connect = lambda c, u, f, rc: self._on_connect(c, connection, rc)
        client.on_disconnect = lambda c, u, rc: self._on_disconnect(c, connection, rc)
        client.on_message = lambda c, u, msg: self._on_message(c, connection, msg)

        try:
            client.connect(
                connection.broker_host,
                connection.broker_port,
                keepalive=connection.keep_alive_interval
            )

            for topic in connection.subscribe_topics:
                client.subscribe(topic, qos=1)

            client.loop_start()
            self.clients[client_id] = client

            connection.status = 'CONNECTED'
            connection.last_connected = timezone.now()
            connection.connection_errors = 0
            connection.save()

        except Exception as exc:
            logger.error(f"Failed to connect to MQTT broker: {exc}")
            connection.status = 'ERROR'
            connection.connection_errors += 1
            connection.save()
            raise

    def _on_connect(self, client, connection: MQTTConnection, rc):
        if rc == 0:
            connection.status = 'CONNECTED'
            connection.last_connected = timezone.now()
            connection.connection_errors = 0
        else:
            connection.status = 'ERROR'
            connection.connection_errors += 1
        connection.save()

    def _on_disconnect(self, client, connection: MQTTConnection, rc):
        connection.status = 'DISCONNECTED'
        connection.last_disconnected = timezone.now()
        if rc != 0:
            connection.status = 'CONNECTING'
        connection.save()

    def _on_message(self, client, connection: MQTTConnection, msg):
        try:
            try:
                payload = json.loads(msg.payload.decode('utf-8'))
            except json.JSONDecodeError:
                payload = {'raw_data': msg.payload.decode('utf-8')}

            self._log_mqtt_message(connection, msg, payload)
            asyncio.create_task(self._process_message(connection, msg.topic, payload))
        except Exception as exc:
            logger.error(f"Error processing MQTT message: {exc}")

    def _log_mqtt_message(self, connection: MQTTConnection, msg, payload):
        try:
            device_id = self._extract_device_id(msg.topic, payload)
            device = IoTDevice.objects.filter(device_id=device_id).first() if device_id else None

            MQTTMessageLog.objects.create(
                connection=connection,
                device=device,
                message_type='PUBLISH',
                topic=msg.topic,
                payload=payload,
                qos=msg.qos,
                retained=msg.retain
            )

            connection.messages_received_today += 1
            connection.bytes_received_today += len(str(payload))
            connection.save(update_fields=['messages_received_today', 'bytes_received_today'])
        except Exception as exc:
            logger.error(f"Error logging MQTT message: {exc}")

    def _extract_device_id(self, topic: str, payload: dict) -> Optional[str]:
        topic_parts = topic.split('/')
        if len(topic_parts) >= 2:
            return topic_parts[1]
        return payload.get('device_id') or payload.get('id')

    async def _process_message(self, connection: MQTTConnection, topic: str, payload: dict):
        message_type = self._determine_message_type(topic, payload)
        handler = self.message_handlers.get(message_type)
        if handler:
            await handler(connection, topic, payload)

    def _determine_message_type(self, topic: str, payload: dict) -> str:
        if 'telemetry' in topic.lower(): return 'telemetry'
        if 'status' in topic.lower(): return 'status'
        if 'config' in topic.lower(): return 'configuration'
        if 'flow' in payload or 'level' in payload or 'total' in payload: return 'telemetry'
        return 'telemetry'

    async def _handle_telemetry_message(self, connection: MQTTConnection, topic: str, payload: dict):
        try:
            device_id = self._extract_device_id(topic, payload)
            if not device_id: return

            device = IoTDevice.objects.select_related('catchment_point').filter(device_id=device_id).first()
            if not device: return

            await self._process_device_telemetry(device, payload)
        except Exception as exc:
            logger.error(f"Error handling telemetry message: {exc}")

    async def _process_device_telemetry(self, device: IoTDevice, payload: dict):
        """Procesar telemetría MQTT usando lógica V3 unificada"""
        try:
            with transaction.atomic():
                device.update_status_from_data(payload)
                
                # Preparar registro para V3
                created_register = {
                    "timestamp": timezone.now(),
                    "metadata": {
                        "last_logger_timestamp": payload.get('timestamp'),
                        "source": "MQTT",
                        "raw_payload": payload
                    },
                    "data": {
                        "flow": payload.get('flow'),
                        "nivel": payload.get('level'),
                        "water_table": payload.get('water_table'),
                        "total": payload.get('total'),
                        "pulses": payload.get('pulses')
                    },
                    "is_error": payload.get('error', False)
                }
                
                # Usar guardado unificado V3 (maneja cálculos de diff y totales)
                save_telemetry_data(device.catchment_point.id, created_register)
                logger.info(f"Telemetry V3 processed for device {device.device_id}")

        except Exception as exc:
            logger.error(f"Error processing device telemetry V3: {exc}")

    async def _handle_status_message(self, connection: MQTTConnection, topic: str, payload: dict):
        device_id = self._extract_device_id(topic, payload)
        if device_id:
            device = IoTDevice.objects.filter(device_id=device_id).first()
            if device:
                device.update_status_from_data(payload)

    async def _handle_configuration_message(self, connection: MQTTConnection, topic: str, payload: dict):
        logger.info(f"Configuration message received: {topic}")

    async def _handle_command_response(self, connection: MQTTConnection, topic: str, payload: dict):
        logger.info(f"Command response received: {topic}")

    async def send_command_to_device(self, device: IoTDevice, command: str, params: dict = None):
        try:
            connection = device.equipment_model.provider.mqtt_connections.filter(is_active=True).first()
            if not connection: raise ValueError("No active connection")

            client = self.clients.get(connection.client_id)
            if not client: raise ValueError("Client not connected")

            command_topic = f"{device.mqtt_topic_prefix}/commands"
            command_payload = {
                'command': command,
                'device_id': device.device_id,
                'timestamp': timezone.now().isoformat(),
                'params': params or {}
            }

            client.publish(command_topic, json.dumps(command_payload), qos=1)
            MQTTMessageLog.objects.create(
                connection=connection, device=device, message_type='PUBLISH',
                topic=command_topic, payload=command_payload
            )
            connection.messages_sent_today += 1
            connection.save(update_fields=['messages_sent_today'])
        except Exception as exc:
            logger.error(f"Error sending command: {exc}")
            raise

    def get_connection_status(self) -> Dict[str, Dict]:
        status = {}
        for connection in MQTTConnection.objects.all():
            client = self.clients.get(connection.client_id)
            status[connection.client_id] = {
                'name': connection.connection_name,
                'status': connection.status,
                'is_connected': client is not None and client.is_connected(),
                'messages_today': connection.messages_received_today
            }
        return status

    async def shutdown(self):
        for client in self.clients.values():
            client.loop_stop()
            client.disconnect()
        self.clients.clear()


mqtt_service = MQTTService()
