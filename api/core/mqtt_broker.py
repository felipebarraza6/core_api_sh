"""
Broker MQTT Integrado para SmartHydro
Permite endpoints específicos por proveedor sin intermediarios
"""

import asyncio
import json
import logging
import ssl
from typing import Dict, List, Optional, Callable
import hbmqtt.broker as broker
import hbmqtt.client as mqtt_client

from django.conf import settings
from django.utils import timezone
from django.apps import apps

from api.telemetry.providers.models import TelemetryProvider, CatchmentPointProvider
from api.telemetry.providers.mqtt_models import CatchmentPointMQTT
from api.telemetry.providers.mqtt_parser import MQTTPayloadParser
from api.telemetry.ingestion.controllers.unified_processing import save_telemetry_data, process_variable_safely

logger = logging.getLogger(__name__)


class SmartHydroMQTTBroker:
    """
    Broker MQTT integrado que permite endpoints específicos por proveedor.
    Puede actuar como servidor para un proveedor específico o como broker global.
    """

    def __init__(self, provider: TelemetryProvider = None):
        self.broker = None
        self.provider = provider
        self.provider_endpoints: Dict[str, dict] = {}
        self.client_connections: Dict[str, dict] = {}
        
        # Parser dinámico si hay provider
        self.parser = None
        if provider and hasattr(provider, 'mqtt_config'):
            self.parser = MQTTPayloadParser(provider.mqtt_config)
            logger.info(f"Broker asociado al proveedor: {provider.name}")


    async def start_broker(self, host: str = '0.0.0.0', port: int = 1883):
        """Iniciar el broker MQTT integrado"""
        try:
            # Configuración del broker
            broker_config = {
                'listeners': {
                    'default': {
                        'type': 'tcp',
                        'bind': f'{host}:{port}',
                        'max_connections': 1000,
                    }
                },
                'timeout-disconnect-delay': 2,
                'auth': {
                    'allow-anonymous': True,  # Configurar autenticación por proveedor
                    'password-file': None,
                },
                'topic-check': {
                    'enabled': True,
                    'acl': self._get_topic_acl(),
                }
            }

            # Iniciar broker
            self.broker = broker.Broker(broker_config)
            await self.broker.start()

            logger.info(f"SmartHydro MQTT Broker started on {host}:{port}")

            # Iniciar procesamiento de mensajes
            asyncio.create_task(self._process_messages())

        except Exception as exc:
            logger.error(f"Failed to start MQTT broker: {exc}")
            raise

    def _get_topic_acl(self) -> dict:
        """Generar ACL de topics basado en proveedores"""
        # ACL básico - se puede hacer más granular
        return {
            'anonymous': ['readwrite #'],  # Permitir todo por ahora
        }

    async def _process_messages(self):
        """Procesar mensajes MQTT entrantes"""
        while True:
            try:
                # El broker maneja los mensajes automáticamente
                # Aquí podemos agregar lógica adicional de procesamiento
                await asyncio.sleep(1)

            except Exception as exc:
                logger.error(f"Error in message processing loop: {exc}")
                await asyncio.sleep(5)

    async def register_provider_endpoint(
        self,
        provider_code: str,
        config: dict
    ):
        """
        Registrar endpoint específico para un proveedor

        Args:
            provider_code: Código único del proveedor
            config: Configuración del endpoint
        """
        try:
            self.provider_endpoints[provider_code] = {
                'config': config,
                'topics': config.get('topics', []),
                'auth': config.get('auth', {}),
                'processors': config.get('processors', []),
                'created_at': timezone.now(),
            }

            logger.info(f"Provider endpoint registered: {provider_code}")

        except Exception as exc:
            logger.error(f"Failed to register provider endpoint {provider_code}: {exc}")

    async def unregister_provider_endpoint(self, provider_code: str):
        """Remover endpoint de proveedor"""
        if provider_code in self.provider_endpoints:
            del self.provider_endpoints[provider_code]
            logger.info(f"Provider endpoint unregistered: {provider_code}")

    def get_provider_topics(self, provider_code: str) -> List[str]:
        """Obtener topics disponibles para un proveedor"""
        if provider_code in self.provider_endpoints:
            return self.provider_endpoints[provider_code]['topics']
        return []

    async def process_provider_message(
        self,
        provider_code: str,
        topic: str,
        payload: dict,
        client_id: str = None
    ):
        """Procesar mensaje específico de proveedor"""
        try:
            if provider_code not in self.provider_endpoints:
                logger.warning(f"Unknown provider: {provider_code}")
                return

            endpoint_config = self.provider_endpoints[provider_code]

            # Encontrar procesador apropiado
            processor = None
            for proc_config in endpoint_config.get('processors', []):
                if proc_config.get('topic_pattern') in topic:
                    processor = proc_config
                    break

            if processor:
                # Ejecutar procesador específico
                await self._execute_processor(processor, topic, payload, client_id)
            else:
                # Procesador por defecto
                await self._default_message_processor(provider_code, topic, payload, client_id)

        except Exception as exc:
            logger.error(f"Error processing provider message: {exc}")

    async def _execute_processor(self, processor: dict, topic: str, payload: dict, client_id: str):
        """Ejecutar procesador específico de proveedor"""
        try:
            processor_type = processor.get('type', 'telemetry')

            if processor_type == 'telemetry':
                await self._process_telemetry_data(processor, topic, payload, client_id)
            elif processor_type == 'command':
                await self._process_command_data(processor, topic, payload, client_id)
            elif processor_type == 'status':
                await self._process_status_data(processor, topic, payload, client_id)
            elif processor_type == 'custom':
                # Procesador personalizado
                await self._process_custom_data(processor, topic, payload, client_id)

        except Exception as exc:
            logger.error(f"Error executing processor {processor.get('type')}: {exc}")

    async def _process_telemetry_data(self, processor: dict, topic: str, payload: dict, client_id: str):
        """Procesar datos de telemetría específicos del proveedor"""
        try:
            # 1. Identificar Proveedor y Punto
            # Si el broker es específico de un provider, lo usamos. 
            # Si no, intentamos inferir del topic (Legacy)
            provider = self.provider
            
            # Decodificar payload si viene como dict
            payload_bytes = json.dumps(payload).encode('utf-8') if isinstance(payload, dict) else payload
            
            # 2. Extraer device_id y Parsear
            if self.parser:
                device_id = self.parser.extract_device_id_from_topic(topic)
                parsed_data = self.parser.parse(topic, payload_bytes, device_id)
            else:
                # Fallback legacy si no hay parser asociado
                device_id = self._extract_device_id('topic', topic, payload)
                parsed_data = payload # Asumir que ya viene listo o procesar genérico
            
            if not device_id:
                logger.warning(f"No device_id found for topic: {topic}")
                return

            # 3. Guardar Telemetría usando Unified Processing
            # Buscamos el CatchmentPointMQTT para este device_id
            try:
                mqtt_point = CatchmentPointMQTT.objects.select_related('point', 'provider').get(
                    provider=provider,
                    point__point_code=device_id, # O custom_device_id si implementamos el lookup completo
                    is_active=True
                )
                
                # Usar lógica de guardado similar a MQTTSubscriberService
                self._save_to_db(mqtt_point, parsed_data)
                
                logger.info(f"Telemetry processed and saved for device {device_id} via internal broker")

            except CatchmentPointMQTT.DoesNotExist:
                logger.warning(f"MQTT Point configuration not found for device: {device_id}")

        except Exception as exc:
            logger.error(f"Error processing telemetry data in broker: {exc}", exc_info=True)

    def _save_to_db(self, mqtt_point, parsed_data):
        """Helper sincrónico para guardar en DB (o envolver en sync_to_async)"""
        from asgiref.sync import sync_to_async
        
        # Reutilizamos la lógica de MQTTSubscriberService._save_telemetry pero adaptada
        # Para simplificar aquí, llamaremos a una función que haga el trabajo sucio
        # (Idealmente refactorizar esto a una utilidad común)
        
        point = mqtt_point.point
        created_register = {
            'point_id': point.id,
            'metadata': {
                'source': 'internal_mqtt_broker',
                'provider': mqtt_point.provider.name,
                'device_id': mqtt_point.get_effective_device_id(),
                'received_at': timezone.now().isoformat()
            }
        }
        
        # Iterar variables y procesar
        # ... (Similar a mqtt_subscriber_service.py) ...
        # Por brevedad en el refactor, usaremos save_telemetry_data directamente si parsed_data ya está formateado
        save_telemetry_data(point.id, {**created_register, **parsed_data})


    async def _process_command_data(self, processor: dict, topic: str, payload: dict, client_id: str):
        """Procesar comandos específicos del proveedor"""
        # Implementar lógica de comandos
        logger.info(f"Command processed: {topic}")

    async def _process_status_data(self, processor: dict, topic: str, payload: dict, client_id: str):
        """Procesar datos de estado específicos del proveedor"""
        # Implementar lógica de estado
        logger.info(f"Status processed: {topic}")

    async def _process_custom_data(self, processor: dict, topic: str, payload: dict, client_id: str):
        """Procesar datos personalizados del proveedor"""
        # Ejecutar lógica personalizada
        logger.info(f"Custom data processed: {topic}")

    async def _default_message_processor(self, provider_code: str, topic: str, payload: dict, client_id: str):
        """Procesador por defecto para mensajes sin procesador específico"""
        try:
            # Intentar procesar como telemetría genérica
            await self._process_telemetry_data({}, topic, payload, client_id)

        except Exception as exc:
            logger.error(f"Error in default message processor: {exc}")

    def _extract_device_id(self, extractor_type: str, topic: str, payload: dict) -> Optional[str]:
        """Extraer device_id usando diferentes estrategias"""
        try:
            if extractor_type == 'topic':
                # Formato: provider/device_id/sensor/data
                parts = topic.split('/')
                return parts[1] if len(parts) > 1 else None

            elif extractor_type == 'payload':
                return payload.get('device_id') or payload.get('id')

            elif extractor_type == 'client_id':
                # Extraer del client_id MQTT
                return client_id.split('_')[-1] if '_' in str(client_id) else str(client_id)

            elif extractor_type == 'custom':
                # Lógica personalizada
                return self._custom_device_id_extraction(topic, payload)

        except Exception:
            pass

        return None

    def _custom_device_id_extraction(self, topic: str, payload: dict) -> Optional[str]:
        """Lógica personalizada de extracción de device_id"""
        # Implementar lógica específica por proveedor
        return payload.get('device_id')

    def _transform_payload_by_provider(self, provider_code: str, payload: dict, processor: dict) -> dict:
        """Transformar payload según mapeo específico del proveedor"""
        try:
            mapping = processor.get('field_mapping', {})

            if not mapping:
                return payload

            transformed = {}
            for target_field, source_info in mapping.items():
                if isinstance(source_info, str):
                    # Mapeo directo
                    transformed[target_field] = payload.get(source_info)
                elif isinstance(source_info, dict):
                    # Mapeo con transformación
                    source_field = source_info.get('source')
                    if source_field and source_field in payload:
                        value = payload[source_field]

                        # Aplicar transformaciones
                        if 'multiplier' in source_info:
                            value = float(value) * source_info['multiplier']
                        if 'offset' in source_info:
                            value = float(value) + source_info['offset']
                        if 'unit_conversion' in source_info:
                            value = self._convert_units(value, source_info['unit_conversion'])

                        transformed[target_field] = value

            # Mantener campos originales no mapeados
            for key, value in payload.items():
                if key not in transformed:
                    transformed[key] = value

            return transformed

        except Exception as exc:
            logger.error(f"Error transforming payload for provider {provider_code}: {exc}")
            return payload

    def _convert_units(self, value: float, conversion: str) -> float:
        """Convertir unidades de medida"""
        try:
            if conversion == 'celsius_to_fahrenheit':
                return (value * 9/5) + 32
            elif conversion == 'liters_to_gallons':
                return value * 0.264172
            elif conversion == 'meters_to_feet':
                return value * 3.28084
            # Agregar más conversiones según necesidad

            return value

        except Exception:
            return value

    async def publish_to_provider_topic(
        self,
        provider_code: str,
        topic_suffix: str,
        payload: dict,
        qos: int = 1
    ):
        """Publicar mensaje en topic específico del proveedor"""
        try:
            if provider_code not in self.provider_endpoints:
                raise ValueError(f"Unknown provider: {provider_code}")

            endpoint = self.provider_endpoints[provider_code]
            base_topic = endpoint['config'].get('publish_topic_prefix', provider_code)

            full_topic = f"{base_topic}/{topic_suffix}"

            # Publicar usando el cliente MQTT integrado
            # (Implementación simplificada - en producción usar cliente MQTT real)
            logger.info(f"Publishing to {full_topic}: {payload}")

        except Exception as exc:
            logger.error(f"Error publishing to provider topic: {exc}")

    async def get_provider_stats(self, provider_code: str) -> dict:
        """Obtener estadísticas del endpoint de proveedor"""
        if provider_code not in self.provider_endpoints:
            return {}

        endpoint = self.provider_endpoints[provider_code]

        return {
            'provider': provider_code,
            'topics': len(endpoint.get('topics', [])),
            'processors': len(endpoint.get('processors', [])),
            'active_connections': len([
                conn for conn in self.client_connections.values()
                if conn.get('provider') == provider_code
            ]),
            'registered_at': endpoint.get('created_at'),
        }

    async def shutdown(self):
        """Cerrar el broker MQTT"""
        try:
            if self.broker:
                await self.broker.shutdown()
                logger.info("SmartHydro MQTT Broker shut down")

        except Exception as exc:
            logger.error(f"Error shutting down MQTT broker: {exc}")


# Instancia global del broker
mqtt_broker = SmartHydroMQTTBroker()
