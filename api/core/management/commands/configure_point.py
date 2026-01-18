"""
Management command para configurar puntos de telemetría
"""
from django.core.management.base import BaseCommand
from api.core.models import (
    CatchmentPoint,
    ProfileDataConfigCatchment,
    CoreVariable,
)


class Command(BaseCommand):
    help = "Configura un punto de telemetría con token y variables"

    def add_arguments(self, parser):
        parser.add_argument("point_id", type=int, nargs='?', help="ID del punto a configurar")
        parser.add_argument("--token", type=str, help="Token del servicio TWIN")
        parser.add_argument(
            "--addition", type=int, default=0, help="Valor de addition (offset)"
        )
        parser.add_argument(
            "--pulses-factor", type=float, default=1000, help="Factor de pulsos (d1)"
        )
        parser.add_argument(
            "--list", action="store_true", help="Listar puntos disponibles"
        )
        parser.add_argument(
            "--search", type=str, help="Buscar puntos por nombre"
        )

    def handle(self, *args, **options):
        # Listar puntos
        if options["list"]:
            points = CatchmentPoint.objects.all()[:20]
            self.stdout.write("\n📋 Puntos disponibles:")
            for p in points:
                self.stdout.write(f"  ID {p.id}: {p.title}")
            return

        # Buscar puntos
        if options["search"]:
            points = CatchmentPoint.objects.filter(
                title__icontains=options["search"]
            )
            self.stdout.write(f"\n🔍 Encontrados {points.count()} puntos:")
            for p in points:
                self.stdout.write(f"  ID {p.id}: {p.title}")
                if p.project:
                    self.stdout.write(f"    Proyecto: {p.project.name}")
            return

        # Configurar punto
        point_id = options["point_id"]
        try:
            point = CatchmentPoint.objects.get(id=point_id)
        except CatchmentPoint.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f"❌ Punto {point_id} no encontrado")
            )
            return

        self.stdout.write(f"\n📍 Configurando: {point.title} (ID: {point.id})")

        # Obtener o crear perfil
        profile, created = ProfileDataConfigCatchment.objects.get_or_create(
            point_catchment=point
        )

        if created:
            self.stdout.write(self.style.SUCCESS("  ✅ Perfil creado"))

        # Actualizar configuración
        if options["token"]:
            profile.token_service = options["token"]
            self.stdout.write(f"  🔑 Token: {options['token']}")

        if options["addition"]:
            profile.addition = options["addition"]
            self.stdout.write(f"  ➕ Addition: {options['addition']} m³")

        # Activar telemetría
        profile.is_telemetry = True
        profile.save()
        self.stdout.write(self.style.SUCCESS("  ✅ Perfil guardado"))

        self.stdout.write(f"  📊 Factor pulsos: {options['pulses_factor']} (se configura en variable)")

        # Verificar/crear variables
        self.stdout.write("\n📊 Variables:")

        # Variable totalizado
        total_var, created = CoreVariable.objects.get_or_create(
            point=point,
            internal_code="total",
            defaults={
                "name": "Totalizado (m³)",
                "unit": "m³",
                "type_variable": "TOTALIZADO",
                "provider_key": "5000",  # ID Twin para totalizado
                "operation": "PHYSICAL",
                "configuration": {
                    "pulses_factor": options["pulses_factor"],
                    "calculate_nivel": False,
                },
                "priority": 10,
            },
        )
        if created:
            self.stdout.write("  ✅ Variable 'total' creada")
        else:
            total_var.provider_key = "5000"
            total_var.configuration["pulses_factor"] = options["pulses_factor"]
            total_var.save()
            self.stdout.write("  ♻️  Variable 'total' actualizada")

        # Variable caudal
        flow_var, created = CoreVariable.objects.get_or_create(
            point=point,
            internal_code="flow",
            defaults={
                "name": "Caudal (L/s)",
                "unit": "L/s",
                "type_variable": "CAUDAL",
                "provider_key": "5001",  # ID Twin para caudal
                "operation": "PHYSICAL",
                "priority": 20,
            },
        )
        if created:
            self.stdout.write("  ✅ Variable 'flow' creada")
        else:
            flow_var.provider_key = "5001"
            flow_var.save()
            self.stdout.write("  ♻️  Variable 'flow' actualizada")

        self.stdout.write(
            self.style.SUCCESS(f"\n✅ Punto {point.title} configurado correctamente")
        )
