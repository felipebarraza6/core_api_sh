"""
Servicio de Suscripción MQTT para recibir datos de dispositivos.

Este servicio escucha el broker MQTT local y procesa mensajes
de dispositivos que publican a topics específicos.
"""

import logging
import json
import paho.mqtt.client as mqtt
from typing import Dict, Any, Optional
from django.conf import settings
from django.utils import timezone

from .models import TelemetryProvider, CatchmentPointProvider
from .mqtt_models import MQTTProviderConfig, CatchmentPointMQTT, PayloadParsingRule
from .mqtt_parser import MQTTPayloadParser
from api.telemetry.ingestion.controllers.unified_processing import (
    process_variable_safely,
    save_telemetry_data
)

logger = logging.getLogger(__name__)


class MQTTSubscriberService:
    """
    Servicio que escucha el broker MQTT local y procesa mensajes entrantes.

    A diferencia de DynamicMQTTHandler que se conecta a brokers externos,
    este servicio escucha TU broker local donde los dispositivos publican.
    """

    def __init__(self, broker_host: str = 'localhost', broker_port: int = 1883):
        """
        Inicializar servicio de suscripción.

        Args:
            broker_host: Host del broker local (default: localhost)
            broker_port: Puerto del broker (default: 1883)
        """
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.client = None
        self.is_running = False

        # Cache de configuraciones
        self.point_configs: Dict[str, CatchmentPointMQTT] = {}
        self.parsing_rules: Dict[int, list] = {}

        logger.info(f"Inicializando MQTT Subscriber Service en {broker_host}:{broker_port}")

    def start(self):
        """Iniciar servicio de suscripción."""
        try:
            # Cargar configuraciones desde BD
            self._load_configurations()

            # Crear cliente MQTT
            client_id = f"smarthydro_subscriber_{timezone.now().timestamp()}"
            self.client = mqtt.Client(client_id=client_id, clean_session=False)

            # Configurar callbacks
            self.client.on_connect = self._on_connect
            self.client.on_message = self._on_message
            self.client.on_disconnect = self._on_disconnect
            self.client.on_subscribe = self._on_subscribe

            # Conectar al broker local
            logger.info(f"Conectando a broker MQTT en {self.broker_host}:{self.broker_port}")
            self.client.connect(self.broker_host, self.broker_port, keepalive=60)

            # Iniciar loop (bloqueante o en thread)
            self.is_running = True
            self.client.loop_start()  # Non-blocking

            logger.info("MQTT Subscriber Service iniciado exitosamente")

        except Exception as e:
            logger.error(f"Error iniciando MQTT Subscriber Service: {e}", exc_info=True)
            raise

    def stop(self):
        """Detener servicio de suscripción."""
        if self.client and self.is_running:
            logger.info("Deteniendo MQTT Subscriber Service")
            self.client.loop_stop()
            self.client.disconnect()
            self.is_running = False

    def _load_configurations(self):
        """Cargar configuraciones de puntos y reglas desde BD."""
        try:
            # Cargar configuraciones MQTT de puntos activos
            mqtt_points = CatchmentPointMQTT.objects.filter(
                is_active=True,
                point__is_active=True
            ).select_related(
                'point',
                'provider',
                'provider__mqtt_config'
            ).prefetch_related(
                'provider__parsing_rules'
            )

            for mqtt_point in mqtt_points:
                device_id = mqtt_point.get_effective_device_id()
                self.point_configs[device_id] = mqtt_point

                # Cachear reglas de parsing
                rules = list(mqtt_point.provider.parsing_rules.filter(is_active=True))
                self.parsing_rules[mqtt_point.provider.id] = rules

            logger.info(f"Cargadas {len(self.point_configs)} configuraciones de puntos MQTT")

        except Exception as e:
            logger.error(f"Error cargando configuraciones MQTT: {e}", exc_info=True)

    def _on_connect(self, client, userdata, flags, rc):
        """Callback cuando se conecta al broker."""
        if rc == 0:
            logger.info("Conectado exitosamente al broker MQTT")

            # Suscribirse a todos los topics configurados
            self._subscribe_to_topics()
        else:
            logger.error(f"Error de conexión MQTT, código: {rc}")

    def _on_disconnect(self, client, userdata, rc):
        """Callback cuando se desconecta del broker."""
        if rc != 0:
            logger.warning(f"Desconexión inesperada del broker MQTT, código: {rc}")
        else:
            logger.info("Desconectado del broker MQTT")

    def _on_subscribe(self, client, userdata, mid, granted_qos):
        """Callback cuando se completa una suscripción."""
        logger.debug(f"Suscripción exitosa, QoS: {granted_qos}")

    def _subscribe_to_topics(self):
        """Suscribirse a todos los topics configurados."""
        subscribed_topics = set()

        for device_id, mqtt_point in self.point_configs.items():
            try:
                topic = mqtt_point.get_subscribe_topic()

                if topic not in subscribed_topics:
                    qos = mqtt_point.provider.mqtt_config.default_qos
                    self.client.subscribe(topic, qos=qos)
                    subscribed_topics.add(topic)
                    logger.info(f"Suscrito a topic: {topic} (QoS {qos})")

            except Exception as e:
                logger.error(f"Error suscribiendo a topic para {device_id}: {e}")

        # Suscripción wildcard para capturar todo (opcional, para debug)
        if settings.DEBUG:
            self.client.subscribe("smarthydro/#", qos=0)
            logger.debug("Suscrito a wildcard topic: smarthydro/#")

    def _on_message(self, client, userdata, message):
        """
        Callback cuando llega un mensaje MQTT.

        Args:
            message: Objeto MQTTMessage con topic y payload
        """
        try:
            topic = message.topic
            payload_raw = message.payload

            logger.debug(f"Mensaje recibido en topic: {topic}")

            # Decodificar payload
            try:
                payload = json.loads(payload_raw.decode('utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError):
                # Si no es JSON, intentar como texto
                payload = {"raw": payload_raw.decode('utf-8', errors='ignore')}

            # Procesar mensaje
            self._process_message(topic, payload)

        except Exception as e:
            logger.error(f"Error procesando mensaje MQTT: {e}", exc_info=True)

    def _process_message(self, topic: str, payload: dict):
        """
        Procesar mensaje MQTT y guardar telemetría.

        Args:
            topic: Topic MQTT donde llegó el mensaje
            payload: Payload decodificado del mensaje
        """
        try:
            # Extraer device_id del topic o payload
            device_id = self._extract_device_id(topic, payload)

            if not device_id:
                logger.warning(f"No se pudo extraer device_id de topic: {topic}")
                return

            # Buscar configuración del punto
            mqtt_point = self.point_configs.get(device_id)

            if not mqtt_point:
                logger.warning(f"No hay configuración para device_id: {device_id}")
                return

            # Actualizar last_seen
            mqtt_point.last_seen = timezone.now()
            mqtt_point.save(update_fields=['last_seen'])

            # Obtener reglas de parsing
            provider = mqtt_point.provider
            rules = self.parsing_rules.get(provider.id, [])

            # Encontrar regla que aplique
            applicable_rule = None
            for rule in rules:
                if rule.matches_condition(topic, payload, device_id):
                    applicable_rule = rule
                    break

            if not applicable_rule:
                logger.warning(f"No hay regla de parsing aplicable para {device_id} en topic {topic}")
                return

            # Parsear datos usando la regla
            parser = MQTTPayloadParser(provider.mqtt_config)
            parsed_data = parser.parse(payload, applicable_rule)

            # Validar datos parseados
            validation_errors = applicable_rule.validate_parsed_data(parsed_data)
            if validation_errors:
                logger.error(f"Errores de validación para {device_id}: {validation_errors}")
                return

            # Guardar telemetría
            self._save_telemetry(mqtt_point, parsed_data)

            logger.info(f"Telemetría guardada exitosamente para {device_id}")

        except Exception as e:
            logger.error(f"Error procesando mensaje de {topic}: {e}", exc_info=True)

    def _extract_device_id(self, topic: str, payload: dict) -> Optional[str]:
        """
        Extraer device_id del topic o payload.

        Soporta formatos comunes:
        - smarthydro/{device_id}/data
        - novus/{device_id}/telemetry
        - nxtra/{device_id}/sensor
        - Payload con campo "device_id" o "deviceId"

        Args:
            topic: Topic MQTT
            payload: Payload del mensaje

        Returns:
            device_id o None si no se puede extraer
        """
        # Intentar extraer del topic
        parts = topic.split('/')

        # Formato: provider/{device_id}/...
        if len(parts) >= 2:
            potential_device_id = parts[1]
            if potential_device_id and potential_device_id != '#' and potential_device_id != '+':
                return potential_device_id

        # Intentar extraer del payload
        for key in ['device_id', 'deviceId', 'device', 'id']:
            if key in payload:
                return str(payload[key])

        return None

    def _save_telemetry(self, mqtt_point: CatchmentPointMQTT, parsed_data: dict):
        """
        Guardar datos de telemetría procesados.

        Args:
            mqtt_point: Configuración del punto MQTT
            parsed_data: Datos parseados del mensaje
        """
        point = mqtt_point.point

        # Crear registro base
        created_register = {
            'point_id': point.id,
            'metadata': {
                'source': 'mqtt',
                'provider': mqtt_point.provider.name,
                'device_id': mqtt_point.get_effective_device_id(),
                'received_at': timezone.now().isoformat()
            }
        }

        # Obtener variables del punto
        point_providers = CatchmentPointProvider.objects.filter(
            point=point,
            is_active=True
        ).select_related('variable')

        # Procesar cada variable
        for pp in point_providers:
            variable = pp.variable
            var_code = variable.variable_code

            # Verificar si el dato parseado contiene esta variable
            if var_code in parsed_data:
                raw_value = parsed_data[var_code]

                # Procesar variable usando sistema unificado
                try:
                    variable_dict = {
                        'id': variable.id,
                        'variable_code': var_code,
                        'type_variable': variable.type_variable,
                        'min_val': variable.min_val,
                        'max_val': variable.max_val,
                        'scale_factor': variable.scale_factor,
                        'offset': variable.offset,
                    }

                    point_dict = {
                        'id': point.id,
                        'point_code': point.point_code,
                    }

                    data_dict = {
                        'value': raw_value,
                        'timestamp': parsed_data.get('timestamp', timezone.now().isoformat())
                    }

                    # Procesar con sistema unificado
                    _, created_register = process_variable_safely(
                        variable=variable_dict,
                        data=data_dict,
                        point_catchment=point_dict,
                        created_register=created_register
                    )

                except Exception as e:
                    logger.error(f"Error procesando variable {var_code}: {e}")

        # Guardar registro final
        try:
            save_telemetry_data(point.id, created_register)
            logger.info(f"Telemetría guardada para punto {point.point_code}")
        except Exception as e:
            logger.error(f"Error guardando telemetría: {e}")


# Instancia global del servicio (se inicializa en apps.py)
mqtt_subscriber = None


def start_mqtt_subscriber():
    """Iniciar servicio de suscripción MQTT (llamar desde apps.py)."""
    global mqtt_subscriber

    if mqtt_subscriber is None:
        broker_host = settings.MQTT_BROKER_HOST if hasattr(settings, 'MQTT_BROKER_HOST') else 'localhost'
        broker_port = settings.MQTT_BROKER_PORT if hasattr(settings, 'MQTT_BROKER_PORT') else 1883

        mqtt_subscriber = MQTTSubscriberService(broker_host, broker_port)
        mqtt_subscriber.start()

    return mqtt_subscriber


def stop_mqtt_subscriber():
    """Detener servicio de suscripción MQTT."""
    global mqtt_subscriber

    if mqtt_subscriber:
        mqtt_subscriber.stop()
        mqtt_subscriber = None
