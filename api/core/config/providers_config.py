"""
Configuración de Proveedores MQTT
Ejemplos de configuración para diferentes proveedores de equipos IoT
"""

from api.core.models import EquipmentProvider, EquipmentModel, MQTTConnection

# Configuraciones de proveedores
PROVIDER_CONFIGS = {
    'NOVUS': {
        'name': 'Novus Automation',
        'code': 'NOVUS',
        'mqtt_config': {
            'broker_host': 'mqtt.novus.cl',
            'broker_port': 8883,
            'use_tls': True,
            'username': 'smarthydro_client',
            'client_id': 'smarthydro_novus_001',
            'subscribe_topics': [
                'novus/devices/+/telemetry',
                'novus/devices/+/status',
                'novus/devices/+/commands/response'
            ],
            'publish_topic_prefix': 'novus/commands'
        },
        'endpoint_config': {
            'topics': [
                'novus/devices/+/telemetry',
                'novus/devices/+/status',
                'novus/devices/+/commands',
                'novus/system/announcements'
            ],
            'processors': [
                {
                    'type': 'telemetry',
                    'topic_pattern': 'novus/devices/+/telemetry',
                    'device_id_extractor': 'topic',  # Extraer de topic: novus/devices/{device_id}/telemetry
                    'field_mapping': {
                        'flow': 'flow_rate_lpm',  # Mapear flow_rate_lpm -> flow
                        'nivel': {'source': 'water_level_cm', 'multiplier': 0.01},  # cm -> m
                        'temperature': 'temperature_c',
                        'battery': {'source': 'battery_percent', 'unit_conversion': None},
                        'signal': 'rssi_dbm'
                    }
                },
                {
                    'type': 'status',
                    'topic_pattern': 'novus/devices/+/status',
                    'device_id_extractor': 'topic'
                },
                {
                    'type': 'command_response',
                    'topic_pattern': 'novus/devices/+/commands/response',
                    'device_id_extractor': 'topic'
                }
            ]
        }
    },

    'TTN': {  # The Things Network
        'name': 'The Things Network',
        'code': 'TTN',
        'mqtt_config': {
            'broker_host': 'eu1.cloud.thethings.network',
            'broker_port': 8883,
            'use_tls': True,
            'username': 'smarthydro@ttn',
            'client_id': 'smarthydro_ttn_001',
            'subscribe_topics': [
                'v3/+/devices/+/up',  # Uplink messages
                'v3/+/devices/+/down/queued',  # Downlink queued
                'v3/+/devices/+/down/sent',  # Downlink sent
                'v3/+/devices/+/down/ack',  # Downlink acknowledged
            ],
            'publish_topic_prefix': 'v3/+/devices/+/down/push'
        },
        'endpoint_config': {
            'topics': [
                'v3/+/devices/+/up',
                'v3/+/devices/+/down/+',
                'v3/+/devices/+/events/+'
            ],
            'processors': [
                {
                    'type': 'telemetry',
                    'topic_pattern': 'v3/+/devices/+/up',
                    'device_id_extractor': 'topic',  # Extraer device_id del topic
                    'field_mapping': {
                        'flow': {'source': 'payload.flow_lpm', 'unit_conversion': None},
                        'nivel': {'source': 'payload.level_m', 'unit_conversion': None},
                        'temperature': 'payload.temperature_c',
                        'battery': {'source': 'payload.battery_v', 'multiplier': 100},  # V -> %
                        'signal': {'source': 'metadata.gateways.0.rssi', 'unit_conversion': None}
                    }
                },
                {
                    'type': 'status',
                    'topic_pattern': 'v3/+/devices/+/events/+',
                    'device_id_extractor': 'topic'
                }
            ]
        }
    },

    'TWIN': {
        'name': 'Twin Technologies',
        'code': 'TWIN',
        'mqtt_config': {
            'broker_host': 'mqtt.twin.cl',
            'broker_port': 1883,
            'use_tls': False,
            'username': 'smarthydro_api',
            'client_id': 'smarthydro_twin_001',
            'subscribe_topics': [
                'twin/devices/+/data',
                'twin/devices/+/status',
                'twin/devices/+/response'
            ],
            'publish_topic_prefix': 'twin/commands'
        },
        'endpoint_config': {
            'topics': [
                'twin/devices/+/data',
                'twin/devices/+/status',
                'twin/devices/+/commands',
                'twin/system/status'
            ],
            'processors': [
                {
                    'type': 'telemetry',
                    'topic_pattern': 'twin/devices/+/data',
                    'device_id_extractor': 'topic',
                    'field_mapping': {
                        'flow': 'sensors.flow.value',
                        'nivel': {'source': 'sensors.level.value', 'unit_conversion': None},
                        'total': 'sensors.totalizer.value',
                        'battery': {'source': 'system.battery.level', 'unit_conversion': None},
                        'signal': 'system.signal.strength'
                    }
                },
                {
                    'type': 'status',
                    'topic_pattern': 'twin/devices/+/status',
                    'device_id_extractor': 'topic'
                }
            ]
        }
    },

    'CUSTOM_PROVIDER': {
        'name': 'Proveedor Personalizado',
        'code': 'CUSTOM',
        'mqtt_config': {
            'broker_host': 'mqtt.custom-provider.com',
            'broker_port': 8883,
            'use_tls': True,
            'username': 'smarthydro_user',
            'client_id': 'smarthydro_custom_001',
            'subscribe_topics': [
                'custom/devices/+/telemetry',
                'custom/devices/+/heartbeat',
                'custom/devices/+/alerts'
            ],
            'publish_topic_prefix': 'custom/commands'
        },
        'endpoint_config': {
            'topics': [
                'custom/devices/+/telemetry',
                'custom/devices/+/heartbeat',
                'custom/devices/+/alerts',
                'custom/commands/+'
            ],
            'processors': [
                {
                    'type': 'telemetry',
                    'topic_pattern': 'custom/devices/+/telemetry',
                    'device_id_extractor': 'topic',
                    'field_mapping': {
                        # Configurar según API del proveedor personalizado
                        'flow': 'data.flow',
                        'nivel': 'data.level',
                        'temperature': 'data.temp',
                        'battery': 'status.battery',
                        'signal': 'status.rssi'
                    }
                },
                {
                    'type': 'status',
                    'topic_pattern': 'custom/devices/+/heartbeat',
                    'device_id_extractor': 'topic'
                },
                {
                    'type': 'custom',
                    'topic_pattern': 'custom/devices/+/alerts',
                    'device_id_extractor': 'topic',
                    'custom_handler': 'handle_custom_alerts'
                }
            ]
        }
    }
}

