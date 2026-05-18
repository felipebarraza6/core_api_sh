"""
Comando de management para ejecutar el runner unificado de telemetría.

Uso:
    python manage.py run_telemetry --frequency=60
    python manage.py run_telemetry --frequency=60 --dry-run
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Ejecuta el runner unificado de telemetría para una frecuencia dada."

    def add_arguments(self, parser):
        parser.add_argument(
            "--frequency",
            type=str,
            required=True,
            help='Frecuencia de ejecución: "1", "5", "10" o "60"',
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Si se pasa, no guarda en BD (solo loguea). Útil para shadow mode.",
        )
        parser.add_argument(
            "--point-id",
            type=int,
            default=None,
            help="Si se pasa, solo procesa este punto de captación.",
        )
        parser.add_argument(
            "--type",
            type=str,
            default=None,
            choices=["tdata", "thethings", "novus"],
            help='Filtra puntos por tipo: "tdata", "thethings" o "novus".',
        )

    def handle(self, *args, **options):
        from api.cronjobs.telemetry.telemetry_unified import run

        frequency = options["frequency"]
        dry_run = options["dry_run"]
        point_id = options.get("point_id")
        point_type = options.get("type")

        if frequency not in ("1", "5", "10", "60"):
            self.stderr.write(self.style.ERROR(f"Frecuencia inválida: {frequency}"))
            return

        mode = "DRY-RUN" if dry_run else "PRODUCCIÓN"
        filter_msg = ""
        if point_id:
            filter_msg += f" | Punto={point_id}"
        if point_type:
            filter_msg += f" | Tipo={point_type}"
        self.stdout.write(self.style.NOTICE(f"[run_telemetry] Frecuencia={frequency} | Modo={mode}{filter_msg}"))

        run(frequency=frequency, dry_run=dry_run, point_id=point_id, point_type=point_type)

        self.stdout.write(self.style.SUCCESS("[run_telemetry] Finalizado"))
