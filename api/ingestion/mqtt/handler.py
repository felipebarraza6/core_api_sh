"""
Dynamic MQTT Handler

Handler MQTT completamente dinámico que integra el parser de payloads
con conexiones MQTT reales usando configuración desde la base de datos.
"""

import asyncio
import logging
import uuid
from typing import Dict, Any, Optional, List, Callable
import paho.mqtt.client as mqtt

from django.utils import timezone
from django.db import transaction

from api.telemetry.providers.models import TelemetryProvider, CatchmentPointProvider
from api.telemetry.providers.mqtt_models import MQTTProviderConfig
from .parser import MQTTPayloadParser
from api.ingestion.services.provider_handlers import BaseProviderHandler
from api.telemetry.ingestion.controllers.unified_processing import save_telemetry_data

logger = logging.getLogger(__name__)


class DynamicMQTTHandler(BaseProviderHandler):
    """
    Handler MQTT completamente dinámico.

    Gestiona conexiones MQTT y parsing de payloads usando configuración
    almacenada en la base de datos.
    """

    provider_name = "mqtt_dynamic"
    supported_protocols = ['mqtt', 'mqtts']
    supported_variables = ['CAUDAL', 'NIVEL', 'TOTALIZADO', 'TEMPERATURA', 'PRESION', 'CONDUCTIVIDAD']

    def __init__(self, provider: TelemetryProvider):
        """
        Inicializar handler con configuración del proveedor.

        Args:
            provider: Instancia de TelemetryProvider con configuración MQTT
        """
        super().__init__()
        self.provider = provider
        self.mqtt_config = provider.mqtt_config  # MQTTProviderConfig
        self.parser = MQTTPayloadParser(self.mqtt_config)

        # Estado de conexión
        self.client = None
        self.is_connected = False
        self.message_queue = asyncio.Queue()
        self.active_subscriptions: Dict[str, List[Callable]] = {}

        # Configuración de reconexión
        self.reconnect_delay = self.mqtt_config.reconnect_delay
        self.max_reconnect_attempts = 10

    async def connect(self) -> bool:
        """
        Establecer conexión MQTT.

        Returns:
            bool: True si la conexión fue exitosa
        """
        try:
            if self.client and self.is_connected:
                logger.debug(f"MQTT client for {self.provider.name} already connected")
                return True

            # Generar client_id único
            client_id = self.mqtt_config.generate_client_id()

            # Crear cliente MQTT
            self.client = mqtt.Client(
                client_id=client_id,
                clean_session=False,
                protocol=mqtt.MQTTv311
            )

            # Configurar autenticación si existe
            if self.mqtt_config.username:
                self.client.username_pw_set(
                    self.mqtt_config.username,
                    self.mqtt_config.password or ""
                )

            # Configurar TLS si es necesario
            if self.mqtt_config.use_tls:
                self.client.tls_set()
                port = 8883
            else:
                port = self.mqtt_config.broker_port

            # Configurar callbacks
            self.client.on_connect = self._on_connect
            self.client.on_disconnect = self._on_disconnect
            self.client.on_message = self._on_message
            self.client.on_subscribe = self._on_subscribe
            self.client.on_unsubscribe = self._on_unsubscribe

            # Configurar parámetros de conexión
            self.client.reconnect_delay_set(
                min_delay=self.reconnect_delay,
                max_delay=self.reconnect_delay * 5
            )
            self.client.max_inflight_messages_set(20)
            self.client.max_queued_messages_set(100)

            # Conectar
            logger.info(f"Connecting MQTT client {client_id} [Service: {self.mqtt_config.service_identifier}] to {self.mqtt_config.broker_host}:{port}")
            self.client.connect(
                self.mqtt_config.broker_host,
                port,
                keepalive=self.mqtt_config.keep_alive
            )

            # Iniciar loop en thread separado
            self.client.loop_start()

            # Esperar conexión
            await self._wait_for_connection(timeout=10)

            if self.is_connected:
                logger.info(f"MQTT client {client_id} connected successfully")
                return True
            else:
                logger.error(f"Failed to connect MQTT client {client_id}")
                return False

        except Exception as exc:
            logger.error(f"Error connecting MQTT client: {exc}")
            return False

    async def _wait_for_connection(self, timeout: int = 10):
        """Esperar a que se establezca la conexión."""
        import time
        start_time = time.time()

        while time.time() - start_time < timeout:
            if self.is_connected:
                return
            await asyncio.sleep(0.1)

    def disconnect(self):
        """Desconectar cliente MQTT."""
        try:
            if self.client:
                logger.info(f"Disconnecting MQTT client for {self.provider.name}")
                self.client.loop_stop()
                self.client.disconnect()
                self.is_connected = False
        except Exception as exc:
            logger.error(f"Error disconnecting MQTT client: {exc}")

    async def subscribe_to_topics(self, topics: List[str], qos: int = None):
        """
        Suscribirse a topics MQTT.

        Args:
            topics: Lista de topics a suscribir
            qos: QoS para las suscripciones (usa configuración por defecto si None)
        """
        if not self.client or not self.is_connected:
            logger.warning("Cannot subscribe: MQTT client not connected")
            return

        if qos is None:
            qos = self.mqtt_config.default_qos

        try:
            for topic in topics:
                logger.debug(f"Subscribing to topic: {topic} (QoS: {qos})")
                self.client.subscribe(topic, qos)
                await asyncio.sleep(0.1)  # Pequeña pausa entre suscripciones

        except Exception as exc:
            logger.error(f"Error subscribing to topics: {exc}")

    async def unsubscribe_from_topics(self, topics: List[str]):
        """
        Cancelar suscripción a topics MQTT.

        Args:
            topics: Lista de topics a cancelar
        """
        if not self.client or not self.is_connected:
            logger.warning("Cannot unsubscribe: MQTT client not connected")
            return

        try:
            for topic in topics:
                logger.debug(f"Unsubscribing from topic: {topic}")
                self.client.unsubscribe(topic)
                await asyncio.sleep(0.1)

        except Exception as exc:
            logger.error(f"Error unsubscribing from topics: {exc}")

    async def publish_message(self, topic: str, payload: Any, qos: int = None, retain: bool = None):
        """
        Publicar mensaje en topic MQTT.

        Args:
            topic: Topic donde publicar
            payload: Payload a publicar (dict, str, bytes)
            qos: QoS del mensaje
            retain: Si el mensaje debe ser retenido
        """
        if not self.client or not self.is_connected:
            logger.warning("Cannot publish: MQTT client not connected")
            return

        if qos is None:
            qos = self.mqtt_config.default_qos

        if retain is None:
            retain = self.mqtt_config.retain_messages

        try:
            # Convertir payload a JSON si es dict
            if isinstance(payload, dict):
                import json
                payload = json.dumps(payload)
            elif not isinstance(payload, (str, bytes)):
                payload = str(payload)

            # Convertir a bytes si es string
            if isinstance(payload, str):
                payload = payload.encode('utf-8')

            logger.debug(f"Publishing to {topic}: {payload[:100]}...")
            self.client.publish(topic, payload, qos=qos, retain=retain)

        except Exception as exc:
            logger.error(f"Error publishing message: {exc}")

    # Callbacks MQTT (se ejecutan en thread separado)
    def _on_connect(self, client, userdata, flags, rc):
        """Callback cuando se conecta al broker."""
        if rc == 0:
            self.is_connected = True
            logger.info(f"MQTT client connected to {self.mqtt_config.broker_host}")
            # Programar tarea asíncrona para manejar la conexión
            asyncio.create_task(self._handle_connection_established())
        else:
            self.is_connected = False
            rc_messages = {
                1: "Connection refused - incorrect protocol version",
                2: "Connection refused - invalid client identifier",
                3: "Connection refused - server unavailable",
                4: "Connection refused - bad username or password",
                5: "Connection refused - not authorised",
            }
            logger.error(f"MQTT connection failed: {rc_messages.get(rc, f'Unknown error {rc}')}")

    def _on_disconnect(self, client, userdata, rc):
        """Callback cuando se desconecta del broker."""
        self.is_connected = False
        if rc != 0:
            logger.warning(f"MQTT client disconnected unexpectedly (rc={rc})")
            # Intentar reconectar
            asyncio.create_task(self._handle_disconnection())
        else:
            logger.info("MQTT client disconnected cleanly")

    def _on_message(self, client, userdata, msg):
        """Callback cuando llega un mensaje."""
        try:
            # Extraer device_id del topic
            device_id = self._extract_device_id_from_topic(msg.topic)

            # Parsear payload usando el motor dinámico
            parsed_data = self.parser.parse(msg.topic, msg.payload, device_id)

            # Agregar información del mensaje MQTT
            parsed_data['metadata'].update({
                'qos': msg.qos,
                'retain': msg.retain,
                'mqtt_timestamp': timezone.now(),
            })

            # Poner en cola para procesamiento asíncrono
            asyncio.create_task(self._process_parsed_message(device_id, parsed_data))

        except Exception as exc:
            logger.error(f"Error processing MQTT message from topic {msg.topic}: {exc}")

    def _on_subscribe(self, client, userdata, mid, granted_qos):
        """Callback cuando se completa una suscripción."""
        logger.debug(f"MQTT subscription confirmed (mid={mid}, qos={granted_qos})")

    def _on_unsubscribe(self, client, userdata, mid):
        """Callback cuando se cancela una suscripción."""
        logger.debug(f"MQTT unsubscription confirmed (mid={mid})")

    def _extract_device_id_from_topic(self, topic: str) -> Optional[str]:
        """Extraer device_id del topic usando el motor dinámico."""
        return self.parser.extract_device_id_from_topic(topic)

    async def _handle_connection_established(self):
        """Manejar establecimiento de conexión."""
        try:
            # Suscribirse a topics configurados
            topics = self._get_provider_topics()
            if topics:
                await self.subscribe_to_topics(topics)

        except Exception as exc:
            logger.error(f"Error handling connection established: {exc}")

    async def _handle_disconnection(self):
        """Manejar desconexión y intentar reconectar."""
        try:
            # Intentar reconectar después del delay
            await asyncio.sleep(self.reconnect_delay)
            logger.info("Attempting MQTT reconnection...")
            await self.connect()

        except Exception as exc:
            logger.error(f"Error handling disconnection: {exc}")

    def _get_provider_topics(self) -> List[str]:
        """Obtener topics para suscribirse basados en configuración del proveedor."""
        topics = []

        try:
            # Obtener todas las configuraciones de punto para este proveedor
            point_configs = CatchmentPointProvider.objects.filter(
                provider=self.provider,
                is_active=True
            ).select_related('point')

            for config in point_configs:
                try:
                    # Generar topic específico del punto
                    topic = self.mqtt_config.build_subscribe_topic(
                        provider=self.provider.name,
                        device_id=config.point_code or config.point.point_code,
                        point_code=config.point.point_code
                    )
                    topics.append(topic)

                except Exception as exc:
                    logger.warning(f"Could not generate topic for point {config.point}: {exc}")

        except Exception as exc:
            logger.error(f"Error getting provider topics: {exc}")

        return topics

    async def _process_parsed_message(self, device_id: str, parsed_data: Dict[str, Any]):
        """
        Procesar mensaje parseado y guardarlo en el sistema de telemetría.

        Args:
            device_id: ID del dispositivo
            parsed_data: Datos parseados por el motor dinámico
        """
        try:
            # Encontrar el punto de captación correspondiente
            point = await self._find_catchment_point(device_id)
            if not point:
                logger.warning(f"No catchment point found for device {device_id}")
                return

            # Preparar registro para el sistema unificado
            created_register = {
                "date_time_medition": parsed_data.get('timestamp') or timezone.now(),
                "date_time_last_logger": parsed_data.get('timestamp') or timezone.now(),
                "device_id": device_id,
                "is_error": False,
                "is_partial": False,
            }

            # Mapear datos parseados a campos del registro
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

            # Agregar metadata del parsing MQTT
            created_register["variable_details"] = [{
                "internal_code": "mqtt_parsed",
                "str_variable": "mqtt_data",
                "type_variable": parsed_data.get('variable_type', 'UNKNOWN'),
                "service": "MQTT",
                "provider": self.provider.name,
                "success": True,
                "value": parsed_data.get('value'),
                "timestamp": parsed_data.get('timestamp'),
            }]

            # Agregar información de días sin conexión si aplica
            if parsed_data.get('timestamp'):
                # Lógica simplificada - en producción usar lógica completa
                created_register["days_not_conection"] = 0

            # Guardar usando el sistema unificado
            record = await asyncio.get_event_loop().run_in_executor(
                None, save_telemetry_data, point.id, created_register
            )

            if record:
                logger.info(f"MQTT telemetry saved for device {device_id} (record {record.id})")
            else:
                logger.error(f"Failed to save MQTT telemetry for device {device_id}")

        except Exception as exc:
            logger.error(f"Error processing parsed MQTT message for device {device_id}: {exc}")

    async def _find_catchment_point(self, device_id: str):
        """Encontrar punto de captación por device_id."""
        from api.telemetry.models import CatchmentPoint

        try:
            # Buscar por point_code primero
            point = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: CatchmentPoint.objects.filter(point_code=device_id).first()
            )
            if point:
                return point

            # Buscar en configuraciones MQTT específicas
            from .mqtt_models import CatchmentPointMQTT
            mqtt_config = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: CatchmentPointMQTT.objects.filter(
                    custom_device_id=device_id,
                    provider=self.provider
                ).select_related('point').first()
            )

            return mqtt_config.point if mqtt_config else None

        except Exception as exc:
            logger.error(f"Error finding catchment point for device {device_id}: {exc}")
            return None

    # Implementación de BaseProviderHandler
    def fetch_data(self, provider_config: CatchmentPointProvider,
                  variable_type: str = None, **kwargs) -> Dict[str, Any]:
        """
        Implementación de BaseProviderHandler.

        Para MQTT, la obtención de datos es asíncrona y basada en eventos,
        por lo que este método retorna información de estado.
        """
        return {
            'timestamp': timezone.now(),
            'value': None,
            'unit': 'status',
            'variable_type': 'mqtt_status',
            'metadata': {
                'connected': self.is_connected,
                'provider': self.provider.name,
                'broker': f"{self.mqtt_config.broker_host}:{self.mqtt_config.broker_port}",
                'message': 'MQTT data is received asynchronously via subscriptions'
            }
        }

    def test_connection(self) -> Dict[str, Any]:
        """Probar conexión MQTT."""
        try:
            # Intentar conectar por un breve período
            success = asyncio.run(self.connect())

            if success:
                # Desconectar inmediatamente después del test
                self.disconnect()
                return {
                    'success': True,
                    'message': 'MQTT connection successful',
                    'broker': f"{self.mqtt_config.broker_host}:{self.mqtt_config.broker_port}"
                }
            else:
                return {
                    'success': False,
                    'message': 'MQTT connection failed',
                    'broker': f"{self.mqtt_config.broker_host}:{self.mqtt_config.broker_port}"
                }

        except Exception as exc:
            return {
                'success': False,
                'message': f'MQTT connection error: {str(exc)}',
                'broker': f"{self.mqtt_config.broker_host}:{self.mqtt_config.broker_port}"
            }