"""
Comando de migración al sistema 100% dinámico.

Inicializa:
- ConfigurationScheme con esquemas por defecto
- SamplingFrequency con frecuencias estándar
- VariableType con tipos de variables comunes
- Migra datos existentes de ProfileDataConfigCatchment a PointConfigurationValue
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from api.telemetry.models import (
    ConfigurationScheme,
    ConfigurationSchemeField,
    SamplingFrequency,
    VariableType,
    CatchmentPoint,
    ProfileDataConfigCatchment,
    PointConfigurationValue,
)


class Command(BaseCommand):
    help = 'Migra el sistema a arquitectura 100% dinámica'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simular sin guardar cambios',
        )
        parser.add_argument(
            '--skip-data-migration',
            action='store_true',
            help='Solo crear esquemas, no migrar datos existentes',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        skip_data = options['skip_data_migration']

        self.stdout.write(self.style.SUCCESS('🚀 Iniciando migración al sistema dinámico...'))

        with transaction.atomic():
            # 1. Crear esquemas de configuración
            self.stdout.write('\n📋 Creando esquemas de configuración...')
            schemes_created = self.create_configuration_schemes(dry_run)

            # 2. Crear frecuencias de muestreo
            self.stdout.write('\n⏱️  Creando frecuencias de muestreo...')
            frequencies_created = self.create_sampling_frequencies(dry_run)

            # 3. Crear tipos de variables
            self.stdout.write('\n🔧 Creando tipos de variables...')
            types_created = self.create_variable_types(dry_run)

            # 4. Migrar datos existentes
            if not skip_data:
                self.stdout.write('\n📦 Migrando datos existentes...')
                migrated_points = self.migrate_existing_data(dry_run)
            else:
                migrated_points = 0

            if dry_run:
                self.stdout.write(self.style.WARNING('\n⚠️  DRY RUN - No se guardaron cambios'))
                transaction.set_rollback(True)
            else:
                self.stdout.write(self.style.SUCCESS('\n✅ Migración completada exitosamente'))

        # Resumen
        self.stdout.write('\n' + '='*60)
        self.stdout.write('RESUMEN:')
        self.stdout.write(f'  - Esquemas creados: {schemes_created}')
        self.stdout.write(f'  - Frecuencias creadas: {frequencies_created}')
        self.stdout.write(f'  - Tipos de variables creados: {types_created}')
        if not skip_data:
            self.stdout.write(f'  - Puntos migrados: {migrated_points}')
        self.stdout.write('='*60)

    def create_configuration_schemes(self, dry_run=False):
        """Crear esquemas de configuración por defecto."""
        schemes_data = [
            {
                'code': 'pozo_subterraneo_std',
                'name': 'Pozo Subterráneo Estándar',
                'category': 'subterraneo',
                'description': 'Esquema estándar para pozos subterráneos con nivel y totalizado',
                'fields': [
                    {'code': 'd1', 'name': 'Profundidad', 'unit': 'mt', 'data_type': 'decimal', 'display_order': 1},
                    {'code': 'd2', 'name': 'Posicionamiento bomba', 'unit': 'mt', 'data_type': 'decimal', 'display_order': 2},
                    {'code': 'd3', 'name': 'Posicionamiento nivel', 'unit': 'mt', 'data_type': 'decimal', 'is_required': True, 'display_order': 3},
                    {'code': 'd4', 'name': 'Diámetro ducto salida', 'unit': 'pulg', 'data_type': 'decimal', 'display_order': 4},
                    {'code': 'd5', 'name': 'Diámetro flujómetro', 'unit': 'pulg', 'data_type': 'decimal', 'display_order': 5},
                    {'code': 'd6', 'name': 'Caudalímetro inicial', 'unit': '', 'data_type': 'integer', 'display_order': 6},
                    {'code': 'addition', 'name': 'Adición (Reset)', 'unit': 'm3', 'data_type': 'integer', 'default_value': 0, 'display_order': 7},
                    {'code': 'pulses_factor', 'name': 'Factor de pulsos', 'unit': 'pulsos/m3', 'data_type': 'integer', 'default_value': 1000, 'display_order': 8},
                ]
            },
            {
                'code': 'sensor_simple',
                'name': 'Sensor Simple (Solo Caudal)',
                'category': 'simple',
                'description': 'Esquema mínimo para sensores que solo miden caudal',
                'fields': [
                    {'code': 'scale_factor', 'name': 'Factor de escala', 'data_type': 'decimal', 'default_value': 1.0, 'display_order': 1},
                ]
            },
            {
                'code': 'agua_superficial',
                'name': 'Agua Superficial',
                'category': 'superficial',
                'description': 'Esquema para puntos de agua superficial',
                'fields': [
                    {'code': 'area_seccion', 'name': 'Área de sección', 'unit': 'm2', 'data_type': 'decimal', 'display_order': 1},
                    {'code': 'coef_rugosidad', 'name': 'Coeficiente de rugosidad', 'data_type': 'decimal', 'default_value': 0.03, 'display_order': 2},
                    {'code': 'pendiente', 'name': 'Pendiente del canal', 'unit': '%', 'data_type': 'decimal', 'display_order': 3},
                ]
            },
        ]

        created = 0
        for scheme_data in schemes_data:
            fields_data = scheme_data.pop('fields')
            
            if dry_run:
                self.stdout.write(f'  [DRY RUN] Crearía esquema: {scheme_data["name"]}')
                created += 1
                continue

            scheme, _ = ConfigurationScheme.objects.get_or_create(
                code=scheme_data['code'],
                defaults=scheme_data
            )
            
            if _:
                self.stdout.write(f'  ✅ Creado: {scheme.name}')
                created += 1
            else:
                self.stdout.write(f'  ⏭️  Ya existe: {scheme.name}')

            # Crear campos del esquema
            for field_data in fields_data:
                ConfigurationSchemeField.objects.get_or_create(
                    scheme=scheme,
                    code=field_data['code'],
                    defaults=field_data
                )

        return created

    def create_sampling_frequencies(self, dry_run=False):
        """Crear frecuencias de muestreo por defecto."""
        frequencies_data = [
            {'code': '1', 'name': '1 minuto', 'minutes': 1, 'cron_expression': '* * * * *', 'display_order': 1},
            {'code': '5', 'name': '5 minutos', 'minutes': 5, 'cron_expression': '*/5 * * * *', 'display_order': 2},
            {'code': '10', 'name': '10 minutos', 'minutes': 10, 'cron_expression': '*/10 * * * *', 'display_order': 3},
            {'code': '15', 'name': '15 minutos', 'minutes': 15, 'cron_expression': '*/15 * * * *', 'display_order': 4},
            {'code': '30', 'name': '30 minutos', 'minutes': 30, 'cron_expression': '*/30 * * * *', 'display_order': 5},
            {'code': '60', 'name': '1 hora', 'minutes': 60, 'cron_expression': '0 * * * *', 'display_order': 6},
        ]

        created = 0
        for freq_data in frequencies_data:
            if dry_run:
                self.stdout.write(f'  [DRY RUN] Crearía frecuencia: {freq_data["name"]}')
                created += 1
                continue

            freq, _ = SamplingFrequency.objects.get_or_create(
                code=freq_data['code'],
                defaults=freq_data
            )
            
            if _:
                self.stdout.write(f'  ✅ Creado: {freq.name}')
                created += 1
            else:
                self.stdout.write(f'  ⏭️  Ya existe: {freq.name}')

        return created

    def create_variable_types(self, dry_run=False):
        """Crear tipos de variables por defecto."""
        types_data = [
            {
                'code': 'TOTALIZADO',
                'name': 'Totalizado (Pulsos)',
                'description': 'Variable calculada desde pulsos del sensor',
                'default_formula': '({pulses} * {config.pulses_factor}) / 1000 + {config.addition}',
                'required_inputs': ['pulses'],
                'default_unit': 'm3'
            },
            {
                'code': 'NIVEL',
                'name': 'Nivel Freático',
                'description': 'Nivel freático calculado desde sensor de nivel',
                'default_formula': '{config.d3} - {raw_nivel}',
                'required_inputs': ['raw_nivel'],
                'default_unit': 'mt'
            },
            {
                'code': 'CAUDAL',
                'name': 'Caudal Instantáneo',
                'description': 'Caudal instantáneo del sensor',
                'default_formula': '{raw_flow}',
                'required_inputs': ['raw_flow'],
                'default_unit': 'L/s'
            },
            {
                'code': 'CAUDAL_PROMEDIO',
                'name': 'Caudal Promedio',
                'description': 'Caudal promedio calculado desde diferencia de totalizado',
                'default_formula': '(({total} - {prev.total}) / {time.diff_seconds}) * 1000',
                'required_inputs': ['total'],
                'default_unit': 'L/s'
            },
            {
                'code': 'GENERICO',
                'name': 'Valor Genérico',
                'description': 'Variable genérica sin procesamiento especial',
                'default_formula': '{raw_value} * {config.scale_factor}',
                'required_inputs': ['raw_value'],
                'default_unit': ''
            },
        ]

        created = 0
        for type_data in types_data:
            if dry_run:
                self.stdout.write(f'  [DRY RUN] Crearía tipo: {type_data["name"]}')
                created += 1
                continue

            var_type, _ = VariableType.objects.get_or_create(
                code=type_data['code'],
                defaults=type_data
            )
            
            if _:
                self.stdout.write(f'  ✅ Creado: {var_type.name}')
                created += 1
            else:
                self.stdout.write(f'  ⏭️  Ya existe: {var_type.name}')

        return created

    def migrate_existing_data(self, dry_run=False):
        """Migrar datos existentes de ProfileDataConfigCatchment."""
        # Obtener esquema por defecto
        try:
            default_scheme = ConfigurationScheme.objects.get(code='pozo_subterraneo_std')
        except ConfigurationScheme.DoesNotExist:
            self.stdout.write(self.style.ERROR('  ❌ Esquema "pozo_subterraneo_std" no encontrado'))
            return 0

        # Obtener campos del esquema
        field_map = {
            'd1': default_scheme.fields.get(code='d1'),
            'd2': default_scheme.fields.get(code='d2'),
            'd3': default_scheme.fields.get(code='d3'),
            'd4': default_scheme.fields.get(code='d4'),
            'd5': default_scheme.fields.get(code='d5'),
            'd6': default_scheme.fields.get(code='d6'),
            'addition': default_scheme.fields.get(code='addition'),
        }

        # Migrar frecuencias
        freq_map = {
            '1': SamplingFrequency.objects.get(code='1'),
            '5': SamplingFrequency.objects.get(code='5'),
            '10': SamplingFrequency.objects.get(code='10'),
            '60': SamplingFrequency.objects.get(code='60'),
        }

        migrated = 0
        profiles = ProfileDataConfigCatchment.objects.select_related('point_catchment').all()

        for profile in profiles:
            point = profile.point_catchment
            
            if dry_run:
                self.stdout.write(f'  [DRY RUN] Migraría punto: {point.title}')
                migrated += 1
                continue

            # Asignar esquema al punto
            if not point.configuration_scheme:
                point.configuration_scheme = default_scheme
                point.save(update_fields=['configuration_scheme'])

            # Migrar frecuencia
            if point.frecuency and not point.frequency:
                freq = freq_map.get(point.frecuency)
                if freq:
                    point.frequency = freq
                    point.save(update_fields=['frequency'])

            # Migrar valores d1-d6 y addition
            for field_code, field in field_map.items():
                if field is None:
                    continue
                
                value = getattr(profile, field_code, None)
                if value is None:
                    continue

                PointConfigurationValue.objects.get_or_create(
                    point=point,
                    field=field,
                    defaults={'value': value}
                )

            migrated += 1
            if migrated % 10 == 0:
                self.stdout.write(f'  📦 Migrados {migrated} puntos...')

        return migrated
