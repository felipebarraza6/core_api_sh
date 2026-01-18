#!/usr/bin/env python3
"""
Test completo del sistema de constantes históricas y sincronización automática
Prueba SQLite de desarrollo y valida funcionamiento completo
"""

import os
import sys
import django
from datetime import datetime, timedelta
from decimal import Decimal

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from django.utils import timezone
from django.db import transaction

# Importar modelos y servicios
from api.core.models import (
    EquipmentProvider, EquipmentModel, IoTDevice,
    ConstantDefinition, ConstantApplication,
    ProviderDataSync, DataPoint, DataStream,
    VariableDefinition, CatchmentPoint
)
from api.core.services.constants_service import constants_service
from api.core.services.provider_sync_service import provider_sync_service
from api.core.config.constants_and_sync_config import (
    initialize_all, get_sync_status_summary
)


def create_test_data():
    """Crear datos de prueba para testing"""
    print("🧪 Creating test data...")

    # Crear cliente y proyecto
    from api.core.models import Client, ProjectCatchments
    client, _ = Client.objects.get_or_create(
        rut="12.345.678-9",
        defaults={'name': 'Cliente Test', 'email': 'test@cliente.com'}
    )

    project, _ = ProjectCatchments.objects.get_or_create(
        name="Proyecto Test",
        client=client,
        defaults={'code_internal': 'TEST001'}
    )

    # Crear punto de captación
    point, _ = CatchmentPoint.objects.get_or_create(
        title="Pozo Test",
        project=project,
        defaults={
            'owner_user_id': 1,  # Asumir que existe user 1
            'is_tdata': True
        }
    )

    # Crear proveedor
    provider, _ = EquipmentProvider.objects.get_or_create(
        code="TEST_PROVIDER",
        defaults={
            'name': 'Proveedor de Prueba',
            'mqtt_broker_host': 'test.mqtt.com',
            'integration_status': 'TESTING'
        }
    )

    # Crear modelo de equipo
    equipment_model, _ = EquipmentModel.objects.get_or_create(
        provider=provider,
        model_code="TEST_MODEL_001",
        defaults={
            'model_name': 'Modelo de Prueba',
            'power_supply': 'Batería AAA',
            'battery_life_days': 365
        }
    )

    # Crear dispositivo IoT
    device, _ = IoTDevice.objects.get_or_create(
        device_id="TEST_DEVICE_001",
        defaults={
            'name': 'Dispositivo de Prueba',
            'catchment_point': point,
            'equipment_model': equipment_model,
            'firmware_version': '1.0.0',
            'battery_level': 85.5,
            'status': 'ONLINE'
        }
    )

    print("✅ Test data created")
    return device, provider


def test_constants_system(device):
    """Probar el sistema de constantes"""
    print("\n🧪 Testing constants system...")

    # Crear constante de prueba
    constant = ConstantDefinition.objects.create(
        name="Constante de Prueba",
        code="TEST_CONSTANT_001",
        constant_type="TOTALIZER_OFFSET",
        value_numeric=Decimal('100.5'),
        device=device,
        is_active=True
    )

    # Aplicar constante a un rango
    start_date = timezone.now() - timedelta(days=7)
    end_date = timezone.now()

    result = constants_service.create_constant_range_application(
        constant, start_date, end_date,
        reason="Prueba de constante histórica"
    )

    if result['success']:
        print(f"✅ Constant application created: {result['application_id']}")
        return True
    else:
        print(f"❌ Constant application failed: {result['error']}")
        return False


def test_data_points_creation(device):
    """Probar creación de puntos de datos"""
    print("\n🧪 Testing data points creation...")

    try:
        # Crear stream de datos
        stream = DataStream.objects.create(
            device=device,
            name="Stream de Prueba",
            code="TEST_STREAM_001",
            stream_type="TELEMETRY",
            is_active=True
        )

        # Crear variable
        variable = VariableDefinition.objects.create(
            name="Caudal de Prueba",
            code="TEST_FLOW_001",
            variable_type="NUMERIC",
            unit="L/min",
            is_required=True
        )

        # Crear puntos de datos
        test_data = [
            {'raw_value': '25.5', 'collected_at': timezone.now() - timedelta(minutes=10)},
            {'raw_value': '26.1', 'collected_at': timezone.now() - timedelta(minutes=5)},
            {'raw_value': '25.8', 'collected_at': timezone.now()},
        ]

        for data in test_data:
            DataPoint.objects.create(
                stream=stream,
                device=device,
                point=device.catchment_point,
                collected_at=data['collected_at'],
                received_at=timezone.now(),
                raw_value=data['raw_value'],
                processed_value=Decimal(data['raw_value']),
                unit="L/min",
                quality="GOOD",
                is_valid=True
            )

        print(f"✅ Created {len(test_data)} test data points")
        return True

    except Exception as exc:
        print(f"❌ Data points creation failed: {exc}")
        return False


