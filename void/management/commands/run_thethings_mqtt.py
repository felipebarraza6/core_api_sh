"""
Comando de management para ejecutar el subscriber MQTT de TheThings.io.

Uso:
    python manage.py run_thethings_mqtt

Este proceso es long-running; se recomienda ejecutarlo como servicio Docker
con restart: always, o mediante supervisord/systemd fuera de contenedores.
"""

from django.core.management.base import BaseCommand

from void.services.mqtt_thethings import TheThingsMQTTClient


class Command(BaseCommand):
    help = "Subscriptor MQTT persistente para telemetría TheThings.io"

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Iniciando subscriber TheThings.io MQTT..."))
        client = TheThingsMQTTClient()
        client.run()
