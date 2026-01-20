"""
Comando para migrar configuración DGA legacy a sistema de Compliance dinámico.

Usage:
    python manage.py migrate_dga_to_compliance --dry-run  # Ver qué haría
    python manage.py migrate_dga_to_compliance            # Ejecutar migración
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from api.telemetry.providers.compliance_models import (
    ComplianceProvider,
    PointComplianceConfig,
    ComplianceStandard
)
from api.telemetry.models.catchment_points import CatchmentPoint


class Command(BaseCommand):
    help = 'Migrar configuración DGA legacy a sistema de Compliance dinámico'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Mostrar qué se haría sin ejecutar cambios',
        )
        parser.add_argument(
            '--skip-provider',
            action='store_true',
            help='Saltar creación del proveedor DGA (si ya existe)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        skip_provider = options['skip_provider']

        if dry_run:
            self.stdout.write(self.style.WARNING('🔍 MODO DRY-RUN - No se harán cambios reales'))

        self.stdout.write(self.style.SUCCESS('🚀 Iniciando migración DGA → Compliance'))

        # Estadísticas
        stats = {
            'provider_created': False,
            'provider_updated': False,
            'points_migrated': 0,
            'points_skipped': 0,
            'points_errors': 0,
            'configs_created': 0,
        }

        try:
            with transaction.atomic():
                # Paso 1: Crear/Actualizar proveedor DGA
                if not skip_provider:
                    self.stdout.write('\n📝 Paso 1: Configurando proveedor DGA...')
                    dga_provider, created = self._create_or_update_dga_provider(dry_run)

                    if created:
                        stats['provider_created'] = True
                        self.stdout.write(self.style.SUCCESS('  ✅ Proveedor DGA creado'))
                    else:
                        stats['provider_updated'] = True
                        self.stdout.write(self.style.SUCCESS('  ✅ Proveedor DGA actualizado'))
                else:
                    self.stdout.write('\n⏭️  Paso 1: Saltando creación de proveedor...')
                    dga_provider = ComplianceProvider.objects.get(name='dga')
                    self.stdout.write(self.style.SUCCESS('  ✅ Usando proveedor existente'))

                # Paso 2: Migrar puntos con configuración DGA
                self.stdout.write('\n📊 Paso 2: Migrando puntos con DGA...')

                # Obtener puntos con DGA configurado
                points_with_dga = self._get_points_with_dga()
                total_points = len(points_with_dga)

                self.stdout.write(f'  📍 Encontrados {total_points} puntos con configuración DGA')

                if total_points == 0:
                    self.stdout.write(self.style.WARNING('  ⚠️  No hay puntos para migrar'))
                    return

                # Migrar cada punto
                for i, point in enumerate(points_with_dga, 1):
                    self.stdout.write(f'\n  [{i}/{total_points}] Procesando: {point.title} ({point.point_code})')

                    try:
                        config_created = self._migrate_point_dga_config(
                            point,
                            dga_provider,
                            dry_run
                        )

                        if config_created:
                            stats['points_migrated'] += 1
                            stats['configs_created'] += 1
                            self.stdout.write(self.style.SUCCESS(f'    ✅ Migrado'))
                        else:
                            stats['points_skipped'] += 1
                            self.stdout.write(self.style.WARNING(f'    ⏭️  Ya tenía configuración de compliance'))

                    except Exception as e:
                        stats['points_errors'] += 1
                        self.stdout.write(self.style.ERROR(f'    ❌ Error: {e}'))

                # Paso 3: Verificación
                self.stdout.write('\n🔍 Paso 3: Verificando migración...')
                self._verify_migration(dga_provider)

                if dry_run:
                    self.stdout.write(self.style.WARNING('\n⚠️  DRY-RUN: Revertiendo cambios...'))
                    raise Exception("Dry run - rolling back")

        except Exception as e:
            if dry_run:
                self.stdout.write(self.style.WARNING('  ✅ Cambios revertidos (dry-run)'))
            else:
                self.stdout.write(self.style.ERROR(f'\n❌ Error durante migración: {e}'))
                raise

        # Mostrar resumen
        self._print_summary(stats, dry_run)

    def _create_or_update_dga_provider(self, dry_run=False):
        """Crear o actualizar el proveedor DGA."""

        provider_config = {
            'name': 'dga',
            'display_name': 'DGA - Dirección General de Aguas',
            'description': 'Sistema de reporte automático de telemetría a la Dirección General de Aguas de Chile',
            'service_type': 'water_rights',

            # Conexión (ajustar URLs reales)
            'base_url': 'https://siac.mop.gob.cl/ufs',
            'auth_endpoint': '/login',
            'data_endpoint_template': '/{uf_id}/procesos/{process_id}/registros',
            'timeout_seconds': 30,

            # Autenticación
            'auth_method': 'oauth2',
            'auth_config': {
                'username': '',  # Se configura por punto o provider
                'password': '',
                'token_field': 'token',
                'auth_url': 'https://siac.mop.gob.cl/ufs/login'
            },

            # Payload template
            'payload_template': {
                'codigo_obra': '{config.codigo_obra}',
                'caudal': '{record.data.flow}',
                'volumen': '{record.data.total}',
                'nivel': '{record.data.nivel}',
                'fecha': '{record.timestamp}',
                'rut_informante': '{config.rut_informante}',
                'nombre_informante': '{config.nombre_informante}',
                'dispositivo_id': '{config.dispositivo_id}',
            },

            # Response mapping
            'response_mapping': {
                'success_field': 'estado',
                'success_value': 'OK',
                'voucher_field': 'comprobante',
                'message_field': 'mensaje',
                'error_field': 'error'
            },

            # Campos requeridos
            'required_fields': [
                {
                    'name': 'codigo_obra',
                    'type': 'string',
                    'label': 'Código de Obra',
                    'help': 'Código ND asignado por DGA (ej: ND-0401-1234)'
                },
                {
                    'name': 'rut_informante',
                    'type': 'string',
                    'label': 'RUT Informante',
                    'help': 'RUT del informante registrado en DGA'
                },
                {
                    'name': 'nombre_informante',
                    'type': 'string',
                    'label': 'Nombre Informante',
                    'help': 'Nombre completo del informante'
                },
                {
                    'name': 'uf_id',
                    'type': 'string',
                    'label': 'ID Unidad Fiscalizable',
                    'help': 'ID de la UF en sistema DGA'
                },
                {
                    'name': 'process_id',
                    'type': 'string',
                    'label': 'ID Proceso DGA',
                    'help': 'ID del proceso en sistema DGA'
                },
                {
                    'name': 'dispositivo_id',
                    'type': 'string',
                    'label': 'ID Dispositivo',
                    'help': 'ID del dispositivo registrado en DGA'
                },
                {
                    'name': 'caudal_otorgado',
                    'type': 'decimal',
                    'label': 'Caudal Otorgado (L/s)',
                    'help': 'Caudal otorgado según resolución DGA'
                },
                {
                    'name': 'tipo_derecho',
                    'type': 'string',
                    'label': 'Tipo de Derecho',
                    'help': 'Tipo de derecho de agua (ej: Consuntivo Permanente)'
                }
            ],

            # Variables de datos
            'data_variables': [
                {'name': 'caudal', 'type': 'decimal', 'label': 'Caudal (L/s)', 'unit': 'L/s'},
                {'name': 'volumen', 'type': 'decimal', 'label': 'Volumen (m³)', 'unit': 'm³'},
                {'name': 'nivel', 'type': 'decimal', 'label': 'Nivel (m)', 'unit': 'm'},
            ],

            # Validaciones
            'validation_rules': {
                'caudal': {
                    'min': 0,
                    'max': 10000,
                    'required': True
                },
                'volumen': {
                    'min': 0,
                    'required': False
                },
                'nivel': {
                    'min': 0,
                    'max': 1000,
                    'required': False
                }
            },

            # Frecuencia y reintentos
            'submission_frequency': 'hourly',
            'max_retries': 3,
            'retry_delay_seconds': 60,

            # Estado
            'is_active': True,
            'documentation_url': 'https://dga.mop.gob.cl/documentacion',
        }

        if dry_run:
            self.stdout.write('  [DRY-RUN] Creando/actualizando proveedor DGA...')
            return None, False

        provider, created = ComplianceProvider.objects.update_or_create(
            name='dga',
            defaults=provider_config
        )

        return provider, created

    def _get_points_with_dga(self):
        """Obtener puntos que tienen configuración DGA."""

        # Buscar puntos que tienen configuración DGA en el modelo asociado
        points = CatchmentPoint.objects.filter(
            dga_data_config_profiles__isnull=False
        ).select_related('dga_data_config_profiles').distinct()

        return list(points)

    def _migrate_point_dga_config(self, point, dga_provider, dry_run=False):
        """Migrar configuración DGA de un punto específico."""

        # Verificar si ya tiene config de compliance DGA
        existing_config = PointComplianceConfig.objects.filter(
            point=point,
            provider=dga_provider
        ).first()

        if existing_config:
            self.stdout.write(f'    ℹ️  Ya existe PointComplianceConfig (ID: {existing_config.id})')
            return False

        # Construir config_data desde dga_data_config
        config_data = self._extract_dga_config_data(point)

        if not config_data:
            self.stdout.write(f'    ⚠️  No se pudo extraer configuración DGA')
            return False

        self.stdout.write(f'    📋 Config extraída: {list(config_data.keys())}')

        if dry_run:
            self.stdout.write(f'    [DRY-RUN] Crearía PointComplianceConfig')
            return True

        # Obtener o crear el estándar de cumplimiento basado en la config legacy
        dga_config_legacy = point.dga_data_config_profiles.first()
        
        standard_code = dga_config_legacy.standard if dga_config_legacy else 'SIN_ESTANDAR'
        
        # Especial para CMP que en el nuevo sistema se llama 'CMP'
        if standard_code == 'CAUDALES_MUY_PEQUENOS':
            standard_code = 'CMP'
            
        compliance_standard = ComplianceStandard.objects.filter(code=standard_code).first()
        
        # Extraer credenciales override (clave DGA específica del pozo)
        credentials_override = {}
        if dga_config_legacy and dga_config_legacy.password_dga_software:
            credentials_override = {
                'password': dga_config_legacy.password_dga_software
            }

        # Crear PointComplianceConfig
        compliance_config = PointComplianceConfig.objects.create(
            point=point,
            provider=dga_provider,
            compliance_standard=compliance_standard,
            config_data=config_data,
            credentials_override=credentials_override,
            data_source='telemetry',
            is_active=True,
            send_compliance=dga_config_legacy.send_dga if dga_config_legacy else False,
        )

        self.stdout.write(f'    💾 PointComplianceConfig creado (ID: {compliance_config.id})')

        return True

    def _extract_dga_config_data(self, point):
        """Extraer datos de configuración DGA del punto."""
        config_data = {}
        dga_config = point.dga_data_config_profiles.first()

        # Extraer de dga_data_config si existe
        if dga_config:

            # Mapear campos del modelo DgaDataConfigCatchment
            field_mapping = {
                'codigo_obra': 'codigo_obra',
                'rut_informante': 'rut_informante',
                'nombre_informante': 'nombre_informante',
                'uf_id': 'uf_id',
                'process_id': 'process_id',
                'dispositivo_id': 'id_dispositivo',  # Puede tener nombre diferente
                'caudal_otorgado': 'caudal_otorgado',
                'tipo_derecho': 'tipo_derecho',
            }

            for config_key, model_field in field_mapping.items():
                if hasattr(dga_config, model_field):
                    value = getattr(dga_config, model_field)
                    if value:
                        config_data[config_key] = value

        # Agregar datos adicionales del punto
        if hasattr(point, 'dga_estandar') and point.dga_estandar:
            config_data['estandar_dga'] = point.dga_estandar

        # Si no hay datos, intentar construir mínimos
        if not config_data:
            # Al menos el point_code como codigo_obra
            config_data = {
                'codigo_obra': point.point_code,
                'rut_informante': '',  # Deberá completarse manualmente
                'nombre_informante': '',
            }

        return config_data

    def _verify_migration(self, dga_provider):
        """Verificar que la migración fue exitosa."""

        # Contar configuraciones creadas
        total_configs = PointComplianceConfig.objects.filter(
            provider=dga_provider
        ).count()

        active_configs = PointComplianceConfig.objects.filter(
            provider=dga_provider,
            is_active=True
        ).count()

        sending_configs = PointComplianceConfig.objects.filter(
            provider=dga_provider,
            send_compliance=True
        ).count()

        self.stdout.write(f'  📊 Total configuraciones DGA: {total_configs}')
        self.stdout.write(f'  ✅ Activas: {active_configs}')
        self.stdout.write(f'  📤 Con envío habilitado: {sending_configs}')

    def _print_summary(self, stats, dry_run):
        """Imprimir resumen de la migración."""

        self.stdout.write('\n' + '='*70)
        self.stdout.write(self.style.SUCCESS('📊 RESUMEN DE MIGRACIÓN'))
        self.stdout.write('='*70)

        if dry_run:
            self.stdout.write(self.style.WARNING('⚠️  MODO DRY-RUN - Ningún cambio fue guardado'))

        self.stdout.write(f"\n🔧 Proveedor DGA:")
        if stats['provider_created']:
            self.stdout.write(self.style.SUCCESS('  ✅ Creado'))
        elif stats['provider_updated']:
            self.stdout.write(self.style.SUCCESS('  ✅ Actualizado'))
        else:
            self.stdout.write('  ⏭️  Sin cambios')

        self.stdout.write(f"\n📍 Puntos:")
        self.stdout.write(f"  ✅ Migrados: {stats['points_migrated']}")
        self.stdout.write(f"  ⏭️  Saltados: {stats['points_skipped']}")
        self.stdout.write(f"  ❌ Errores: {stats['points_errors']}")

        self.stdout.write(f"\n📋 Configuraciones:")
        self.stdout.write(f"  ✅ Creadas: {stats['configs_created']}")

        if not dry_run and stats['points_migrated'] > 0:
            self.stdout.write('\n' + '='*70)
            self.stdout.write(self.style.SUCCESS('✅ MIGRACIÓN COMPLETADA EXITOSAMENTE'))
            self.stdout.write('='*70)
            self.stdout.write('\n📝 Próximos pasos:')
            self.stdout.write('  1. Verificar configuraciones en Admin → Point Compliance Configs')
            self.stdout.write('  2. Completar credenciales en Admin → Compliance Providers → DGA')
            self.stdout.write('  3. Revisar y ajustar config_data de cada punto según necesidad')
            self.stdout.write('  4. Probar envío manual con un punto de prueba')
            self.stdout.write('  5. Una vez confirmado, deprecar campos legacy en CatchmentPoint')

        elif dry_run:
            self.stdout.write('\n' + '='*70)
            self.stdout.write(self.style.WARNING('🔍 VISTA PREVIA COMPLETADA'))
            self.stdout.write('='*70)
            self.stdout.write('\n📝 Para ejecutar la migración real:')
            self.stdout.write('  python manage.py migrate_dga_to_compliance')

        self.stdout.write('')
