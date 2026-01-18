from django.core.management.base import BaseCommand
from django.utils import timezone
from api.core.models import TelemetryRecord

class Command(BaseCommand):
    help = "Muestra los ultimos N registros de un punto, ordenados por timestamp desc."

    def add_arguments(self, parser):
        parser.add_argument("--point", type=int, required=True)
        parser.add_argument("--limit", type=int, default=10)

    def handle(self, *args, **opts):
        pid = opts['point']
        limit = opts['limit']
        qs = (
            TelemetryRecord.objects.filter(point_id=pid)
            .order_by('-timestamp', '-id')[:limit]
        )
        self.stdout.write(f"Ultimos {qs.count()} registros V3 para punto {pid} (timestamp desc):")
        self.stdout.write("timestamp | created | pulses | total | total_diff | total_today_diff")
        for r in qs:
            data = r.data
            timestamp = r.timestamp
            created = r.created
            pulses = data.get('pulses', 0)
            total = data.get('total', 0)
            total_diff = data.get('total_diff', 0)
            total_today_diff = data.get('total_today_diff', 0)
            
            self.stdout.write(f"{timestamp} | {created} | {pulses} | {total} | {total_diff} | {total_today_diff}")
