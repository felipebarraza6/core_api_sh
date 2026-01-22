"""
Management command para simular un mensaje MQTT y validar el flujo completo de ingesta.

Este comando permite dos modos de operación:
1. MODO SIMULACIÓN INTERNA (Default):
   - Simula el mensaje y llama directamente al parser y procesador interno.
   - Útil para validar lógica de parsing y guardado sin necesidad de broker.

2. MODO PUBLICACIÓN REAL (--publish):
   - Conecta al broker MQTT configurado y publica el mensaje real.
   - Opcionalmente espera (--wait) para verificar que el worker procesó el mensaje.
   - Útil para validar la integración completa (Broker -> Subscriber -> Ingestion).
"""

import json
import time
import uuid
from decimal import Decimal
import paho.mqtt.client as mqtt

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.conf import settings

from api.telemetry.providers.models import TelemetryProvider, CatchmentPointProvider
from api.telemetry.providers.mqtt_models import CatchmentPointMQTT, MQTTProviderConfig
from api.telemetry.providers.mqtt_parser import MQTTPayloadParser
from api.telemetry.models.telemetry import TelemetryRecord, CoreVariable
from api.telemetry.models.catchment_points import CatchmentPoint
from api.telemetry.ingestion.controllers.unified_processing import (
    process_variable_safely,
    save_telemetry_data
)
from api.infrastructure.models import Device


