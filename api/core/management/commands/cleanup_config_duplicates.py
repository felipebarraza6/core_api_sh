"""
Management command para detectar y limpiar configuraciones duplicadas en puntos de captación.
Mantiene solo la configuración más reciente (ID más alto).

Uso:
    python manage.py cleanup_config_duplicates           # Solo análisis
    python manage.py cleanup_config_duplicates --delete  # Eliminar duplicados
"""

from django.core.management.base import BaseCommand
from django.db.models import Count
from collections import defaultdict

from api.core.models import (
    CatchmentPoint,
    ProfileDataConfigCatchment,
    DgaDataConfigCatchment,
    ProfileIkoluCatchment
)


class Command(BaseCommand):
    help = 'Detecta y limpia configuraciones duplicadas en puntos de captación'

    def add_arguments(self, parser):
        parser.add_argument(
            '--delete',
            action='store_true',
            help='Eliminar duplicados (mantener solo el más reciente)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simular eliminación sin hacer cambios',
        )

    def analyze_duplicates(self, model, field_name='point_catchment_id'):
        """Analiza duplicados en un modelo específico."""
        self.stdout.write(f"\n{'='*80}")
        self.stdout.write(f"Analizando: {model.__name__}")
        self.stdout.write('='*80)

        # Encontrar point_catchment_id con múltiples configuraciones
        duplicates = (
            model.objects
            .values(field_name)
            .annotate(count=Count('id'))
            .filter(count__gt=1)
            .order_by('-count')
        )

        if not duplicates:
            self.stdout.write(self.style.SUCCESS(
                f"✅ No se encontraron duplicados en {model.__name__}"
            ))
            return []

        self.stdout.write(self.style.WARNING(
            f"⚠️  Encontrados {len(duplicates)} puntos con configuraciones duplicadas:"
        ))
        self.stdout.write("")

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

            self.stdout.write(f"\n📍 Punto: {point_info}")
            self.stdout.write(f"   Configuraciones duplicadas: {count}")

            # Obtener todas las configuraciones para este punto
            configs = (
                model.objects
                .filter(**{field_name: point_id})
                .order_by('-id')  # Más reciente primero (ID más alto)
            )

            self.stdout.write(f"\n   Detalles de configuraciones:")
            for i, config in enumerate(configs):
                status = "🟢 MANTENER (más reciente)" if i == 0 else "🔴 ELIMINAR"
                created = config.created.strftime('%Y-%m-%d %H:%M:%S') if hasattr(config, 'created') and config.created else 'N/A'
                updated = config.updated.strftime('%Y-%m-%d %H:%M:%S') if hasattr(config, 'updated') and config.updated else 'N/A'

                self.stdout.write(f"   [{status}]")
                self.stdout.write(f"      ID: {config.id}")
                self.stdout.write(f"      Created: {created}")
                self.stdout.write(f"      Updated: {updated}")

                # Añadir a lista de eliminación (excepto el primero)
                if i > 0:
                    to_delete.append(config)

        self.stdout.write(f"\n📊 Resumen {model.__name__}:")
        self.stdout.write(f"   Total puntos con duplicados: {len(duplicates)}")
        self.stdout.write(f"   Total configuraciones a eliminar: {len(to_delete)}")

        return to_delete

    def handle(self, *args, **options):
        """Ejecuta el comando."""
        self.stdout.write("\n" + "="*80)
        self.stdout.write("ANÁLISIS DE CONFIGURACIONES DUPLICADAS - PUNTOS DE CAPTACIÓN")
        self.stdout.write("="*80)

        # Estadísticas generales
        total_points = CatchmentPoint.objects.count()

        self.stdout.write(f"\n📊 Estadísticas Generales:")
        self.stdout.write(f"   Total puntos de captación: {total_points}")

        total_profile_data = ProfileDataConfigCatchment.objects.count()
        total_dga_data = DgaDataConfigCatchment.objects.count()
        total_ikolu = ProfileIkoluCatchment.objects.count()

        self.stdout.write(f"\n📊 Configuraciones Existentes:")
        self.stdout.write(f"   ProfileDataConfigCatchment: {total_profile_data}")
        self.stdout.write(f"   DgaDataConfigCatchment: {total_dga_data}")
        self.stdout.write(f"   ProfileIkoluCatchment: {total_ikolu}")

        # Analizar duplicados en cada modelo
        to_delete_profile = self.analyze_duplicates(ProfileDataConfigCatchment)
        to_delete_dga = self.analyze_duplicates(DgaDataConfigCatchment)
        to_delete_ikolu = self.analyze_duplicates(ProfileIkoluCatchment)

        # Resumen total
        total_to_delete = len(to_delete_profile) + len(to_delete_dga) + len(to_delete_ikolu)

        self.stdout.write(f"\n{'='*80}")
        self.stdout.write("RESUMEN FINAL")
        self.stdout.write('='*80)
        self.stdout.write(f"ProfileDataConfigCatchment a eliminar: {len(to_delete_profile)}")
        self.stdout.write(f"DgaDataConfigCatchment a eliminar: {len(to_delete_dga)}")
        self.stdout.write(f"ProfileIkoluCatchment a eliminar: {len(to_delete_ikolu)}")
        self.stdout.write(f"TOTAL a eliminar: {total_to_delete}")

        if total_to_delete == 0:
            self.stdout.write(self.style.SUCCESS(
                "\n✅ No hay duplicados para limpiar. Tu base de datos está limpia."
            ))
            return

        # Si se especificó --delete, eliminar
        if options['delete']:
            if options['dry_run']:
                self.stdout.write(self.style.WARNING(
                    "\n🔍 Modo DRY-RUN: No se eliminará nada (simulación)"
                ))
            else:
                self.stdout.write(self.style.WARNING(
                    "\n🗑️  Eliminando duplicados..."
                ))

            deleted_counts = {
                'ProfileDataConfigCatchment': 0,
                'DgaDataConfigCatchment': 0,
                'ProfileIkoluCatchment': 0
            }

            if not options['dry_run']:
                for config in to_delete_profile:
                    config.delete()
                    deleted_counts['ProfileDataConfigCatchment'] += 1

                for config in to_delete_dga:
                    config.delete()
                    deleted_counts['DgaDataConfigCatchment'] += 1

                for config in to_delete_ikolu:
                    config.delete()
                    deleted_counts['ProfileIkoluCatchment'] += 1

                self.stdout.write(self.style.SUCCESS("\n✅ Limpieza completada exitosamente:"))
                self.stdout.write(f"   ProfileDataConfigCatchment eliminados: {deleted_counts['ProfileDataConfigCatchment']}")
                self.stdout.write(f"   DgaDataConfigCatchment eliminados: {deleted_counts['DgaDataConfigCatchment']}")
                self.stdout.write(f"   ProfileIkoluCatchment eliminados: {deleted_counts['ProfileIkoluCatchment']}")
                self.stdout.write(f"   TOTAL eliminados: {sum(deleted_counts.values())}")
            else:
                self.stdout.write(self.style.SUCCESS("\n✅ Simulación completada (no se eliminó nada)"))
                self.stdout.write(f"   Se habrían eliminado {total_to_delete} configuraciones duplicadas")

        else:
            self.stdout.write(self.style.WARNING(
                "\n⚠️  Para eliminar los duplicados, ejecuta:"
            ))
            self.stdout.write("   python manage.py cleanup_config_duplicates --delete")
            self.stdout.write("\n   O para simular sin cambios:")
            self.stdout.write("   python manage.py cleanup_config_duplicates --delete --dry-run")

        self.stdout.write(f"\n{'='*80}")
        self.stdout.write("Script finalizado")
        self.stdout.write('='*80 + "\n")
