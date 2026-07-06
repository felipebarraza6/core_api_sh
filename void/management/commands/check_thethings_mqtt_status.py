"""
Comando de management para revisar el estado de puntos TheThings.io
en la transición de polling REST a MQTT.

Uso:
    python manage.py check_thethings_mqtt_status --points 3,12,22
    python manage.py check_thethings_mqtt_status --points 3
"""

from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from api.core.models import CatchmentPoint, InteractionDetail, ProfileDataConfigCatchment
from api.core.models.telemetry_providers import TelemetryProvider


class Command(BaseCommand):
    help = "Revisa estado de puntos TheThings.io para validación MQTT"

    def add_arguments(self, parser):
        parser.add_argument(
            "--points",
            required=True,
            help="IDs de puntos separados por coma, ej. 3,12,22",
        )
        parser.add_argument(
            "--hours",
            type=int,
            default=24,
            help="Ventana de horas hacia atrás para contar registros (default: 24)",
        )

    def handle(self, *args, **options):
        points_str = options["points"]
        hours = options["hours"]

        try:
            point_ids = [int(x.strip()) for x in points_str.split(",") if x.strip()]
        except ValueError:
            raise CommandError("--points debe ser una lista de números separados por coma")

        # Revisar que TheThings.io esté activo como proveedor
        thethings_provider = TelemetryProvider.objects.filter(
            handler_name="thethings", is_active=True
        ).first()
        if not thethings_provider:
            self.stdout.write(
                self.style.WARNING("No hay proveedor TelemetryProvider activo con handler_name='thethings'")
            )

        since = timezone.now() - timedelta(hours=hours)

        for point_id in point_ids:
            self._check_point(point_id, since, hours)
            self.stdout.write("")

    def _check_point(self, point_id: int, since, hours: int):
        point = CatchmentPoint.objects.filter(id=point_id).first()
        if not point:
            self.stdout.write(self.style.ERROR(f"Punto {point_id}: no existe"))
            return

        profile = ProfileDataConfigCatchment.objects.filter(
            point_catchment=point
        ).select_related("point_catchment").first()

        token = profile.token_service if profile else None
        polling_off = profile.disable_thethings_polling if profile else False

        self.stdout.write(
            self.style.NOTICE(
                f"=== Punto {point_id}: {point.title} ==="
            )
        )
        self.stdout.write(f"  Token:           {self._mask(token) if token else 'SIN TOKEN'}")
        self.stdout.write(f"  is_thethings:    {point.is_thethings}")
        self.stdout.write(f"  Polling REST:    {'DESACTIVADO' if polling_off else 'ACTIVADO'}")

        # Variables del esquema
        schemes = list(point.schemes.all())
        if schemes:
            for scheme in schemes:
                vars_list = [f"{v.str_variable}({v.type_variable})" for v in scheme.variables.all()]
                self.stdout.write(f"  Esquema '{scheme.name}': {', '.join(vars_list)}")
        else:
            self.stdout.write(self.style.WARNING("  Sin esquema asociado"))

        # Último registro
        latest = InteractionDetail.objects.filter(
            catchment_point=point
        ).order_by("-date_time_medition").first()

        if latest:
            self.stdout.write(f"  Último registro: {latest.date_time_medition} UTC")
            self.stdout.write(f"    total={latest.total}, flow={latest.flow}, nivel={latest.nivel}")
            self.stdout.write(f"    send_dga={latest.send_dga}, is_error={latest.is_error}")
            self.stdout.write(f"    variable_values: {latest.variable_values}")
        else:
            self.stdout.write(self.style.WARNING("  Sin registros en InteractionDetail"))

        # Registros en ventana
        count = InteractionDetail.objects.filter(
            catchment_point=point,
            date_time_medition__gte=since,
        ).count()
        self.stdout.write(f"  Registros últimas {hours}h: {count}")

        # Alerta si no hay registros recientes
        if latest and latest.date_time_medition < since:
            self.stdout.write(
                self.style.WARNING(
                    f"  ALERTA: último registro es anterior a {since}"
                )
            )

    def _mask(self, token: str) -> str:
        if not token:
            return ""
        if len(token) <= 12:
            return "***"
        return f"{token[:8]}..."
