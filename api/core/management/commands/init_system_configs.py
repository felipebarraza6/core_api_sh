from django.core.management.base import BaseCommand
from api.telemetry.models.management_super import SystemConfiguration
from api.compliance.models import ComplianceProvider

class Command(BaseCommand):
    help = 'Initialize system configurations'

    def handle(self, *args, **options):
        configs = [
            {
                'key': 'google_chat.webhook_url',
                'value': 'https://chat.googleapis.com/v1/spaces/AAQAm9y1FaI/messages?key=AIzaSyDdI0hCZtE6vySjMm-WEfRq3CPzqKqqsHI&token=IMIDu11REWEYRywIk-zC_QFo5tPi04IqvY1ToNuk9Vo',
                'category': 'NOTIFICATIONS',
                'description': 'URL principal para notificaciones de Google Chat'
            },
            {
                'key': 'google_chat.webhook_dga_url',
                'value': 'https://chat.googleapis.com/v1/spaces/AAQAuNyVmJc/messages?key=AIzaSyDdI0hCZtE6vySjMm-WEfRq3CPzqKqqsHI&token=vGilyWJuJR8AKXYSobhQYLYNalVAqtUwyiEpm6iLGhU',
                'category': 'NOTIFICATIONS',
                'description': 'URL para notificaciones de reportes DGA'
            }
        ]

        for config_data in configs:
            obj, created = SystemConfiguration.objects.get_or_create(
                key=config_data['key'],
                defaults=config_data
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'Created config: {obj.key}'))
            else:
                self.stdout.write(f'Config already exists: {obj.key}')

        # 2. Inicializar Proveedores de Cumplimiento base
        self.stdout.write('\n📝 Paso 2: Configurando proveedores de cumplimiento...')
        
        providers = [
            {
                'name': 'dga',
                'display_name': 'DGA - Dirección General de Aguas',
                'description': 'Sistema de reporte automático de telemetría a la DGA',
                'service_type': 'water_rights',
                'base_url': 'https://siac.mop.gob.cl/ufs',
                'auth_endpoint': '/login',
                'data_endpoint_template': '/{uf_id}/procesos/{process_id}/registros',
                'auth_method': 'oauth2',
                'auth_config': {
                    'username_field': 'usuario',
                    'password_field': 'password',
                    'token_response_field': 'token'
                },
                'payload_template': {
                    'codigo_obra': '{config.codigo_obra}',
                    'caudal': '{record.data.flow}',
                    'volumen': '{record.data.total}',
                    'nivel': '{record.data.nivel}',
                    'fecha': '{record.timestamp|format:%Y-%m-%dT%H:%M:%S}',
                    'rut_informante': '{config.rut_informante}',
                    'nombre_informante': '{config.nombre_informante}',
                    'dispositivo_id': '{config.dispositivo_id}',
                }
            },
            {
                'name': 'sma',
                'display_name': 'SMA - Superintendencia del Medio Ambiente',
                'description': 'Sistema de reporte automático de telemetría a la SMA',
                'service_type': 'environmental',
                'base_url': 'https://conexiones.sma.gob.cl/api/v1',
                'auth_endpoint': '/auth',
                'data_endpoint_template': '/ufs/{uf_id}/procesos/{process_id}/registros',
                'auth_method': 'oauth2',
                'auth_config': {
                    'username': '76006727-K',
                    'password': '{O=+b_k_aD',
                    'username_field': 'usuario',
                    'password_field': 'password',
                    'token_response_field': 'token'
                },
                'payload_template': [
                    {
                        "dispositivoId": "{config.dispositivo_id}",
                        "parametros": [
                            {
                                "nombre": "Q",
                                "valor": "{record.data.flow}",
                                "unidad": "l/s",
                                "estampaTiempo": "{record.timestamp|format:%Y-%m-%dT%H:%M:%S}"
                            },
                            {
                                "nombre": "VA",
                                "valor": "{record.data.total}",
                                "unidad": "m3",
                                "estampaTiempo": "{record.timestamp|format:%Y-%m-%dT%H:%M:%S}"
                            }
                        ]
                    }
                ]
            }
        ]

        for prov_data in providers:
            obj, created = ComplianceProvider.objects.get_or_create(
                name=prov_data['name'],
                defaults=prov_data
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'Created provider: {obj.display_name}'))
            else:
                self.stdout.write(f'Provider already exists: {obj.display_name}')
