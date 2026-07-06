"""Compare void processed readings against legacy InteractionDetail."""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from void.models import Point, ProcessedReading


class Command(BaseCommand):
    help = "Compara lecturas procesadas de void contra legacy (shadow mode)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=1,
            help="Días hacia atrás para comparar.",
        )
        parser.add_argument(
            "--point-id",
            type=int,
            help="Comparar solo un punto void específico.",
        )

    def handle(self, *args, **options):
        days = options["days"]
        point_id = options["point_id"]
        since = timezone.now() - timedelta(days=days)

        qs = Point.objects.filter(migration_status__in=["shadow", "migrated"])
        if point_id:
            qs = qs.filter(pk=point_id)

        total_void = 0
        total_legacy = 0
        differences = 0

        for point in qs:
            if point.legacy_point is None:
                continue

            void_count = ProcessedReading.objects.filter(
                device__point=point,
                timestamp__gte=since,
            ).count()

            from api.core.models import InteractionDetail
            legacy_count = InteractionDetail.objects.filter(
                catchment_point=point.legacy_point,
                date_time_medition__gte=since,
            ).count()

            total_void += void_count
            total_legacy += legacy_count
            if void_count != legacy_count:
                differences += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"Punto {point.id} (legacy {point.legacy_point_id}): "
                        f"void={void_count}, legacy={legacy_count}"
                    )
                )

        self.stdout.write(
            self.style.NOTICE(
                f"Resumen últimos {days} días: void={total_void}, legacy={total_legacy}, "
                f"puntos con diferencias={differences}"
            )
        )