# Modelos de equipos por proveedor
EQUIPMENT_MODELS = {
    'NOVUS': [
        {
            'model_name': 'Flow Meter Pro',
            'model_code': 'NVS-FMP-001',
            'description': 'Medidor de caudal profesional con batería de larga duración',
            'power_supply': 'Batería Li-ion 3.6V',
            'battery_life_days': 365,
            'operating_temperature_min': -20,
            'operating_temperature_max': 60,
            'available_sensors': {
                'flow': {'type': 'electromagnetic', 'range': '0.1-1000 L/min', 'accuracy': '±1%'},
                'temperature': {'type': 'PT100', 'range': '-50°C to 150°C', 'accuracy': '±0.5°C'},
                'pressure': {'type': 'ceramic', 'range': '0-10 bar', 'accuracy': '±0.1 bar'}
            },
            'communication_range_meters': 1000,
            'data_transmission_interval_min': 15,
            'firmware_version': '2.1.4'
        },
        {
            'model_name': 'Level Sensor Plus',
            'model_code': 'NVS-LSP-002',
            'description': 'Sensor de nivel ultrasónico con compensación de temperatura',
            'power_supply': 'Batería 9V Alcalina',
            'battery_life_days': 180,
            'operating_temperature_min': -10,
            'operating_temperature_max': 70,
            'available_sensors': {
                'level': {'type': 'ultrasonic', 'range': '0.2-5m', 'accuracy': '±2mm'},
                'temperature': {'type': 'NTC', 'range': '-20°C to 80°C', 'accuracy': '±1°C'}
            },
            'communication_range_meters': 800,
            'data_transmission_interval_min': 30,
            'firmware_version': '1.8.2'
        }
    ],

    'TTN': [
        {
            'model_name': 'LoRa Flow Monitor',
            'model_code': 'TTN-LFM-001',
            'description': 'Monitor de caudal LoRaWAN de bajo consumo',
            'power_supply': '2x AA Alcalinas',
            'battery_life_days': 730,  # 2 años
            'operating_temperature_min': -20,
            'operating_temperature_max': 55,
            'available_sensors': {
                'flow': {'type': 'turbine', 'range': '1-5000 L/h', 'accuracy': '±2%'},
                'battery_voltage': {'type': 'ADC', 'range': '0-5V', 'accuracy': '±0.1V'}
            },
            'communication_range_meters': 10000,  # LoRa range
            'data_transmission_interval_min': 60,  # Cada hora para ahorrar batería
            'firmware_version': '3.2.1'
        }
    ],

    'TWIN': [
        {
            'model_name': 'Smart Telemetry Unit',
            'model_code': 'TWIN-STU-001',
            'description': 'Unidad de telemetría inteligente con múltiples sensores',
            'power_supply': 'Panel Solar + Batería',
            'battery_life_days': 1095,  # 3 años con panel solar
            'operating_temperature_min': -30,
            'operating_temperature_max': 75,
            'available_sensors': {
                'flow': {'type': 'electromagnetic', 'range': '0.5-2000 m³/h', 'accuracy': '±0.5%'},
                'level': {'type': 'radar', 'range': '0-20m', 'accuracy': '±1cm'},
                'pressure': {'type': 'piezoresistive', 'range': '0-50 bar', 'accuracy': '±0.05%'},
                'temperature': {'type': 'PT1000', 'range': '-50°C to 200°C', 'accuracy': '±0.2°C'},
                'conductivity': {'type': 'electrodal', 'range': '0-200 mS/cm', 'accuracy': '±1%'}
            },
            'communication_range_meters': 2000,
            'data_transmission_interval_min': 5,
            'firmware_version': '4.1.0'
        }
    ]
}

