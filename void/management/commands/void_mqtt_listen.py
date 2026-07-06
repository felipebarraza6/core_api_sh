"""Start MQTT listener for void providers."""
from django.core.management.base import BaseCommand

from void.models import Provider
from void.services.mqtt import MqttConsumer


class Command(BaseCommand):
    help = "Inicia listener MQTT para proveedores void configurados"

    def add_arguments(self, parser):
        parser.add_argument(
            "--provider-id",
            type=int,
            help="ID del proveedor MQTT a escuchar. Si no se indica, escucha todos los activos.",
        )
        parser.add_argument(
            "--daemon",
            action="store_true",
            help="Modo no bloqueante (loop_start).",
        )

    def handle(self, *args, **options):
        provider_id = options["provider_id"]
        daemon = options["daemon"]

        qs = Provider.objects.filter(protocol="MQTT", is_active=True)
        if provider_id:
            qs = qs.filter(pk=provider_id)

        if not qs.exists():
            self.stdout.write(self.style.WARNING("No hay proveedores MQTT activos."))
            return

        consumers = []
        for provider in qs:
            self.stdout.write(self.style.NOTICE(f"Iniciando consumer para {provider}..."))
            consumer = MqttConsumer(provider)
            consumers.append(consumer)
            if daemon:
                consumer.run_non_blocking()

        if daemon:
            self.stdout.write(self.style.SUCCESS("Consumers MQTT iniciados en modo daemon."))
            # En modo daemon no bloqueamos; en producción esto debe correr como servicio.
            import time
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                for consumer in consumers:
                    consumer.client.loop_stop()
        else:
            # Solo un consumer en modo bloqueante; múltiples requieren threads o servicios separados.
            consumer = consumers[0]
            consumer.run_forever()
