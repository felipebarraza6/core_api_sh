"""
Configuración Completa del Sistema de Constantes y Sincronización
Integración automática con proveedores y gestión histórica
"""

from django.conf import settings
from api.telemetry.models.management_super import SystemConfiguration

# Configuración de constantes por defecto para diferentes proveedores
DEFAULT_CONSTANTS_CONFIG = {
    'NOVUS': {
        'FLOW_MULTIPLIER': {
            'name': 'Multiplicador de Caudal Novus',
            'code': 'NOVUS_FLOW_MULT',
            'constant_type': 'FLOW_MULTIPLIER',
            'value_numeric': 1.0,
            'description': 'Factor de corrección para mediciones de caudal Novus'
        },
        'TOTALIZER_OFFSET': {
            'name': 'Offset Totalizador Novus',
            'code': 'NOVUS_TOTAL_OFFSET',
            'constant_type': 'TOTALIZER_OFFSET',
            'value_numeric': 0.0,
            'description': 'Corrección de offset para totalizadores Novus'
        }
    },

    'TTN': {
        'BATTERY_CALIBRATION': {
            'name': 'Calibración Batería TTN',
            'code': 'TTN_BATTERY_CAL',
            'constant_type': 'BATTERY_CALIBRATION',
            'value_numeric': 0.0,
            'description': 'Corrección de nivel de batería para dispositivos TTN'
        }
    },

    'TWIN': {
        'LEVEL_OFFSET': {
            'name': 'Offset Nivel Twin',
            'code': 'TWIN_LEVEL_OFFSET',
            'constant_type': 'LEVEL_OFFSET',
            'value_numeric': 0.0,
            'description': 'Corrección de offset para mediciones de nivel Twin'
        }
    }
}

# Configuración de sincronización automática por proveedor
DEFAULT_SYNC_CONFIG = {
    'NOVUS': {
        'sync_type': 'INCREMENTAL',
        'sync_interval_minutes': 15,  # Cada 15 minutos
        'sync_config': {
            'historical_endpoint': {
                'url': 'https://api.novus.cl/v1/devices/{device_id}/historical',
                'method': 'GET',
                'auth_type': 'bearer'
            },
            'incremental_endpoint': {
                'url': 'https://api.novus.cl/v1/devices/{device_id}/recent',
                'method': 'GET',
                'auth_type': 'bearer'
            },
            'buffer_hours': 1,
            'max_records_per_request': 1000,
            'field_mapping': {
                'flow': 'flow_rate_lpm',
                'level': 'water_level_cm',
                'total': 'totalizer_m3',
                'temperature': 'temperature_c',
                'battery': 'battery_percent'
            }
        }
    },

    'TTN': {
        'sync_type': 'REALTIME',
        'sync_interval_minutes': 5,  # Cada 5 minutos para realtime
        'sync_config': {
            'mqtt_broker': 'eu1.cloud.thethings.network',
            'mqtt_port': 8883,
            'mqtt_use_tls': True,
            'mqtt_topics': [
                'v3/+/devices/+/up',
                'v3/+/devices/+/down/acked',
                'v3/+/devices/+/events/#'
            ],
            'field_mapping': {
                'flow': {'source': 'payload.flow_lpm', 'conversion': None},
                'level': {'source': 'payload.level_m', 'conversion': None},
                'battery': {'source': 'payload.battery_v', 'multiplier': 100},
                'signal': {'source': 'metadata.gateways.0.rssi', 'conversion': None}
            }
        }
    },

    'TWIN': {
        'sync_type': 'INCREMENTAL',
        'sync_interval_minutes': 10,
        'sync_config': {
            'historical_endpoint': {
                'url': 'https://api.twin.cl/data/historical/{device_id}',
                'method': 'POST',
                'auth_type': 'basic'
            },
            'field_mapping': {
                'flow': 'sensors.flow.value',
                'level': 'sensors.level.value',
                'total': 'sensors.totalizer.value',
                'temperature': 'sensors.temperature.value',
                'battery': 'system.battery.level'
            }
        }
    }
}

