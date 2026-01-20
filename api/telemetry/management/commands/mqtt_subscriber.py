"""
Comando para gestionar el servicio de suscripción MQTT.

Uso:
    python manage.py mqtt_subscriber start    # Iniciar servicio
    python manage.py mqtt_subscriber stop     # Detener servicio
    python manage.py mqtt_subscriber status   # Ver estado
"""

from django.core.management.base import BaseCommand
from api.telemetry.providers.mqtt_subscriber_service import (
    start_mqtt_subscriber,
    stop_mqtt_subscriber,
    mqtt_subscriber
)


class Command(BaseCommand):
    help = 'Gestionar servicio de suscripción MQTT'

    def add_arguments(self, parser):
        parser.add_argument(
            'action',
            type=str,
            choices=['start', 'stop', 'status'],
            help='Acción a realizar (start/stop/status)'
        )

    def handle(self, *args, **options):
        action = options['action']

        if action == 'start':
            self.stdout.write(self.style.SUCCESS('🚀 Iniciando MQTT Subscriber Service...'))

            try:
                service = start_mqtt_subscriber()
                self.stdout.write(self.style.SUCCESS('✅ Servicio iniciado exitosamente'))
                self.stdout.write(f'   Broker: {service.broker_host}:{service.broker_port}')
                self.stdout.write(f'   Puntos configurados: {len(service.point_configs)}')

                # Mantener servicio corriendo
                self.stdout.write('\n⏳ Servicio corriendo... (Ctrl+C para detener)')
                try:
                    import time
                    while True:
                        time.sleep(1)
                except KeyboardInterrupt:
                    self.stdout.write('\n\n⚠️  Deteniendo servicio...')
                    stop_mqtt_subscriber()
                    self.stdout.write(self.style.SUCCESS('✅ Servicio detenido'))

            except Exception as e:
                self.stdout.write(self.style.ERROR(f'❌ Error: {e}'))

        elif action == 'stop':
            self.stdout.write('⚠️  Deteniendo MQTT Subscriber Service...')
            stop_mqtt_subscriber()
            self.stdout.write(self.style.SUCCESS('✅ Servicio detenido'))

        elif action == 'status':
            if mqtt_subscriber and mqtt_subscriber.is_running:
                self.stdout.write(self.style.SUCCESS('✅ Servicio CORRIENDO'))
                self.stdout.write(f'   Broker: {mqtt_subscriber.broker_host}:{mqtt_subscriber.broker_port}')
                self.stdout.write(f'   Puntos configurados: {len(mqtt_subscriber.point_configs)}')
            else:
                self.stdout.write(self.style.WARNING('⚠️  Servicio DETENIDO'))
