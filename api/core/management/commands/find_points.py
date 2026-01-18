from django.core.management.base import BaseCommand
from api.telemetry.models.catchment_points import CatchmentPoint

class Command(BaseCommand):
    help = "Busca puntos de captación por título (case-insensitive) y muestra id y título."

    def add_arguments(self, parser):
        parser.add_argument('--q', type=str, required=True, help='Texto a buscar en title')

    def handle(self, *args, **options):
        q = options['q']
        qs = CatchmentPoint.objects.filter(title__icontains=q).order_by('id')
        if not qs.exists():
            self.stdout.write(self.style.WARNING('No se encontraron puntos'))
            return
        for cp in qs:
            self.stdout.write(f"{cp.id}\t{cp.title}")