# Configuración de constantes históricas por defecto
DEFAULT_HISTORICAL_CONSTANTS = [
    {
        'name': 'Reset Contador 2024-01-15',
        'code': 'RESET_20240115',
        'constant_type': 'TOTALIZER_OFFSET',
        'value_numeric': 15000.5,  # Valor perdido por reset
        'scope': 'GLOBAL',  # Aplica a todos
        'description': 'Corrección por reset de contador general el 15/01/2024'
    },
    {
        'name': 'Calibración Caudal Q1 2024',
        'code': 'FLOW_CAL_Q1_2024',
        'constant_type': 'FLOW_MULTIPLIER',
        'value_numeric': 1.05,  # 5% de corrección
        'scope': 'GLOBAL',
        'description': 'Ajuste de calibración para todos los medidores de caudal Q1 2024'
    }
]

def initialize_provider_constants_and_sync():
    """
    Inicializar constantes y configuraciones de sincronización para proveedores
    """
    from api.core.models import (
        EquipmentProvider, ConstantDefinition,
        ProviderDataSync
    )

    # Inicializar constantes por proveedor
    for provider_code, constants in DEFAULT_CONSTANTS_CONFIG.items():
        try:
            provider = EquipmentProvider.objects.get(code=provider_code)

            for constant_data in constants.values():
                constant, created = ConstantDefinition.objects.get_or_create(
                    code=constant_data['code'],
                    defaults={
                        **constant_data,
                        'is_active': True
                    }
                )

                if created:
                    print(f"✅ Created constant: {constant.name} for {provider.name}")

        except EquipmentProvider.DoesNotExist:
            print(f"⚠️  Provider {provider_code} not found, skipping constants")

    # Inicializar configuraciones de sincronización
    for provider_code, sync_data in DEFAULT_SYNC_CONFIG.items():
        try:
            provider = EquipmentProvider.objects.get(code=provider_code)

            # Crear configuración MQTT si aplica
            if 'mqtt_broker' in sync_data['sync_config']:
                mqtt_config = sync_data['sync_config']
                # Aquí se crearía la conexión MQTT
                print(f"📡 MQTT config needed for {provider.name}")

            # Crear configuración de sync
            sync_config, created = ProviderDataSync.objects.get_or_create(
                provider=provider,
                defaults={
                    'sync_type': sync_data['sync_type'],
                    'sync_interval_minutes': sync_data['sync_interval_minutes'],
                    'sync_config': sync_data['sync_config'],
                    'is_active': True
                }
            )

            if created:
                print(f"✅ Created sync config for {provider.name}")

        except EquipmentProvider.DoesNotExist:
            print(f"⚠️  Provider {provider_code} not found, skipping sync config")

    # Inicializar constantes históricas por defecto
    for constant_data in DEFAULT_HISTORICAL_CONSTANTS:
        constant, created = ConstantDefinition.objects.get_or_create(
            code=constant_data['code'],
            defaults={
                **constant_data,
                'is_active': True
            }
        )

        if created:
            print(f"✅ Created historical constant: {constant.name}")

    print("🎉 Provider constants and sync configurations initialized!")


def setup_system_configuration():
    """
    Configurar parámetros del sistema para constantes y sincronización
    """
    system_configs = [
        {
            'key': 'constants.auto_apply_historical',
            'value': {'enabled': True, 'max_records_per_batch': 1000},
            'category': 'CONSTANTS',
            'description': 'Configuración para aplicación automática de constantes históricas'
        },
        {
            'key': 'sync.auto_initialize_providers',
            'value': {'enabled': True, 'default_sync_type': 'INCREMENTAL'},
            'category': 'SYNC',
            'description': 'Configuración para inicialización automática de proveedores'
        },
        {
            'key': 'sync.health_check_interval',
            'value': {'minutes': 30, 'alert_on_failures': True},
            'category': 'SYNC',
            'description': 'Configuración de health checks para sincronización'
        },
        {
            'key': 'constants.validation_rules',
            'value': {
                'max_offset_change_percent': 50,
                'require_approval_for_large_changes': True,
                'large_change_threshold': 1000
            },
            'category': 'CONSTANTS',
            'description': 'Reglas de validación para cambios de constantes'
        },
        {
            'key': 'sync.retry_policy',
            'value': {
                'max_retries': 3,
                'backoff_factor': 2,
                'max_backoff_seconds': 3600
            },
            'category': 'SYNC',
            'description': 'Política de reintentos para sincronización'
        }
    ]

    for config_data in system_configs:
        config, created = SystemConfiguration.objects.get_or_create(
            key=config_data['key'],
            defaults=config_data
        )

        if created:
            print(f"✅ Created system config: {config.key}")

    print("🎉 System configurations initialized!")


