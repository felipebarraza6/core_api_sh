"""Inicializa el offset de totalizadores void desde legacy InteractionDetail.

Cuando un punto legacy ya lleva tiempo acumulando, su ``InteractionDetail.total``
puede ser mayor que el valor crudo del contador (``pulses``) por resets/
compensaciones históricas. Este comando calcula ese offset y lo aplica al
estado stateful de void para que los totales coincidan desde el inicio.

Uso:
    python manage.py void_init_totalizer_offset --project-legacy-id 2 --dry-run
    python manage.py void_init_totalizer_offset --project-legacy-id 2
    python manage.py void_init_totalizer_offset --point-id 109 --dry-run
"""
from decimal import Decimal

from django.core.management.base import BaseCommand

from api.core.models import InteractionDetail
from void.models import Device, DeviceVariableConfig, DeviceVariableState, Point


class Command(BaseCommand):
    help = "Inicializa offset de totalizadores void desde legacy"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="No guardar cambios, solo mostrar lo que se haría.",
        )
        parser.add_argument(
            "--point-id",
            type=int,
            help="ID legacy del punto (CatchmentPoint.id) a procesar.",
        )
        parser.add_argument(
            "--project-legacy-id",
            type=int,
            help="ID legacy del proyecto (ProjectCatchments.id) a procesar.",
        )
        parser.add_argument(
            "--skip-negative",
            action="store_true",
            help="Omitir offsets negativos (default: alertar pero aplicar).",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        point_id = options["point_id"]
        project_id = options["project_legacy_id"]
        skip_negative = options["skip_negative"]

        qs = Point.objects.filter(
            legacy_point__isnull=False,
            device__variable_configs__processing_type="stateful",
        ).distinct()

        if point_id:
            qs = qs.filter(legacy_point_id=point_id)
        if project_id:
            qs = qs.filter(legacy_point__project_id=project_id)

        total_updated = 0
        total_skipped = 0

        for point in qs:
            device = point.device
            legacy_point = point.legacy_point

            # Último InteractionDetail no erróneo.
            last_id = InteractionDetail.objects.filter(
                catchment_point=legacy_point,
            ).exclude(is_error=True).order_by("-date_time_medition").first()

            if not last_id or last_id.total is None or last_id.pulses is None:
                self.stdout.write(
                    self.style.WARNING(f"{point}: sin InteractionDetail válido. Skip.")
                )
                total_skipped += 1
                continue

            legacy_total = Decimal(str(last_id.total))
            legacy_pulses = Decimal(str(last_id.pulses))

            for config in device.variable_configs.filter(processing_type="stateful"):
                pulses_factor = Decimal(config.pulses_factor or 1000)
                raw_total = (legacy_pulses * pulses_factor) / Decimal("1000")
                offset = legacy_total - raw_total

                if skip_negative and offset < 0:
                    self.stdout.write(
                        self.style.WARNING(
                            f"{point} | {config.source_variable}: offset negativo ({offset:.3f}). Skip."
                        )
                    )
                    total_skipped += 1
                    continue

                if not dry_run:
                    # Actualizar config.
                    config.offset = offset
                    config.save(update_fields=["offset"])

                    # Actualizar estado stateful si existe.
                    state, _ = DeviceVariableState.objects.get_or_create(
                        device=device,
                        variable=config.source_variable,
                        defaults={"state": {}},
                    )
                    state.state["offset"] = str(offset)

                    # Si el estado ya tenía un last_total calculado sin offset,
                    # lo ajustamos para mantener coherencia.
                    last_total = state.state.get("last_total")
                    if last_total is not None:
                        try:
                            adjusted = Decimal(str(last_total)) + offset
                            state.state["last_total"] = str(adjusted)
                        except Exception:
                            pass

                    state.save(update_fields=["state"])

                self.stdout.write(
                    self.style.SUCCESS(
                        f"{'[DRY-RUN] ' if dry_run else ''}{point} | {config.source_variable}: "
                        f"legacy_total={legacy_total} raw_total={raw_total} offset={offset:.3f}"
                    )
                )
                total_updated += 1

        self.stdout.write(
            self.style.NOTICE(
                f"Proceso completado: {total_updated} configs actualizadas, {total_skipped} omitidas."
            )
        )
