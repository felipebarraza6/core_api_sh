#!/usr/bin/env python3
"""
Migrar puntos Twin al sistema dinámico de proveedores

Este script configura automáticamente los puntos que tienen is_tdata=True
para usar el sistema dinámico en lugar del hardcodeado.
"""

import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import CatchmentPoint
try:
    from api.core.providers.models import TelemetryProvider, CatchmentPointProvider
except ImportError:
    print("❌ Error: Modelos de proveedores no encontrados. Ejecuta las migraciones primero.")
    exit(1)

from api.core.providers import get_provider_manager


def migrate_twin_points():
    """Migrar puntos twin al sistema dinámico"""

    print("🔄 MIGRACIÓN: Puntos Twin → Sistema Dinámico")
    print("=" * 50)

    # Verificar que existen los proveedores
    manager = get_provider_manager()
    providers = {
        'twin': manager.get_provider('twin'),
        'nettra': manager.get_provider('nettra')
    }

    missing_providers = [name for name, provider in providers.items() if not provider]
    if missing_providers:
        print(f"❌ Faltan proveedores: {missing_providers}")
        print("Ejecuta: python3 create_sample_providers.py")
        return

    # Obtener puntos twin
    twin_points = CatchmentPoint.objects.filter(is_tdata=True).prefetch_related(
        'schemes__variables'
    )

    print(f"📊 Encontrados {twin_points.count()} puntos con is_tdata=True")

    migrated_count = 0
    skipped_count = 0

    for point in twin_points:
        print(f"\n🔄 Procesando punto {point.id}: {point.title}")

        # Verificar si ya tiene configuración dinámica
        existing_configs = CatchmentPointProvider.objects.filter(point=point)
        if existing_configs.exists():
            print(f"   ⚠️ Ya tiene {existing_configs.count()} configuraciones dinámicas")
            skipped_count += 1
            continue

        # Analizar las variables del punto para determinar qué proveedores necesita
        try:
            schemes = point.schemes.all()
            if not schemes.exists():
                print("   ⚠️ No tiene esquemas asociados")
                skipped_count += 1
                continue

            # Obtener las variables de todos los esquemas
            variables_by_service = {}
            for scheme in schemes:
                for var in scheme.variables.all():
                    service = var.service or 'TWIN'  # Default para Twin
                    if service not in variables_by_service:
                        variables_by_service[service] = []
                    variables_by_service[service].append(var)

            print(f"   📋 Servicios encontrados: {list(variables_by_service.keys())}")

            # Mapear servicios a proveedores y crear configuraciones
            service_to_provider = {
                'TWIN': 'twin',
                'NETTRA': 'nettra',
                'THETHINGS': 'nettra',
                'NOVUS': 'nettra'
            }

            configs_created = 0
            for service, variables in variables_by_service.items():
                provider_name = service_to_provider.get(service)
                if not provider_name:
                    print(f"   ⚠️ Servicio '{service}' no soportado, saltando")
                    continue

                # Usar el token de la primera variable como point_code
                first_var = variables[0]
                point_code = first_var.token_service or f"point_{point.id}"

                # Crear configuración dinámica
                try:
                    config = manager.create_provider_config(
                        point_id=point.id,
                        provider_name=provider_name,
                        config={
                            'point_code': point_code,
                            'config_override': {},
                            'device_config': {
                                'migrated_from': service,
                                'variables_count': len(variables),
                                'variable_names': [v.str_variable for v in variables]
                            },
                            'priority': 1 if service == 'TWIN' else 2  # Twin primero
                        }
                    )
                    print(f"   ✅ Creada config para {provider_name}: {point_code}")
                    configs_created += 1

                except Exception as e:
                    print(f"   ❌ Error creando config para {provider_name}: {e}")

            if configs_created > 0:
                migrated_count += 1
                print(f"   🎉 Punto migrado exitosamente ({configs_created} configs)")
            else:
                print("   ⚠️ No se pudieron crear configuraciones")
        except Exception as e:
            print(f"   ❌ Error procesando punto: {e}")
            skipped_count += 1

    print("\n📊 RESUMEN DE MIGRACIÓN")
    print("=" * 50)
    print(f"✅ Puntos migrados: {migrated_count}")
    print(f"⚠️ Puntos omitidos: {skipped_count}")
    print(f"📈 Total procesados: {twin_points.count()}")

    if migrated_count > 0:
        print("\n🚀 PRUEBA EL SISTEMA DINÁMICO")
        print("Ahora puedes ejecutar:")
        print("python3 api/cronjobs/telemetry/twin_dynamic.py")
        print()
        print("O reemplazar en el cronjob:")
        print("from .twin_dynamic import run as run_twin_dynamic")

    return migrated_count


def test_dynamic_twin():
    """Probar el sistema dinámico con un punto twin"""

    print("\n🧪 TESTING: Sistema Dinámico Twin")
    print("=" * 50)

    # Obtener un punto twin migrado
    points_with_config = CatchmentPointProvider.objects.filter(
        point__is_tdata=True
    ).values_list('point_id', flat=True).distinct()

    if not points_with_config:
        print("❌ No hay puntos twin migrados para probar")
        return

    point_id = points_with_config[0]
    print(f"📍 Probando con punto {point_id}")

    # Importar y ejecutar la función dinámica
    try:
        from api.cronjobs.telemetry.twin_dynamic import get_data_with_retry_dynamic

        # Probar con una variable de ejemplo
        result = get_data_with_retry_dynamic(
            point_id=point_id,
            provider_name='twin',  # Probar con twin
            variable_name='caudal'   # Variable de ejemplo
        )

        if result:
            print("✅ Sistema dinámico funcionando:")
            print(f"   Valor: {result.get('value')}")
            print(f"   Timestamp: {result.get('date_time')}")
        else:
            print("⚠️ Sistema dinámico retornó None (esperado con tokens demo)")

    except Exception as e:
        print(f"❌ Error en testing: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # Migrar puntos
    migrated = migrate_twin_points()

    # Si se migraron puntos, probar el sistema
    if migrated > 0:
        test_dynamic_twin()

    print("\n🎯 PRÓXIMOS PASOS:")
    print("1. Probar el cronjob dinámico: python3 api/cronjobs/telemetry/twin_dynamic.py")
    print("2. Si funciona, reemplazar twin.py con twin_dynamic.py")
    print("3. Repetir proceso con otros cronjobs (nettra.py, etc.)")
    print("4. Una vez probado, eliminar archivos getters/ (ya hecho)")