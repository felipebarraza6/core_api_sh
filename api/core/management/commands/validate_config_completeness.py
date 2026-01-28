"""
Management command para validar que todos los puntos activos tengan configuraciones completas.

Valida:
- Que cada punto activo tenga ProfileDataConfigCatchment
- Que cada punto activo tenga DgaDataConfigCatchment
- Que cada punto activo tenga ProfileIkoluCatchment
- Detecta configuraciones huérfanas (sin punto asociado)

Uso:
    python manage.py validate_config_completeness
    python manage.py validate_config_completeness --fix  # Crear configuraciones faltantes
"""

from django.core.management.base import BaseCommand
from api.core.models import (
    CatchmentPoint,
    ProfileDataConfigCatchment,
    DgaDataConfigCatchment,
    ProfileIkoluCatchment
)


class Command(BaseCommand):
    help = 'Valida que todos los puntos activos tengan configuraciones completas'

    def add_arguments(self, parser):
        parser.add_argument(
            '--fix',
            action='store_true',
            help='Crear configuraciones faltantes automáticamente',
        )
        parser.add_argument(
            '--include-inactive',
            action='store_true',
            help='Incluir puntos inactivos en el análisis',
        )

    def handle(self, *args, **options):
        """Ejecuta el comando."""
        self.stdout.write("\n" + "="*80)
        self.stdout.write("VALIDACIÓN DE CONFIGURACIONES - PUNTOS DE CAPTACIÓN")
        self.stdout.write("="*80)

        # Obtener puntos a analizar
        if options['include_inactive']:
            points = CatchmentPoint.objects.all()
            self.stdout.write("\n🔍 Analizando TODOS los puntos (incluidos inactivos)")
        else:
            # Por defecto, analizar todos los puntos (no hay campo 'active' en el modelo)
            points = CatchmentPoint.objects.all()
            self.stdout.write("\n🔍 Analizando todos los puntos de captación")

        total_points = points.count()
        self.stdout.write(f"   Total puntos a analizar: {total_points}")

        # Contar configuraciones existentes
        total_profile_data = ProfileDataConfigCatchment.objects.count()
        total_dga_data = DgaDataConfigCatchment.objects.count()
        total_ikolu = ProfileIkoluCatchment.objects.count()

        self.stdout.write(f"\n📊 Configuraciones Existentes:")
        self.stdout.write(f"   ProfileDataConfigCatchment: {total_profile_data}")
        self.stdout.write(f"   DgaDataConfigCatchment: {total_dga_data}")
        self.stdout.write(f"   ProfileIkoluCatchment: {total_ikolu}")

        # Validar cada punto
        missing_profile_data = []
        missing_dga_data = []
        missing_ikolu = []

        self.stdout.write(f"\n{'='*80}")
        self.stdout.write("ANÁLISIS DETALLADO")
        self.stdout.write('='*80)

        for point in points:
            issues = []

            # Verificar ProfileDataConfigCatchment
            if not ProfileDataConfigCatchment.objects.filter(point_catchment=point).exists():
                issues.append("❌ Sin ProfileDataConfigCatchment")
                missing_profile_data.append(point)

            # Verificar DgaDataConfigCatchment
            if not DgaDataConfigCatchment.objects.filter(point_catchment=point).exists():
                issues.append("❌ Sin DgaDataConfigCatchment")
                missing_dga_data.append(point)

            # Verificar ProfileIkoluCatchment
            if not ProfileIkoluCatchment.objects.filter(point_catchment=point).exists():
                issues.append("❌ Sin ProfileIkoluCatchment")
                missing_ikolu.append(point)

            # Mostrar solo puntos con problemas
            if issues:
                self.stdout.write(f"\n⚠️  Punto ID:{point.id} - {point.title}")
                for issue in issues:
                    self.stdout.write(f"   {issue}")

        # Buscar configuraciones huérfanas
        self.stdout.write(f"\n{'='*80}")
        self.stdout.write("CONFIGURACIONES HUÉRFANAS (sin punto asociado)")
        self.stdout.write('='*80)

        orphan_profile = ProfileDataConfigCatchment.objects.filter(point_catchment__isnull=True)
        orphan_dga = DgaDataConfigCatchment.objects.filter(point_catchment__isnull=True)
        orphan_ikolu = ProfileIkoluCatchment.objects.filter(point_catchment__isnull=True)

        if orphan_profile.exists():
            self.stdout.write(self.style.WARNING(
                f"\n⚠️  ProfileDataConfigCatchment huérfanos: {orphan_profile.count()}"
            ))
            for config in orphan_profile[:5]:  # Mostrar solo los primeros 5
                self.stdout.write(f"   ID: {config.id}")

        if orphan_dga.exists():
            self.stdout.write(self.style.WARNING(
                f"\n⚠️  DgaDataConfigCatchment huérfanos: {orphan_dga.count()}"
            ))
            for config in orphan_dga[:5]:
                self.stdout.write(f"   ID: {config.id}")

        if orphan_ikolu.exists():
            self.stdout.write(self.style.WARNING(
                f"\n⚠️  ProfileIkoluCatchment huérfanos: {orphan_ikolu.count()}"
            ))
            for config in orphan_ikolu[:5]:
                self.stdout.write(f"   ID: {config.id}")

        if not orphan_profile.exists() and not orphan_dga.exists() and not orphan_ikolu.exists():
            self.stdout.write(self.style.SUCCESS("✅ No hay configuraciones huérfanas"))

        # Resumen
        self.stdout.write(f"\n{'='*80}")
        self.stdout.write("RESUMEN")
        self.stdout.write('='*80)
        self.stdout.write(f"Puntos sin ProfileDataConfigCatchment: {len(missing_profile_data)}")
        self.stdout.write(f"Puntos sin DgaDataConfigCatchment: {len(missing_dga_data)}")
        self.stdout.write(f"Puntos sin ProfileIkoluCatchment: {len(missing_ikolu)}")

        total_issues = len(missing_profile_data) + len(missing_dga_data) + len(missing_ikolu)

        if total_issues == 0:
            self.stdout.write(self.style.SUCCESS(
                "\n✅ Todos los puntos tienen sus configuraciones completas"
            ))
        else:
            self.stdout.write(self.style.WARNING(
                f"\n⚠️  Total de configuraciones faltantes: {total_issues}"
            ))

            if options['fix']:
                self.stdout.write(self.style.WARNING("\n🔧 Creando configuraciones faltantes..."))

                created_counts = {
                    'ProfileDataConfigCatchment': 0,
                    'DgaDataConfigCatchment': 0,
                    'ProfileIkoluCatchment': 0
                }

                # Crear ProfileDataConfigCatchment faltantes
                for point in missing_profile_data:
                    ProfileDataConfigCatchment.objects.create(
                        point_catchment=point,
                        is_telemetry=True,
                        d1=0.0,
                        d2=0.0,
                        d3=0.0,
                        d4=0.0,
                        d5=0.0,
                        d6=0
                    )
                    created_counts['ProfileDataConfigCatchment'] += 1

                # Crear DgaDataConfigCatchment faltantes
                for point in missing_dga_data:
                    DgaDataConfigCatchment.objects.create(
                        point_catchment=point,
                        send_dga=False,
                        standard='SIN_ESTANDAR',
                        type_dga='SUBTERRANEO'
                    )
                    created_counts['DgaDataConfigCatchment'] += 1

                # Crear ProfileIkoluCatchment faltantes
                for point in missing_ikolu:
                    ProfileIkoluCatchment.objects.create(
                        point_catchment=point,
                        entry_by_form=False,
                        m1=True,
                        m2=False,
                        m3=False,
                        m4=False
                    )
                    created_counts['ProfileIkoluCatchment'] += 1

                self.stdout.write(self.style.SUCCESS("\n✅ Configuraciones creadas exitosamente:"))
                self.stdout.write(f"   ProfileDataConfigCatchment: {created_counts['ProfileDataConfigCatchment']}")
                self.stdout.write(f"   DgaDataConfigCatchment: {created_counts['DgaDataConfigCatchment']}")
                self.stdout.write(f"   ProfileIkoluCatchment: {created_counts['ProfileIkoluCatchment']}")
                self.stdout.write(f"   TOTAL: {sum(created_counts.values())}")

            else:
                self.stdout.write(self.style.WARNING(
                    "\n⚠️  Para crear las configuraciones faltantes, ejecuta:"
                ))
                self.stdout.write("   python manage.py validate_config_completeness --fix")

        self.stdout.write(f"\n{'='*80}")
        self.stdout.write("Validación finalizada")
        self.stdout.write('='*80 + "\n")
