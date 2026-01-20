"""Servicio MQTT para conexión directa de equipos IoT (V3) - Sistema Dinámico."""

import asyncio
import json
import logging
import ssl
import paho.mqtt.client as mqtt
from typing import Dict, Optional, Callable

from django.utils import timezone
from django.db import transaction

from api.infrastructure.models import Device, Connection, MessageLog
from api.telemetry.models.catchment_points import CatchmentPoint
from api.telemetry.models.telemetry import TelemetryRecord
from api.telemetry.ingestion.controllers.unified_processing import save_telemetry_data
from api.telemetry.providers import get_provider_manager

logger = logging.getLogger(__name__)


class MQTTService:
    """
    Servicio MQTT para gestión de conexiones y mensajes con equipos IoT (V3) - Sistema Dinámico.

    Este servicio ahora delega el procesamiento de mensajes MQTT a los handlers
    dinámicos configurados en la base de datos a través del ProviderManager.
    """

    def __init__(self):
        self.clients: Dict[str, mqtt.Client] = {}
        self.provider_manager = get_provider_manager()
        self.message_handlers: Dict[str, Callable] = {}
        self._setup_message_handlers()

    def _setup_message_handlers(self):
        """Configurar handlers para diferentes tipos de mensajes."""
        self.message_handlers = {
            'telemetry': self._handle_telemetry_message_dynamic,
            'status': self._handle_status_message,
            'configuration': self._handle_configuration_message,
            'command_response': self._handle_command_response,
        }

    async def initialize_connections(self):
        """Inicializar todas las conexiones MQTT activas."""
        active_connections = Connection.objects.filter(is_active=True)
        for connection in active_connections:
            try:
                await self.start_connection(connection)
            except Exception as exc:
                logger.error(f"Failed to initialize MQTT connection {connection.connection_name}: {exc}")

    async def start_connection(self, connection: Connection):
        """Iniciar una conexión MQTT específica."""
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

    def _on_connect(self, client, connection: Connection, rc):
        if rc == 0:
            connection.status = 'CONNECTED'
            connection.last_connected = timezone.now()
            connection.connection_errors = 0
        else:
            connection.status = 'ERROR'
            connection.connection_errors += 1
        connection.save()

    def _on_disconnect(self, client, connection: Connection, rc):
        connection.status = 'DISCONNECTED'
        connection.last_disconnected = timezone.now()
        if rc != 0:
            connection.status = 'CONNECTING'
        connection.save()

    def _on_message(self, client, connection: Connection, msg):
        try:
            # Log the message first
            self._log_mqtt_message(connection, msg)

            # Decode payload
            try:
                payload = json.loads(msg.payload.decode('utf-8'))
            except json.JSONDecodeError:
                payload = {'raw_data': msg.payload.decode('utf-8')}

            # Process message using dynamic system
            asyncio.create_task(self._process_message_dynamic(connection, msg.topic, payload, msg))
        except Exception as exc:
            logger.error(f"Error processing MQTT message: {exc}")

    def _log_mqtt_message(self, connection: Connection, msg):
        try:
            # Extract device_id for logging
            device_id = self._extract_device_id_from_topic(msg.topic)
            device = Device.objects.filter(device_id=device_id).first() if device_id else None

            MessageLog.objects.create(
                connection=connection,
                device=device,
                message_type='PUBLISH',
                topic=msg.topic,
                payload={'raw_payload': True},  # Don't store full payload for performance
                qos=msg.qos,
                retained=msg.retain
            )

            connection.messages_received_today += 1
            connection.bytes_received_today += len(msg.payload)
            connection.save(update_fields=['messages_received_today', 'bytes_received_today'])
        except Exception as exc:
            logger.error(f"Error logging MQTT message: {exc}")

    def _extract_device_id_from_topic(self, topic: str) -> Optional[str]:
        """Extract device_id from topic using dynamic provider configuration."""
        topic_parts = topic.split('/')
        if len(topic_parts) >= 2:
            # Try to match against configured providers
            for provider_name, provider in self.provider_manager._providers.items():
                if provider.provider_type == 'mqtt' and hasattr(provider, 'mqtt_config'):
                    try:
                        # Use the MQTT config to extract device_id
                        template = provider.mqtt_config.subscribe_topic_template
                        # Simple extraction: assume {provider}/{device_id}/... format
                        if template.startswith(f"{provider_name}/{{device_id}}"):
                            parts = topic.split('/')
                            if len(parts) > 1:
                                return parts[1]
                    except Exception:
                        continue

            # Fallback to simple extraction
            return topic_parts[1]
        return None

    async def _process_message_dynamic(self, connection: Connection, topic: str, payload: dict, msg):
        """Process message using dynamic provider system."""
        try:
            # Find the appropriate MQTT provider handler for this topic
            handler = self._find_handler_for_topic(topic)
            if not handler:
                logger.debug(f"No handler found for topic: {topic}")
                return

            # Extract device_id
            device_id = self._extract_device_id_from_topic(topic)

            # Use the handler's parser to process the message
            parsed_data = handler.parser.parse(topic, msg.payload, device_id or '')

            # Save telemetry data
            await self._save_telemetry_from_parsed_data(device_id, parsed_data)

        except Exception as exc:
            logger.error(f"Error in dynamic message processing: {exc}")

    def _find_handler_for_topic(self, topic: str):
        """Find the appropriate MQTT handler for a topic."""
        for provider_name, provider in self.provider_manager._providers.items():
            if provider.provider_type == 'mqtt':
                handler = self.provider_manager.get_handler(provider_name)
                if handler and hasattr(handler, 'parser'):
                    # Check if this handler can handle this topic pattern
                    try:
                        mqtt_config = provider.mqtt_config
                        # Simple check: if topic matches the subscribe template pattern
                        if self._topic_matches_provider(topic, provider):
                            return handler
                    except Exception:
                        continue
        return None

    def _topic_matches_provider(self, topic: str, provider) -> bool:
        """Check if topic matches provider's subscription pattern."""
        try:
            template = provider.mqtt_config.subscribe_topic_template
            # Simple pattern matching - could be enhanced with regex
            provider_prefix = f"{provider.name}/"
            return topic.startswith(provider_prefix)
        except Exception:
            return False

    async def _save_telemetry_from_parsed_data(self, device_id: str, parsed_data: Dict):
        """Save telemetry data from parsed MQTT message."""
        try:
            # Find catchment point by device_id
            point = await self._find_catchment_point_async(device_id)
            if not point:
                logger.warning(f"No catchment point found for device {device_id}")
                return

            # Prepare register data
            created_register = {
                "date_time_medition": parsed_data.get('timestamp') or timezone.now(),
                "date_time_last_logger": parsed_data.get('timestamp') or timezone.now(),
                "device_id": device_id,
                "is_error": False,
                "is_partial": False,
            }

            # Map parsed data to register fields
            data_mapping = {
                'flow': 'flow',
                'nivel': 'nivel',
                'water_table': 'water_table',
                'total': 'total',
                'pulses': 'pulses',
                'temperature': 'temperature',
                'pressure': 'pressure',
                'conductivity': 'conductivity',
            }

            for parsed_field, register_field in data_mapping.items():
                if parsed_field in parsed_data:
                    created_register[register_field] = parsed_data[parsed_field]

            # Add metadata
            created_register["variable_details"] = [{
                "internal_code": "mqtt_dynamic",
                "str_variable": "mqtt_data",
                "type_variable": parsed_data.get('variable_type', 'UNKNOWN'),
                "service": "MQTT_DYNAMIC",
                "provider": "mqtt",
                "success": True,
                "value": parsed_data.get('value'),
                "timestamp": parsed_data.get('timestamp'),
            }]

            # Save using unified processing
            record = await asyncio.get_event_loop().run_in_executor(
                None, save_telemetry_data, point.id, created_register
            )

            if record:
                logger.info(f"Dynamic MQTT telemetry saved for device {device_id} (record {record.id})")

        except Exception as exc:
            logger.error(f"Error saving telemetry from parsed data: {exc}")

    async def _find_catchment_point_async(self, device_id: str):
        """Find catchment point by device_id asynchronously."""
        from api.telemetry.models.catchment_points import CatchmentPoint

        try:
            # First try by point_code
            point = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: CatchmentPoint.objects.filter(point_code=device_id).first()
            )
            if point:
                return point

            # Try to find through MQTT configuration
            from api.telemetry.providers.mqtt_models import CatchmentPointMQTT
            mqtt_config = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: CatchmentPointMQTT.objects.filter(
                    custom_device_id=device_id
                ).select_related('point').first()
            )

            return mqtt_config.point if mqtt_config else None

        except Exception as exc:
            logger.error(f"Error finding catchment point for device {device_id}: {exc}")
            return None

    async def _handle_telemetry_message_dynamic(self, connection: Connection, topic: str, payload: dict):
        """
        Legacy method - now delegates to dynamic processing.
        Kept for backward compatibility.
        """
        logger.debug("Using legacy telemetry handler - consider migrating to dynamic system")
        # This method is now handled by _process_message_dynamic
        pass

    async def _handle_status_message(self, connection: Connection, topic: str, payload: dict):
        device_id = self._extract_device_id(topic, payload)
        if device_id:
            device = Device.objects.filter(device_id=device_id).first()
            if device:
                device.update_status_from_data(payload)

    async def _handle_configuration_message(self, connection: Connection, topic: str, payload: dict):
        logger.info(f"Configuration message received: {topic}")

    async def _handle_command_response(self, connection: Connection, topic: str, payload: dict):
        logger.info(f"Command response received: {topic}")

    async def send_command_to_device(self, device: Device, command: str, params: dict = None):
        try:
            connection = device.device_model.manufacturer.mqtt_connections.filter(is_active=True).first()
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
            MessageLog.objects.create(
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
        for connection in Connection.objects.all():
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
