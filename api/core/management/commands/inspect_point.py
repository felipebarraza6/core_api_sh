from django.core.management.base import BaseCommand
from django.utils import timezone
from api.core.models import InteractionDetail

class Command(BaseCommand):
    help = "Muestra los ultimos N registros de un punto, ordenados por date_time_medition desc."

    def add_arguments(self, parser):
        parser.add_argument("--point", type=int, required=True)
        parser.add_argument("--limit", type=int, default=10)

    def handle(self, *args, **opts):
        pid = opts[point]
        limit = opts[limit]
        qs = (
            InteractionDetail.objects.filter(catchment_point_id=pid)
            .order_by(-date_time_medition, -id)[:limit]
        )
        self.stdout.write(f"Ultimos {qs.count()} registros para punto {pid} (date_time_medition desc):")
        self.stdout.write("date_time_medition | created | pulses | total | total_diff | total_today_diff")
        for r in qs:
            self.stdout.write(f"{r.date_time_medition} | {r.created} | {r.pulses} | {r.total} | {r.total_diff} | {r.total_today_diff}")
