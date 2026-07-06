"""Reporte de shadow mode por ventana de tiempo.

Ejemplos:
    python manage.py void_shadow_report --hours 24
    python manage.py void_shadow_report --device-id 55 --hours 6
    python manage.py void_shadow_report --project-legacy-id 2 --hours 12
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta

from void.models import Device, ShadowRun


class Command(BaseCommand):
    help = "Reporte de resultados de shadow mode"

    def add_arguments(self, parser):
        parser.add_argument(
            "--hours",
            type=int,
            default=24,
            help="Ventana hacia atrás en horas (default: 24).",
        )
        parser.add_argument(
            "--device-id",
            type=int,
            help="Filtrar por device void específico.",
        )
        parser.add_argument(
            "--project-legacy-id",
            type=int,
            help="Filtrar por proyecto legacy.",
        )
        parser.add_argument(
            "--output-field",
            type=str,
            help="Filtrar por campo procesado (total, flow, nivel, water_table).",
        )

    def handle(self, *args, **options):
        hours = options["hours"]
        device_id = options["device_id"]
        project_id = options["project_legacy_id"]
        output_field = options["output_field"]

        since = timezone.now() - timedelta(hours=hours)
        qs = ShadowRun.objects.filter(created__gte=since)

        if device_id:
            qs = qs.filter(device_id=device_id)
        if project_id:
            qs = qs.filter(device__point__legacy_point__project_id=project_id)
        if output_field:
            qs = qs.filter(output_field=output_field)

        total_runs = qs.count()
        if total_runs == 0:
            self.stdout.write(self.style.WARNING("No hay shadow runs en la ventana solicitada."))
            return

        total_match = sum(r.matched_count for r in qs)
        total_mismatch = sum(r.mismatched_count for r in qs)
        total_legacy_only = sum(r.legacy_only_count for r in qs)
        total_void_only = sum(r.void_only_count for r in qs)

        self.stdout.write(self.style.NOTICE(f"Shadow report últimas {hours}h"))
        self.stdout.write(f"Runs: {total_runs}")
        self.stdout.write(
            f"Comparaciones: match={total_match} mismatch={total_mismatch} "
            f"legacy_only={total_legacy_only} void_only={total_void_only}"
        )

        # Agrupar por punto/campo.
        grouped = {}
        for run in qs.select_related("device", "device__point"):
            key = (run.device.point.name, run.output_field or run.variable)
            if key not in grouped:
                grouped[key] = {
                    "match": 0,
                    "mismatch": 0,
                    "legacy_only": 0,
                    "void_only": 0,
                    "runs": 0,
                }
            grouped[key]["match"] += run.matched_count
            grouped[key]["mismatch"] += run.mismatched_count
            grouped[key]["legacy_only"] += run.legacy_only_count
            grouped[key]["void_only"] += run.void_only_count
            grouped[key]["runs"] += 1

        self.stdout.write(self.style.NOTICE("\nPor punto/campo:"))
        for (point, field), stats in sorted(grouped.items()):
            total_comparisons = stats["match"] + stats["mismatch"] + stats["legacy_only"] + stats["void_only"]
            if total_comparisons == 0:
                continue
            match_pct = stats["match"] * 100 / total_comparisons
            self.stdout.write(
                f"  {point:30s} | {field:15s} | "
                f"match={stats['match']:3d} mismatch={stats['mismatch']:3d} "
                f"L_only={stats['legacy_only']:3d} V_only={stats['void_only']:3d} "
                f"({match_pct:5.1f}%)"
            )