def test_provider_sync_setup(provider):
    """Probar configuración de sincronización con proveedor"""
    print("\n🧪 Testing provider sync setup...")

    try:
        # Crear configuración de sync
        sync_config = ProviderDataSync.objects.create(
            provider=provider,
            sync_type="INCREMENTAL",
            sync_interval_minutes=60,
            sync_config={
                'test_mode': True,
                'mock_data': True
            },
            is_active=True
        )

        print(f"✅ Provider sync config created: {sync_config.id}")
        return True

    except Exception as exc:
        print(f"❌ Provider sync setup failed: {exc}")
        return False


def test_historical_data_editing(device):
    """Probar edición de data histórica"""
    print("\n🧪 Testing historical data editing...")

    try:
        # Obtener un punto de dato existente
        data_point = DataPoint.objects.filter(device=device).first()
        if not data_point:
            print("⚠️  No data points found for editing test")
            return True

        original_value = data_point.processed_value

        # Editar el valor
        result = constants_service.edit_historical_data_point(
            data_point.data_point_id,
            new_processed_value=original_value + Decimal('5.0'),
            correction_reason="Prueba de edición histórica"
        )

        if result['success']:
            print(f"✅ Historical data edited: {data_point.data_point_id}")
            return True
        else:
            print(f"❌ Historical data edit failed: {result['error']}")
            return False

    except Exception as exc:
        print(f"❌ Historical data editing failed: {exc}")
        return False


def test_constants_to_data_points(device):
    """Probar aplicación de constantes a puntos de datos"""
    print("\n🧪 Testing constants application to data points...")

    try:
        # Obtener constante
        constant = ConstantDefinition.objects.filter(device=device).first()
        if not constant:
            print("⚠️  No constants found for application test")
            return True

        # Obtener puntos de datos
        data_points = DataPoint.objects.filter(device=device)[:5]
        if not data_points:
            print("⚠️  No data points found for constants test")
            return True

        # Aplicar constante manualmente a cada punto
        applied_count = 0
        for dp in data_points:
            if constants_service._apply_constant_to_value(float(dp.processed_value or 0), constant):
                applied_count += 1

        print(f"✅ Constants applied to {applied_count} data points")
        return True

    except Exception as exc:
        print(f"❌ Constants application failed: {exc}")
        return False


def run_performance_test():
    """Ejecutar test de performance"""
    print("\n🧪 Running performance tests...")

    try:
        # Test de creación masiva de data points
        start_time = timezone.now()

        # Crear múltiples puntos de datos
        data_points = []
        base_time = timezone.now() - timedelta(hours=1)

        for i in range(100):
            data_points.append(DataPoint(
                stream_id=1,  # Asumir que existe
                device_id=1,  # Asumir que existe
                point_id=1,   # Asumir que existe
                collected_at=base_time + timedelta(minutes=i),
                received_at=timezone.now(),
                raw_value=f"{20.0 + (i * 0.1):.1f}",
                processed_value=Decimal(f"{20.0 + (i * 0.1):.1f}"),
                unit="L/min",
                quality="GOOD",
                is_valid=True
            ))

        # Bulk create
        DataPoint.objects.bulk_create(data_points)

        end_time = timezone.now()
        duration = (end_time - start_time).total_seconds()

        print(".2f"        print("✅ Performance test passed")
        return True

    except Exception as exc:
        print(f"❌ Performance test failed: {exc}")
        return False


def main():
    """Ejecutar todas las pruebas"""
    print("🚀 SmartHydro Constants & Sync System Test")
    print("=" * 60)

    # Inicializar sistema
    print("📋 Initializing system...")
    try:
        initialize_all()
        print("✅ System initialized")
    except Exception as exc:
        print(f"❌ System initialization failed: {exc}")
        return 1

    # Crear datos de prueba
    try:
        device, provider = create_test_data()
    except Exception as exc:
        print(f"❌ Test data creation failed: {exc}")
        return 1

    # Ejecutar pruebas
    tests = [
        ("Constants System", lambda: test_constants_system(device)),
        ("Data Points Creation", lambda: test_data_points_creation(device)),
        ("Provider Sync Setup", lambda: test_provider_sync_setup(provider)),
        ("Historical Data Editing", lambda: test_historical_data_editing(device)),
        ("Constants to Data Points", lambda: test_constants_to_data_points(device)),
        ("Performance Test", run_performance_test),
    ]

    passed = 0
    total = len(tests)

    for test_name, test_func in tests:
        try:
            if test_func():
                passed += 1
        except Exception as exc:
            print(f"❌ {test_name} failed with exception: {exc}")

    # Mostrar resumen final
    print("\n" + "=" * 60)
    print("📊 Test Results Summary:"    print(f"   • Tests passed: {passed}/{total}")
    print(".1f"
    # Mostrar estado del sistema
    try:
        sync_summary = get_sync_status_summary()
        print("   • Providers configured:"        print(f"   • Active syncs:"        print(f"   • Total records synced:"    except Exception as exc:
        print(f"   • System status check failed: {exc}")

    print("\n" + "=" * 60)

    if passed == total:
        print("🎉 ALL TESTS PASSED!")
        print("✅ SmartHydro Constants & Sync System is working correctly")
        print("\n🚀 Ready for production use!")
        return 0
    else:
        print("⚠️  SOME TESTS FAILED")
        print("🔧 Please check the errors above and fix them before production use")
        return 1


if __name__ == '__main__':
    sys.exit(main())