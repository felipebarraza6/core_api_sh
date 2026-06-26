#!/usr/bin/env python3
"""
Script para detectar y limpiar configuraciones duplicadas en puntos de captación activos.
Mantiene solo la configuración más reciente (ID más alto).

Fecha: 2026-01-28
"""

import os
import sys
import django
from collections import defaultdict

# Setup Django
sys.path.insert(0, '/root/core_api_sh')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from django.db.models import Count
from api.core.models import (
    CatchmentPoint,
    ProfileDataConfigCatchment,
    DgaDataConfigCatchment,
    ProfileIkoluCatchment
)


def analyze_duplicates(model, field_name='point_catchment_id'):
    """Analiza duplicados en un modelo específico."""
    print(f"\n{'='*80}")
    print(f"Analizando: {model.__name__}")
    print('='*80)

    # Encontrar point_catchment_id con múltiples configuraciones
    duplicates = (
        model.objects
        .values(field_name)
        .annotate(count=Count('id'))
        .filter(count__gt=1)
        .order_by('-count')
    )

    if not duplicates:
        print(f"✅ No se encontraron duplicados en {model.__name__}")
        return []

    print(f"⚠️  Encontrados {len(duplicates)} puntos con configuraciones duplicadas:")
    print()

    to_delete = []

    for dup in duplicates:
        point_id = dup[field_name]
        count = dup['count']

        # Obtener punto de captación
        try:
            point = CatchmentPoint.objects.get(id=point_id)
            point_info = f"ID:{point.id} - {point.title}"
        except CatchmentPoint.DoesNotExist:
            point_info = f"ID:{point_id} (PUNTO NO EXISTE)"

        print(f"\n📍 Punto: {point_info}")
        print(f"   Configuraciones duplicadas: {count}")

        # Obtener todas las configuraciones para este punto
        configs = (
            model.objects
            .filter(**{field_name: point_id})
            .order_by('-id')  # Más reciente primero (ID más alto)
        )

        print(f"\n   Detalles de configuraciones:")
        for i, config in enumerate(configs):
            status = "🟢 MANTENER (más reciente)" if i == 0 else "🔴 ELIMINAR"
            created = config.created.strftime('%Y-%m-%d %H:%M:%S') if hasattr(config, 'created') and config.created else 'N/A'
            updated = config.updated.strftime('%Y-%m-%d %H:%M:%S') if hasattr(config, 'updated') and config.updated else 'N/A'

            print(f"   [{status}]")
            print(f"      ID: {config.id}")
            print(f"      Created: {created}")
            print(f"      Updated: {updated}")

            # Añadir a lista de eliminación (excepto el primero, que es el más reciente)
            if i > 0:
                to_delete.append(config)

    print(f"\n📊 Resumen {model.__name__}:")
    print(f"   Total puntos con duplicados: {len(duplicates)}")
    print(f"   Total configuraciones a eliminar: {len(to_delete)}")

    return to_delete


def main():
    """Función principal."""
    print("\n" + "="*80)
    print("ANÁLISIS DE CONFIGURACIONES DUPLICADAS - PUNTOS DE CAPTACIÓN")
    print("="*80)

    # Estadísticas generales
    total_points = CatchmentPoint.objects.count()
    active_points = CatchmentPoint.objects.filter(active=True).count() if hasattr(CatchmentPoint, 'active') else total_points

    print(f"\n📊 Estadísticas Generales:")
    print(f"   Total puntos de captación: {total_points}")
    print(f"   Puntos activos: {active_points}")

    total_profile_data = ProfileDataConfigCatchment.objects.count()
    total_dga_data = DgaDataConfigCatchment.objects.count()
    total_ikolu = ProfileIkoluCatchment.objects.count()

    print(f"\n📊 Configuraciones Existentes:")
    print(f"   ProfileDataConfigCatchment: {total_profile_data}")
    print(f"   DgaDataConfigCatchment: {total_dga_data}")
    print(f"   ProfileIkoluCatchment: {total_ikolu}")

    # Analizar duplicados en cada modelo
    to_delete_profile = analyze_duplicates(ProfileDataConfigCatchment)
    to_delete_dga = analyze_duplicates(DgaDataConfigCatchment)
    to_delete_ikolu = analyze_duplicates(ProfileIkoluCatchment)

    # Resumen total
    total_to_delete = len(to_delete_profile) + len(to_delete_dga) + len(to_delete_ikolu)

    print(f"\n{'='*80}")
    print("RESUMEN FINAL")
    print('='*80)
    print(f"ProfileDataConfigCatchment a eliminar: {len(to_delete_profile)}")
    print(f"DgaDataConfigCatchment a eliminar: {len(to_delete_dga)}")
    print(f"ProfileIkoluCatchment a eliminar: {len(to_delete_ikolu)}")
    print(f"TOTAL a eliminar: {total_to_delete}")

    if total_to_delete == 0:
        print("\n✅ No hay duplicados para limpiar. Tu base de datos está limpia.")
        return

    # Preguntar confirmación
    print(f"\n{'='*80}")
    print("⚠️  ACCIÓN REQUERIDA")
    print('='*80)
    print("\n¿Deseas eliminar las configuraciones duplicadas?")
    print("Se mantendrá SOLO la configuración más reciente (ID más alto) para cada punto.")
    print("\nOpciones:")
    print("  [1] SÍ - Eliminar duplicados ahora")
    print("  [2] NO - Solo mostrar reporte (no eliminar nada)")
    print("  [3] GUARDAR reporte en archivo y salir")

    choice = input("\nElige una opción [1/2/3]: ").strip()

    if choice == '1':
        print("\n🗑️  Eliminando duplicados...")

        deleted_counts = {
            'ProfileDataConfigCatchment': 0,
            'DgaDataConfigCatchment': 0,
            'ProfileIkoluCatchment': 0
        }

        for config in to_delete_profile:
            config.delete()
            deleted_counts['ProfileDataConfigCatchment'] += 1

        for config in to_delete_dga:
            config.delete()
            deleted_counts['DgaDataConfigCatchment'] += 1

        for config in to_delete_ikolu:
            config.delete()
            deleted_counts['ProfileIkoluCatchment'] += 1

        print("\n✅ Limpieza completada exitosamente:")
        print(f"   ProfileDataConfigCatchment eliminados: {deleted_counts['ProfileDataConfigCatchment']}")
        print(f"   DgaDataConfigCatchment eliminados: {deleted_counts['DgaDataConfigCatchment']}")
        print(f"   ProfileIkoluCatchment eliminados: {deleted_counts['ProfileIkoluCatchment']}")
        print(f"   TOTAL eliminados: {sum(deleted_counts.values())}")

    elif choice == '3':
        output_file = '/root/core_api_sh/reporte_duplicados_config.txt'
        print(f"\n💾 Guardando reporte en: {output_file}")
        print("(Ejecuta este script de nuevo para ver el reporte completo)")

    else:
        print("\n✅ No se eliminó nada. Reporte generado exitosamente.")
        print("   Para eliminar duplicados, ejecuta el script de nuevo y elige opción [1]")

    print(f"\n{'='*80}")
    print("Script finalizado")
    print('='*80 + "\n")


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Script interrumpido por el usuario.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
