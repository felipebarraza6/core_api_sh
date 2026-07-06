"""Run shadow mode comparison for one or all devices."""
from django.core.management.base import BaseCommand

from void.models import Device
from void.services import ShadowService


class Command(BaseCommand):
    help = "Ejecuta shadow mode: compara lecturas legacy vs void"

    def add_arguments(self, parser):
        parser.add_argument(
            "--device-id",
            type=int,
            help="ID del device void a comparar. Si no se indica, corre sobre todos los activos.",
        )
        parser.add_argument(
            "--variable",
            type=str,
            default="pulses",
            help="Variable a comparar (default: pulses).",
        )
        parser.add_argument(
            "--window-minutes",
            type=int,
            default=70,
            help="Ventana de tiempo hacia atrás (default: 70 min).",
        )
        parser.add_argument(
            "--max-devices",
            type=int,
            default=None,
            help="Máximo de dispositivos a procesar (solo si --device-id no se indica).",
        )
        parser.add_argument(
            "--no-ingest",
            action="store_true",
            help="No ingesar desde proveedor; solo comparar datos ya existentes en void.",
        )
        parser.add_argument(
            "--process",
            action="store_true",
            help="Procesar lecturas crudas con PipelineService antes de comparar.",
        )

    def handle(self, *args, **options):
        device_id = options["device_id"]
        variable = options["variable"]
        window_minutes = options["window_minutes"]
        max_devices = options["max_devices"]
        ingest = not options["no_ingest"]
        process = options["process"]

        service = ShadowService()

        if device_id:
            qs = Device.objects.filter(pk=device_id)
        else:
            qs = Device.objects.filter(
                is_active=True,
                provider__is_active=True,
            ).exclude(point__legacy_point__isnull=True)
            if max_devices:
                qs = qs[:max_devices]

        total = qs.count()
        self.stdout.write(f"Procesando {total} dispositivo(s) para variable '{variable}'...")

        for device in qs:
            run = service.run(
                device=device,
                variable=variable,
                window_minutes=window_minutes,
                ingest=ingest,
                process=process,
            )
            self.stdout.write(
                f"  Device {device.id} ({device}): {run.status} | "
                f"legacy={run.legacy_count} void={run.void_count} "
                f"match={run.matched_count} mismatch={run.mismatched_count} "
                f"legacy_only={run.legacy_only_count} void_only={run.void_only_count}"
            )
            if run.error_message:
                self.stdout.write(self.style.WARNING(f"    Error: {run.error_message}"))
