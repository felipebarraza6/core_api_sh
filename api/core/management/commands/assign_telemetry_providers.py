"""
Comando para asignar TelemetryProvider a las variables según el tipo de punto.

Uso:
    python manage.py assign_telemetry_providers --dry-run
    python manage.py assign_telemetry_providers
"""
from django.core.management.base import BaseCommand

from api.core.models import CatchmentPoint, TelemetryProvider, Variable


class Command(BaseCommand):
    help = "Asigna TelemetryProvider a variables sin provider según is_tdata/is_thethings/is_novus"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Muestra cambios sin aplicarlos",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        # Cargar providers
        providers = {}
        for tp in TelemetryProvider.objects.all():
            providers[tp.handler_name] = tp

        required = ["tdata", "thethings", "tago"]
        missing = [h for h in required if h not in providers]
        if missing:
            self.stderr.write(self.style.ERROR(f"Faltan providers: {missing}"))
            return

        # Mapeo de flag -> handler_name
        flag_to_handler = {
            "is_tdata": "tdata",
            "is_thethings": "thethings",
            "is_novus": "tago",
        }

        puntos = CatchmentPoint.objects.filter(data_config_profiles__is_telemetry=True)
        total_vars = 0
        puntos_afectados = 0

        for punto in puntos:
            handler_name = None
            for flag, handler in flag_to_handler.items():
                if getattr(punto, flag, False):
                    handler_name = handler
                    break

            if not handler_name:
                self.stdout.write(
                    self.style.WARNING(
                        f"Punto {punto.id} ({punto.title}): sin tipo telemetría (tdata/thethings/novus)"
                    )
                )
                continue

            provider = providers[handler_name]
            vars_sin_provider = Variable.objects.filter(
                scheme_catchment__points_catchment=punto,
                provider__isnull=True,
            )
            count = vars_sin_provider.count()
            if count:
                total_vars += count
                puntos_afectados += 1
                if not dry_run:
                    vars_sin_provider.update(provider=provider)
                self.stdout.write(
                    f"Punto {punto.id} ({punto.title}): {count} variables -> {handler_name}"
                )

        mode = "[DRY-RUN] " if dry_run else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{mode}Total: {total_vars} variables actualizadas en {puntos_afectados} puntos"
            )
        )
