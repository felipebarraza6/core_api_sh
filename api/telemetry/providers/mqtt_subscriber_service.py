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

    def __init__(self, provider: TelemetryProvider = None, broker_host: str = None, broker_port: int = None):
        """
        Inicializar servicio de suscripción.

        Args:
            provider: Instancia de TelemetryProvider (Opcional)
            broker_host: Host del broker (Override)
            broker_port: Puerto del broker (Override)
        """
        self.provider = provider
        
        # Obtener config de MQTT si hay provider
        mqtt_config = getattr(provider, 'mqtt_config', None) if provider else None
        
        # Intentar obtener de SystemConfiguration (Pilar Zero Hardcoding)
        try:
            from api.telemetry.models.management_super import SystemConfiguration
            sys_conf = SystemConfiguration.objects.filter(category='MQTT', key='BROKER_CONFIG').first()
            sys_vals = sys_conf.value if sys_conf else {}
        except Exception:
            sys_vals = {}
        
        self.broker_host = broker_host or sys_vals.get('host') or (mqtt_config.broker_host if mqtt_config else 'mqtt_broker')
        self.broker_port = broker_port or sys_vals.get('port') or (mqtt_config.broker_port if mqtt_config else 1883)
        self.client = None
        self.is_running = False

        # Cache de configuraciones
        self.point_configs: Dict[str, CatchmentPointMQTT] = {}
        self.parsing_rules: Dict[int, list] = {}

        logger.info(f"Inicializando MQTT Subscriber Service para {provider.name if provider else 'Global'} en {self.broker_host}:{self.broker_port}")

    def start(self):
        """Iniciar servicio de suscripción."""
        try:
            # Cargar configuraciones desde BD
            self._load_configurations()

            # Crear cliente MQTT
            client_id = f"smarthydro_{self.provider.name if self.provider else 'sub'}_{timezone.now().timestamp()}"
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
            query = CatchmentPointMQTT.objects.filter(
                is_active=True,
                point__is_active=True
            )
            
            if self.provider:
                query = query.filter(provider=self.provider)

            mqtt_points = query.select_related(
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

            # Procesar mensaje
            self._process_message(topic, message.payload)

        except Exception as e:
            logger.error(f"Error procesando mensaje MQTT: {e}", exc_info=True)

    def _process_message(self, topic: str, payload_bytes: bytes):
        """
        Procesar mensaje MQTT y guardar telemetría.
        """
        try:
            # 1. Encontrar configuración de punto por topic
            # Para esto necesitamos un parser temporal o una forma de mapear topics
            # Por ahora buscaremos en el cache de configuraciones
            
            applicable_mqtt_point = None
            device_id = None
            
            for d_id, mqtt_p in self.point_configs.items():
                parser = MQTTPayloadParser(mqtt_p.provider.mqtt_config)
                extracted_id = parser.extract_device_id_from_topic(topic)
                if extracted_id == d_id:
                    applicable_mqtt_point = mqtt_p
                    device_id = d_id
                    break

            if not applicable_mqtt_point:
                return

            # 2. Parsear usando el motor dinámico
            parser = MQTTPayloadParser(applicable_mqtt_point.provider.mqtt_config)
            parsed_data = parser.parse(topic, payload_bytes, device_id)

            # 3. Guardar telemetría
            self._save_telemetry(applicable_mqtt_point, parsed_data)

        except Exception as e:
            logger.error(f"Error procesando mensaje de {topic}: {e}", exc_info=True)

    def _extract_device_id(self, topic: str, payload: dict) -> Optional[str]:
        """DEPRECATED: Usar MQTTPayloadParser.extract_device_id_from_topic"""
        return None
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
        point = mqtt_point.point
        """
        Guardar datos de telemetría procesados.

        Args:
            mqtt_point: Configuración del punto MQTT
            parsed_data: Datos parseados del mensaje
        """

        # Crear registro base
        created_register = {
            'point_id': point.id,
            'date_time_medition': parsed_data.get('timestamp') or timezone.now().isoformat(),
            'metadata': {
                **parsed_data.get('metadata', {}),
                'source': 'mqtt',
                'provider': mqtt_point.provider.name,
                'device_id': mqtt_point.get_effective_device_id(),
                'received_at': timezone.now().isoformat()
            }
        }

        # Obtener configuraciones de proveedor para este punto y proveedor MQTT
        # Cada CatchmentPointProvider        # Obtener variables configuradas para este punto
        point_providers = CatchmentPointProvider.objects.filter(
            point=point,
            is_active=True
        ).select_related('variable', 'variable__type_definition')


        point_dict = {
            'id': point.id,
            'point_code': point.point_code,
        }

        for pp in point_providers:
            variable = pp.variable
            provider_key = pp.provider_variable_key or variable.internal_code
            

            # Buscar en metadata (donde el parser pone los campos extra)
            metadata = parsed_data.get('metadata', {})
            if provider_key in metadata:
                raw_value = metadata[provider_key]
                
                try:
                    variable_dict = {
                        'id': variable.id,
                        'internal_code': variable.internal_code,
                        'type_variable': variable.type_definition.code if variable.type_definition else 'unknown',
                        'min_value': variable.min_value,
                        'max_value': variable.max_value,
                        'scale_factor': variable.scale_factor,
                        'offset': variable.offset,
                    }

                    data_dict = {
                        'value': raw_value,
                        'date_time': created_register.get('date_time_medition')
                    }

                    # Procesar con sistema unificado
                    _, created_register = process_variable_safely(
                        variable=variable_dict,
                        data=data_dict,
                        point_catchment=point_dict,
                        created_register=created_register
                    )

                except Exception as e:
                    logger.error(f"Error procesando variable {variable.internal_code}: {e}")
            else:

        # Guardar registro final
        try:
            save_telemetry_data(point.id, created_register)
            logger.info(f"Telemetría guardada para punto {point.point_code}")

            # Actualizar last_seen del punto MQTT
            mqtt_point.last_seen = timezone.now()
            mqtt_point.save(update_fields=['last_seen'])

            # Actualizar last_seen del Device si está vinculado
            if point.device:
                point.device.last_seen = timezone.now()
                point.device.status = 'ONLINE'
                point.device.save(update_fields=['last_seen', 'status'])

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

        mqtt_subscriber = MQTTSubscriberService(broker_host=broker_host, broker_port=broker_port)
        mqtt_subscriber.start()

    return mqtt_subscriber


def stop_mqtt_subscriber():
    """Detener servicio de suscripción MQTT."""
    global mqtt_subscriber

    if mqtt_subscriber:
        mqtt_subscriber.stop()
        mqtt_subscriber = None