def validate_constant_change(constant: 'ConstantDefinition',
                           new_value: float,
                           user=None) -> tuple[bool, str]:
    """
    Validar un cambio de constante según reglas del sistema
    """
    try:
        # Obtener configuración de validación
        validation_config = SystemConfiguration.objects.filter(
            key='constants.validation_rules'
        ).first()

        if not validation_config:
            return True, "No validation rules configured"

        rules = validation_config.value

        # Validar cambio máximo permitido
        if hasattr(constant, 'value_numeric') and constant.value_numeric:
            current_value = float(constant.value_numeric)
            change_percent = abs((new_value - current_value) / current_value) * 100

            max_change = rules.get('max_offset_change_percent', 100)
            if change_percent > max_change:
                return False, f"Cambio de {change_percent:.1f}% excede el máximo permitido ({max_change}%)"

        # Validar si requiere aprobación
        large_change_threshold = rules.get('large_change_threshold', 10000)
        requires_approval = rules.get('require_approval_for_large_changes', False)

        if requires_approval and abs(new_value) > large_change_threshold:
            if not user or not user.is_staff:
                return False, f"Cambios grandes requieren aprobación de administrador"

        return True, "Cambio válido"

    except Exception as exc:
        return False, f"Error de validación: {exc}"


def get_sync_status_summary() -> dict:
    """
    Obtener resumen del estado de sincronización de todos los proveedores
    """
    from api.core.models import ProviderDataSync

    syncs = ProviderDataSync.objects.select_related('provider')

    summary = {
        'total_providers': syncs.count(),
        'active_syncs': 0,
        'healthy_syncs': 0,
        'failed_syncs': 0,
        'total_records_synced': 0,
        'providers': []
    }

    for sync in syncs:
        if sync.is_active:
            summary['active_syncs'] += 1

        if sync.current_status == 'SUCCESS':
            summary['healthy_syncs'] += 1
        elif sync.current_status == 'FAILED':
            summary['failed_syncs'] += 1

        summary['total_records_synced'] += sync.total_records_synced

        summary['providers'].append({
            'name': sync.provider.name,
            'code': sync.provider.code,
            'status': sync.current_status,
            'last_sync': sync.last_successful_sync.isoformat() if sync.last_successful_sync else None,
            'records_synced': sync.total_records_synced,
            'is_active': sync.is_active
        })

    return summary


def initialize_all():
    """
    Inicializar todo el sistema de constantes y sincronización
    """
    print("🚀 Initializing SmartHydro Constants & Sync System...")
    print("=" * 60)

    try:
        initialize_provider_constants_and_sync()
        print()

        setup_system_configuration()
        print()

        # Mostrar resumen
        sync_summary = get_sync_status_summary()
        print("📊 System Summary:")
        print(f"   • Providers configured: {sync_summary['total_providers']}")
        print(f"   • Active syncs: {sync_summary['active_syncs']}")
        print(f"   • Total records synced: {sync_summary['total_records_synced']}")
        print()
        print("✅ SmartHydro Constants & Sync System initialized successfully!")
        print()
        print("📋 Next steps:")
        print("   1. Configure provider API credentials")
        print("   2. Run initial historical data sync")
        print("   3. Set up monitoring alerts")
        print("   4. Test constant applications")

    except Exception as exc:
        print(f"❌ Initialization failed: {exc}")
        raise


if __name__ == '__main__':
    # Ejecutar inicialización cuando se llame directamente
    initialize_all()
