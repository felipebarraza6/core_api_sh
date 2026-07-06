"""
Comando de management para simular la llegada de un mensaje MQTT de TheThings.io.

Uso:
    python manage.py simulate_thethings_mqtt \
        --token <THING_TOKEN> \
        --values '{"pulsos": 999, "nivel": 5.5}' \
        --datetime "2026-07-06T14:30:00Z"

No toca la plataforma real; inyecta los valores directamente en la misma ruta de
procesamiento que usa el subscriber MQTT (_save_mqtt_measurement).
"""

import json
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from api.core.models import CatchmentPoint
from api.core.serializers import CatchmentPointSerializerDetailCron
from void.services.mqtt_thethings import (
    _lookup_point_by_token,
    _save_mqtt_measurement,
    _serialize_point_for_processing,
)


class Command(BaseCommand):
    help = "Simula la llegada de un mensaje MQTT de TheThings.io para un punto"

    def add_arguments(self, parser):
        parser.add_argument(
            "--token",
            required=True,
            help="THING_TOKEN del punto a simular",
        )
        parser.add_argument(
            "--values",
            required=True,
            help='JSON con los valores a inyectar, ej. {"pulsos": 999, "nivel": 5.5}',
        )
        parser.add_argument(
            "--datetime",
            dest="dt_str",
            help='Timestamp ISO de los valores (default: ahora UTC), ej. 2026-07-06T14:30:00Z',
        )

    def handle(self, *args, **options):
        token = options["token"]
        values_raw = options["values"]
        dt_str = options["dt_str"]

        # Validar JSON de valores
        try:
            values_dict = json.loads(values_raw)
        except json.JSONDecodeError as e:
            raise CommandError(f"--values no es JSON válido: {e}")

        if not isinstance(values_dict, dict):
            raise CommandError("--values debe ser un objeto JSON, ej. {\"pulsos\": 999}")

        # Timestamp por defecto
        if not dt_str:
            dt_str = timezone.now().strftime("%Y-%m-%dT%H:%M:%SZ")

        # Normalizar a formato Z
        try:
            dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
            dt_iso = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError as e:
            raise CommandError(f"--datetime no es una fecha válida: {e}")

        # Buscar punto
        point = _lookup_point_by_token(token)
        if not point:
            raise CommandError(
                f"No se encontró un punto activo asociado al token '{token}'"
            )

        point_data = _serialize_point_for_processing(point)
        if not point_data:
            raise CommandError(f"No se pudo serializar el punto {point.id}")

        # Convertir a formato de payload MQTT
        mqtt_values = []
        for key, value in values_dict.items():
            mqtt_values.append({
                "key": key,
                "value": value,
                "datetime": dt_iso,
            })

        self.stdout.write(
            self.style.NOTICE(
                f"Simulando mensaje MQTT para punto {point.id} "
                f"(token={token[:8]}...) con {len(mqtt_values)} valor(es)"
            )
        )

        ok = _save_mqtt_measurement(point_data, token, mqtt_values)

        if ok:
            self.stdout.write(
                self.style.SUCCESS(
                    f"OK: punto {point.id} procesado | datetime={dt_iso}"
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    f"No se procesó ninguna variable conocida para punto {point.id}"
                )
            )