class Command(BaseCommand):
    help = 'Simula un mensaje MQTT y valida el flujo completo de ingesta'

    def add_arguments(self, parser):
        parser.add_argument(
            '--device-id',
            type=str,
            help='UUID del dispositivo (si no se especifica, usa el primer dispositivo con MQTT interno)'
        )
        parser.add_argument(
            '--publish',
            action='store_true',
            help='Si se activa, conecta al broker real y publica el mensaje.'
        )
        parser.add_argument(
            '--wait',
            action='store_true',
            help='En modo --publish, espera a que aparezca el registro en BD.'
        )
        # Valores de simulación
        parser.add_argument('--flow', type=float, default=2.5, help='Valor de caudal')
        parser.add_argument('--total', type=float, default=1250.7, help='Valor de total acumulado')
        parser.add_argument('--nivel', type=float, default=12.3, help='Valor de nivel')
        parser.add_argument('--pulses', type=int, default=5000, help='Valor de pulsos')

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING('\n' + '=' * 70))
        self.stdout.write(self.style.MIGRATE_HEADING('SIMULACIÓN DE MENSAJE MQTT'))
        self.stdout.write(self.style.MIGRATE_HEADING('=' * 70 + '\n'))

        # 1. Buscar configuración MQTT
        device_id = options.get('device_id')
        mqtt_point = self._find_mqtt_point(device_id)

        if not mqtt_point:
            return

        point = mqtt_point.point
        device = point.device
        provider = mqtt_point.provider
        mqtt_config = provider.mqtt_config

        self._print_config(point, device, mqtt_point, provider, mqtt_config)

        # 2. Construir mensaje
        timestamp = timezone.now()
        payload = {
            'timestamp': timestamp.isoformat(),
            'data': {
                'flow': options['flow'],
                'total': options['total'],
                'nivel': options['nivel'],
                'pulses': options['pulses'],
            }
        }
        topic = mqtt_point.get_subscribe_topic()
        payload_json = json.dumps(payload)

        self.stdout.write(self.style.SUCCESS('\n2. MENSAJE PREPARADO'))
        self.stdout.write(f'   Topic:   {topic}')
        self.stdout.write(f'   Payload: {json.dumps(payload, indent=2)}')

        # 3. Ejecutar según modo
        if options['publish']:
            self._run_publish_mode(mqtt_config, topic, payload_json, point, options['wait'])
        else:
            self._run_internal_simulation(mqtt_config, mqtt_point, topic, payload_json, payload, point, provider)

    def _find_mqtt_point(self, device_id):
        if device_id:
            try:
                return CatchmentPointMQTT.objects.select_related(
                    'point', 'point__device', 'provider', 'provider__mqtt_config'
                ).get(custom_device_id=device_id)
            except CatchmentPointMQTT.DoesNotExist:
                try:
                    # Intento buscar por point_code si no es device_id directo
                    return CatchmentPointMQTT.objects.select_related(
                        'point', 'point__device', 'provider', 'provider__mqtt_config'
                    ).get(point__point_code=device_id)
                except CatchmentPointMQTT.DoesNotExist:
                    self.stdout.write(self.style.ERROR(f'No se encontró CatchmentPointMQTT para: {device_id}'))
                    return None
        else:
            first = CatchmentPointMQTT.objects.select_related(
                'point', 'point__device', 'provider', 'provider__mqtt_config'
            ).filter(is_active=True).first()
            
            if not first:
                self.stdout.write(self.style.ERROR('No hay puntos con MQTT configurado'))
            return first

    def _print_config(self, point, device, mqtt_point, provider, mqtt_config):
        self.stdout.write(self.style.SUCCESS('1. CONFIGURACIÓN ENCONTRADA'))
        self.stdout.write(f'   Punto:      {point.title} ({point.point_code})')
        self.stdout.write(f'   Device ID:  {mqtt_point.get_effective_device_id()}')
        self.stdout.write(f'   Proveedor:  {provider.display_name}')
        self.stdout.write(f'   Broker:     {mqtt_config.broker_host}:{mqtt_config.broker_port}')
        self.stdout.write(f'   Mode:       {mqtt_config.mode}')

    def _run_publish_mode(self, config, topic, payload_str, point, wait):
        self.stdout.write(self.style.SUCCESS('\n3. MODO PUBLICACIÓN REAL'))
        
        client_id = f"simulator_{uuid.uuid4().hex[:8]}"
        client = mqtt.Client(client_id=client_id)

        if config.username:
            client.username_pw_set(config.username, config.password)
        
        if config.use_tls:
            client.tls_set()
            port = 8883
        else:
            port = config.broker_port

        try:
            self.stdout.write(f"   Conectando a {config.broker_host}:{port}...")
            client.connect(config.broker_host, port, 60)
            
            self.stdout.write(f"   Publicando en {topic}...")
            info = client.publish(topic, payload_str, qos=1)
            info.wait_for_publish()
            
            self.stdout.write(self.style.SUCCESS("   ✓ Mensaje publicado exitosamente"))
            client.disconnect()

            if wait:
                self._wait_for_record(point)

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"   ✗ Error MQTT: {e}"))

    def _wait_for_record(self, point):
        self.stdout.write(f"\n   Esperando ingestión (timeout 10s)...")
        start_count = TelemetryRecord.objects.filter(point=point).count()
        
        for i in range(10):
            time.sleep(1)
            current_count = TelemetryRecord.objects.filter(point=point).count()
            if current_count > start_count:
                last_record = TelemetryRecord.objects.filter(point=point).latest('timestamp')
                self.stdout.write(self.style.SUCCESS(f"   ✓ Nuevo registro detectado! ID: {last_record.id}"))
                self.stdout.write(f"     Timestamp: {last_record.timestamp}")
                return
            self.stdout.write(".", ending="")
        
        self.stdout.write(self.style.WARNING("\n   ⚠ Timeout esperando registro. Verifica logs del worker."))

    def _run_internal_simulation(self, mqtt_config, mqtt_point, topic, payload_str, payload_dict, point, provider):
        self.stdout.write(self.style.SUCCESS('\n3. MODO SIMULACIÓN INTERNA (MOCK)'))
        
        # 3.1 Parsing
        parser = MQTTPayloadParser(mqtt_config)
        parsed_data = parser.parse(topic, payload_str.encode('utf-8'), mqtt_point.get_effective_device_id())
        
        # Fallback si el parser falla (ej: falta librería jmespath)
        if 'error' in parsed_data.get('metadata', {}):
            self.stdout.write(self.style.WARNING(f"   ⚠ Parser arrojó error, usando payload directo como fallback."))
            data_dict = payload_dict.get('data', payload_dict)
            parsed_data.update(data_dict)
        
        self.stdout.write(f"   Datos parseados: {json.dumps(parsed_data, indent=2, default=str)}")

        # 3.2 Processing
        self.stdout.write(self.style.SUCCESS('\n4. PROCESAMIENTO VARIABLES'))
        
        point_providers = CatchmentPointProvider.objects.filter(
            point=point, provider=provider, is_active=True
        ).select_related('variable')

        created_register = {
            'point_id': point.id,
            'metadata': {
                'source': 'mqtt_simulation_mock',
                'provider': provider.name,
                'device_id': mqtt_point.get_effective_device_id(),
                'received_at': timezone.now().isoformat()
            }
        }

        # Simulación simplificada de unified_processing
        # En la realidad esto lo hace DynamicMQTTHandler que mapea parsed_data -> registro
        # Aquí reconstruimos ese mapeo manualmente para validar 'process_variable_safely'
        
        # NOTA: DynamicMQTTHandler usa un mapeo directo parsed_data -> created_register fields
        # Pero process_variable_safely se usa mas para cuando traemos datos raw de APIs.
        # Para MQTT, el handler hace el trabajo pesado.
        
        # Replicando lógica de DynamicMQTTHandler._process_parsed_message
        created_register.update({
            "date_time_medition": parsed_data.get('timestamp') or timezone.now(),
            "date_time_last_logger": parsed_data.get('timestamp') or timezone.now(),
            "device_id": mqtt_point.get_effective_device_id(),
            "is_error": False,
        })

        # Mapeo directo
        for field in ['flow', 'nivel', 'water_table', 'total', 'pulses']:
            if field in parsed_data:
                created_register[field] = parsed_data[field]
                self.stdout.write(f"   Mapeado {field}: {parsed_data[field]}")

        # 3.3 Guardado
        self.stdout.write(self.style.SUCCESS('\n5. GUARDADO (save_telemetry_data)'))
        try:
            record = save_telemetry_data(point.id, created_register)
            if record:
                self.stdout.write(self.style.SUCCESS(f"   ✓ Registro guardado id={record.id}"))
                self.stdout.write(f"     Data: {record.data}")
            else:
                self.stdout.write(self.style.ERROR("   ✗ Falló save_telemetry_data"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"   ✗ Error guardando: {e}"))
