"""
Management command para configurar el proveedor MQTT interno de SmartHydro.

Crea:
1. TelemetryProvider para MQTT interno
2. MQTTProviderConfig con configuración del broker local
3. PayloadParsingRule para parsear mensajes JSON estándar
4. Vincula un Device de prueba a un CatchmentPoint
5. Configura CatchmentPointMQTT para recibir datos
"""

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

from api.telemetry.providers.models import TelemetryProvider, CatchmentPointProvider
from api.telemetry.providers.mqtt_models import (
    MQTTProviderConfig,
    PayloadParsingRule,
    CatchmentPointMQTT
)
from api.telemetry.models.catchment_points import CatchmentPoint
from api.telemetry.models.telemetry import CoreVariable, TelemetryScheme, SchemeVariable
from api.infrastructure.models import Device


User = get_user_model()


class Command(BaseCommand):
    help = 'Configura el proveedor MQTT interno de SmartHydro con datos de prueba'

    def add_arguments(self, parser):
        parser.add_argument(
            '--device-name',
            type=str,
            default='NETTRA-NRTU-2000-001',
            help='Nombre del dispositivo a vincular (default: NETTRA-NRTU-2000-001)'
        )

    def handle(self, *args, **options):
        device_name = options['device_name']

        self.stdout.write(self.style.MIGRATE_HEADING('Configurando MQTT interno de SmartHydro...\n'))

        # 1. Crear o obtener TelemetryProvider para MQTT interno
        provider, created = TelemetryProvider.objects.get_or_create(
            name='smarthydro_mqtt',
            defaults={
                'display_name': 'SmartHydro MQTT Interno',
                'description': 'Broker MQTT local para dispositivos que publican directamente a SmartHydro',
                'provider_type': 'mqtt_server',
                'base_url': 'mqtt://localhost:1883',
                'auth_method': 'basic',
                'auth_config': {
                    'username': 'smarthydro',
                    'password': 'dev_mqtt_password'
                },
                'endpoint_template': '/smarthydro/{device_id}/telemetry',
                'is_active': True,
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f'✓ TelemetryProvider creado: {provider.display_name}'))
        else:
            self.stdout.write(f'  TelemetryProvider existente: {provider.display_name}')

        # 2. Crear o obtener MQTTProviderConfig
        mqtt_config, created = MQTTProviderConfig.objects.get_or_create(
            provider=provider,
            defaults={
                'service_identifier': 'smarthydro',
                'mode': 'server',
                'broker_host': 'localhost',
                'broker_port': 1883,
                'use_tls': False,
                'client_id_prefix': 'smarthydro_sub',
                'subscribe_topic_template': 'smarthydro/{device_id}/telemetry',
                'publish_topic_template': 'smarthydro/{device_id}/commands',
                'default_qos': 1,
                'retain_messages': False,
                'username': 'smarthydro',
                'password': 'dev_mqtt_password',
                'keep_alive': 60,
                'reconnect_delay': 5,
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f'✓ MQTTProviderConfig creado'))
        else:
            self.stdout.write(f'  MQTTProviderConfig existente')

        # 3. Crear regla de parsing para JSON estándar
        parsing_rule, created = PayloadParsingRule.objects.get_or_create(
            provider=provider,
            name='JSON Estándar SmartHydro',
            defaults={
                'description': 'Parsea mensajes JSON con estructura {timestamp, data: {var_code: value}}',
                'rule_type': 'always',
                'rule_condition': {},
                'priority': 100,
                'parsing_method': 'jsonpath',
                'field_mappings': {
                    'timestamp': 'timestamp',
                    'flow': 'data.flow',
                    'total': 'data.total',
                    'nivel': 'data.nivel',
                    'pulses': 'data.pulses',
                    'battery': 'data.battery',
                    'signal': 'data.signal',
                },
                'transformations': [],
                'validation_rules': {
                    'required_fields': ['timestamp'],
                },
                'is_active': True,
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f'✓ PayloadParsingRule creado: {parsing_rule.name}'))
        else:
            self.stdout.write(f'  PayloadParsingRule existente: {parsing_rule.name}')

        # 4. Buscar Device con MQTT interno
        try:
            device = Device.objects.get(name=device_name)
            if not device.use_internal_mqtt:
                self.stdout.write(self.style.WARNING(
                    f'⚠ El dispositivo {device_name} no usa MQTT interno. '
                    f'Cambiando use_internal_mqtt=True...'
                ))
                device.use_internal_mqtt = True
                device.save(update_fields=['use_internal_mqtt'])

            self.stdout.write(self.style.SUCCESS(f'✓ Device encontrado: {device.name} (token: {device.token[:8]}...)'))
        except Device.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'✗ No se encontró dispositivo {device_name}'))
            self.stdout.write('  Ejecute primero: python manage.py create_test_devices')
            return

        # 5. Crear o obtener usuario de prueba para el punto
        user, created = User.objects.get_or_create(
            username='test_mqtt_user',
            defaults={
                'email': 'test_mqtt@smarthydro.cl',
                'first_name': 'Test',
                'last_name': 'MQTT User',
            }
        )
        if created:
            user.set_password('testpass123')
            user.save()
            self.stdout.write(self.style.SUCCESS(f'✓ Usuario de prueba creado: {user.username}'))
        else:
            self.stdout.write(f'  Usuario existente: {user.username}')

        # 6. Crear o obtener TelemetryScheme para el punto
        scheme, created = TelemetryScheme.objects.get_or_create(
            name='Esquema MQTT Básico',
            defaults={
                'description': 'Esquema básico para puntos con dispositivos MQTT internos'
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f'✓ TelemetryScheme creado: {scheme.name}'))

            # Crear variables del esquema
            scheme_vars = [
                {'name': 'Caudal', 'internal_code': 'flow', 'unit': 'm³/h', 'type_variable': 'CAUDAL'},
                {'name': 'Total Acumulado', 'internal_code': 'total', 'unit': 'm³', 'type_variable': 'TOTALIZADO'},
                {'name': 'Nivel', 'internal_code': 'nivel', 'unit': 'm', 'type_variable': 'NIVEL'},
                {'name': 'Pulsos', 'internal_code': 'pulses', 'unit': 'pulsos', 'type_variable': 'GENERIC'},
            ]
            for sv_data in scheme_vars:
                SchemeVariable.objects.create(scheme=scheme, **sv_data)
            self.stdout.write(f'    + {len(scheme_vars)} variables de esquema creadas')
        else:
            self.stdout.write(f'  TelemetryScheme existente: {scheme.name}')

        # 7. Crear o obtener CatchmentPoint vinculado al Device
        point, created = CatchmentPoint.objects.get_or_create(
            point_code=f'MQTT-TEST-{device.device_id.hex[:8].upper()}',
            defaults={
                'title': f'Punto de Prueba MQTT ({device.name})',
                'owner_user': user,
                'device': device,
                'processing_scheme': scheme,
                'lat': '-33.4489',
                'lon': '-70.6693',
                'is_active': True,
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f'✓ CatchmentPoint creado: {point.title}'))
        else:
            # Actualizar device si no estaba vinculado
            if point.device != device:
                point.device = device
                point.save(update_fields=['device'])
                self.stdout.write(self.style.SUCCESS(f'✓ CatchmentPoint actualizado con Device'))
            else:
                self.stdout.write(f'  CatchmentPoint existente: {point.title}')

        # 8. Crear CoreVariables para el punto
        core_vars_data = [
            {'name': 'Caudal Instantáneo', 'internal_code': 'flow', 'type_variable': 'flow', 'unit': 'm³/h'},
            {'name': 'Total Acumulado', 'internal_code': 'total', 'type_variable': 'total', 'unit': 'm³'},
            {'name': 'Nivel Freático', 'internal_code': 'nivel', 'type_variable': 'nivel', 'unit': 'm'},
            {'name': 'Pulsos Sensor', 'internal_code': 'pulses', 'type_variable': 'pulses', 'unit': 'pulsos'},
        ]

        for cv_data in core_vars_data:
            var, created = CoreVariable.objects.get_or_create(
                point=point,
                internal_code=cv_data['internal_code'],
                defaults={
                    'name': cv_data['name'],
                    'type_variable': cv_data['type_variable'],
                    'unit': cv_data['unit'],
                    'is_active': True,
                }
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'  ✓ CoreVariable creado: {var.name}'))

                # 9. Crear CatchmentPointProvider para mapear variable al proveedor
                CatchmentPointProvider.objects.create(
                    point=point,
                    provider=provider,
                    variable=var,
                    device=device,
                    provider_device_id=cv_data['internal_code'],  # Key en el JSON del proveedor
                    is_active=True,
                    priority=10,
                )
                self.stdout.write(f'    + CatchmentPointProvider creado para {var.internal_code}')

        # 10. Crear CatchmentPointMQTT
        mqtt_point, created = CatchmentPointMQTT.objects.get_or_create(
            point=point,
            defaults={
                'provider': provider,
                'custom_device_id': str(device.device_id),
                'is_active': True,
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f'✓ CatchmentPointMQTT creado'))
        else:
            self.stdout.write(f'  CatchmentPointMQTT existente')

        # Resumen final
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(self.style.SUCCESS('CONFIGURACIÓN MQTT COMPLETADA'))
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write('')
        self.stdout.write(f'Dispositivo: {device.name}')
        self.stdout.write(f'Device ID:   {device.device_id}')
        self.stdout.write(f'Token:       {device.token}')
        self.stdout.write(f'Punto:       {point.title} ({point.point_code})')
        self.stdout.write('')
        self.stdout.write('Topic de suscripción:')
        self.stdout.write(f'  smarthydro/{device.device_id}/telemetry')
        self.stdout.write('')
        self.stdout.write('Ejemplo de mensaje para publicar:')
        self.stdout.write('''
mosquitto_pub -h localhost -p 1883 \\
  -u smarthydro -P dev_mqtt_password \\
  -t "smarthydro/{device_id}/telemetry" \\
  -m '{{"timestamp": "2026-01-22T15:00:00Z", "data": {{"flow": 2.5, "total": 1250.7, "nivel": 12.3, "pulses": 5000}}}}'
'''.replace('{device_id}', str(device.device_id)))
        self.stdout.write('')
