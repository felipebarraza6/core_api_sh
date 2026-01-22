import asyncio
import logging
from django.core.management.base import BaseCommand
from api.telemetry.providers.models import TelemetryProvider
from api.telemetry.providers.mqtt_subscriber_service import MQTTSubscriberService
# Note: SmartHydroMQTTBroker needs to be imported carefully if it's async

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Lanza un servicio MQTT dinámico para un proveedor específico'

    def add_arguments(self, parser):
        parser.add_argument('provider_id', type=int, help='ID del TelemetryProvider')
        parser.add_argument('--port', type=int, help='Override de puerto')

    def handle(self, *args, **options):
        provider_id = options['provider_id']
        try:
            provider = TelemetryProvider.objects.get(id=provider_id)
        except TelemetryProvider.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Proveedor {provider_id} no existe"))
            return

        if not hasattr(provider, 'mqtt_config'):
            self.stdout.write(self.style.ERROR(f"Proveedor {provider.name} no tiene configuración MQTT"))
            return

        config = provider.mqtt_config
        port = options['port'] or config.broker_port
        
        self.stdout.write(self.style.SUCCESS(f"🚀 Iniciando servicio para {provider.name} en modo '{config.mode}' (Puerto: {port})"))

        if config.mode == 'client':
            # Modo Cliente: SmartHydro se conecta a un broker externo
            service = MQTTSubscriberService(provider=provider, broker_port=port)
            try:
                service.start()
                self.stdout.write(self.style.SUCCESS("✅ Suscripción activa. Presione Ctrl+C para detener."))
                # Keep alive
                import time
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                self.stdout.write(self.style.WARNING("\n🛑 Deteniendo servicio de suscripción..."))
                service.stop()
        else:
            # Modo Servidor: SmartHydro ACTÚA como broker
            from api.core.mqtt_broker import SmartHydroMQTTBroker
            broker_service = SmartHydroMQTTBroker(provider=provider)
            
            async def run_broker():
                try:
                    await broker_service.start_broker(host='0.0.0.0', port=port)
                    self.stdout.write(self.style.SUCCESS(f"✅ Broker Interno activo en puerto {port}. Presione Ctrl+C para detener."))
                    
                    # El broker de hbmqtt corre en su propio loop interno una vez iniciado
                    while True:
                        await asyncio.sleep(3600)
                except Exception as e:
                    logger.error(f"Error en el broker: {e}")
                finally:
                    await broker_service.shutdown()

            try:
                loop = asyncio.get_event_loop()
                loop.run_until_complete(run_broker())
            except KeyboardInterrupt:
                self.stdout.write(self.style.WARNING("\n🛑 Apagando broker MQTT..."))