def setup_provider_configurations():
    """
    Configurar proveedores y modelos de equipos automáticamente
    """
    from django.core.management import call_command

    # Crear proveedores
    for provider_code, config in PROVIDER_CONFIGS.items():
        provider, created = EquipmentProvider.objects.get_or_create(
            code=provider_code,
            defaults={
                'name': config['name'],
                'website': config.get('website', ''),
                'description': config['description'] if 'description' in config else f'Proveedor {config["name"]}',
                'integration_status': 'PRODUCTION' if provider_code in ['NOVUS', 'TTN'] else 'TESTING'
            }
        )

        if created:
            print(f"✅ Created provider: {provider.name}")

        # Crear conexión MQTT
        if 'mqtt_config' in config:
            mqtt_config = config['mqtt_config']
            connection, conn_created = MQTTConnection.objects.get_or_create(
                provider=provider,
                client_id=mqtt_config['client_id'],
                defaults={
                    'connection_name': f'{provider_code} Connection',
                    'broker_host': mqtt_config['broker_host'],
                    'broker_port': mqtt_config['broker_port'],
                    'username': mqtt_config.get('username', ''),
                    'password': mqtt_config.get('password', ''),
                    'use_tls': mqtt_config.get('use_tls', False),
                    'subscribe_topics': mqtt_config['subscribe_topics'],
                    'publish_topic_prefix': mqtt_config['publish_topic_prefix']
                }
            )

            if conn_created:
                print(f"✅ Created MQTT connection for {provider.name}")

    # Crear modelos de equipos
    for provider_code, models_list in EQUIPMENT_MODELS.items():
        try:
            provider = EquipmentProvider.objects.get(code=provider_code)

            for model_config in models_list:
                model, model_created = EquipmentModel.objects.get_or_create(
                    provider=provider,
                    model_code=model_config['model_code'],
                    defaults=model_config
                )

                if model_created:
                    print(f"✅ Created equipment model: {model.model_name}")

        except EquipmentProvider.DoesNotExist:
            print(f"⚠️  Provider {provider_code} not found, skipping models")

    print("🎉 Provider configurations completed!")


def get_provider_endpoint_config(provider_code: str) -> dict:
    """
    Obtener configuración de endpoint para un proveedor específico
    """
    return PROVIDER_CONFIGS.get(provider_code, {}).get('endpoint_config', {})


def validate_provider_message(provider_code: str, topic: str, payload: dict) -> bool:
    """
    Validar mensaje de proveedor según su configuración
    """
    config = get_provider_endpoint_config(provider_code)
    if not config:
        return False

    # Validar que el topic esté permitido
    allowed_topics = config.get('topics', [])
    if not any(topic_pattern in topic for topic_pattern in allowed_topics):
        return False

    # Aquí se pueden agregar más validaciones específicas
    return True


if __name__ == '__main__':
    # Ejecutar configuración cuando se llame directamente
    setup_provider_configurations()