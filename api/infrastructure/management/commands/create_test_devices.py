"""
Management command para crear datos de prueba de Infrastructure.
Crea 3 fabricantes (Novus, Nettra, Twin) con 1 modelo y 5 dispositivos cada uno.
"""

from django.core.management.base import BaseCommand
from api.infrastructure.models import Manufacturer, DeviceModel, Device


class Command(BaseCommand):
    help = 'Crea fabricantes, modelos y dispositivos de prueba'

    def handle(self, *args, **options):
        # Definir fabricantes con sus datos
        manufacturers_data = [
            {
                'name': 'Novus Automation',
                'code': 'NOVUS',
                'description': 'Fabricante brasileño de equipos de automatización y telemetría',
                'website': 'https://www.novusautomation.com',
                'integration_status': 'PRODUCTION',
                'model': {
                    'model_name': 'NXperience',
                    'model_code': 'NXP-IoT-4G',
                    'description': 'Datalogger IoT con conectividad 4G y múltiples entradas analógicas/digitales'
                }
            },
            {
                'name': 'Nettra',
                'code': 'NETTRA',
                'description': 'Proveedor de soluciones IoT para monitoreo remoto',
                'website': 'https://www.nettra.io',
                'integration_status': 'PRODUCTION',
                'model': {
                    'model_name': 'Nettra RTU',
                    'model_code': 'NRTU-2000',
                    'description': 'Unidad de telemetría remota con soporte MQTT y Modbus'
                }
            },
            {
                'name': 'Twin',
                'code': 'TWIN',
                'description': 'Fabricante de sensores y dataloggers industriales',
                'website': 'https://www.twin.cl',
                'integration_status': 'TESTING',
                'model': {
                    'model_name': 'Twin Logger',
                    'model_code': 'TL-500',
                    'description': 'Logger compacto con batería solar y comunicación LoRa/4G'
                }
            },
        ]

        created_counts = {'manufacturers': 0, 'models': 0, 'devices': 0}

        for mfr_data in manufacturers_data:
            model_data = mfr_data.pop('model')

            # Crear o obtener fabricante
            manufacturer, created = Manufacturer.objects.get_or_create(
                code=mfr_data['code'],
                defaults=mfr_data
            )
            if created:
                created_counts['manufacturers'] += 1
                self.stdout.write(self.style.SUCCESS(f'  Fabricante creado: {manufacturer.name}'))
            else:
                self.stdout.write(f'  Fabricante existente: {manufacturer.name}')

            # Crear o obtener modelo
            device_model, created = DeviceModel.objects.get_or_create(
                manufacturer=manufacturer,
                model_code=model_data['model_code'],
                defaults=model_data
            )
            if created:
                created_counts['models'] += 1
                self.stdout.write(self.style.SUCCESS(f'    Modelo creado: {device_model.model_name}'))
            else:
                self.stdout.write(f'    Modelo existente: {device_model.model_name}')

            # Crear 5 dispositivos para este modelo
            for i in range(1, 6):
                device_name = f'{manufacturer.code}-{device_model.model_code}-{i:03d}'

                # Verificar si ya existe un dispositivo con este nombre
                existing = Device.objects.filter(name=device_name).exists()
                if not existing:
                    device = Device.objects.create(
                        name=device_name,
                        device_model=device_model,
                        status='OFFLINE',
                        imei=f'35000000000{manufacturer.code[:2]}{i:02d}' if i <= 2 else ''
                    )
                    created_counts['devices'] += 1
                    self.stdout.write(f'      Device creado: {device.name} (token: {device.token[:8]}...)')
                else:
                    self.stdout.write(f'      Device existente: {device_name}')

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'Resumen: {created_counts["manufacturers"]} fabricantes, '
            f'{created_counts["models"]} modelos, '
            f'{created_counts["devices"]} dispositivos creados'
        ))
