"""Point service for void."""
from typing import Optional

from django.db.models import QuerySet

from void.models import Point, PointPermission, VoidUserProfile


class PointService:
    """Servicio unificado de gestión y consulta de puntos."""

    def get_points_for_user(self, user) -> QuerySet:
        """Retorna queryset de puntos accesibles para el usuario."""
        profile = getattr(user, "void_profile", None)
        if profile is None:
            return Point.objects.none()

        if profile.role in {"admin", "operator"}:
            return Point.objects.all()

        allowed_group_ids = PointPermission.objects.filter(
            user=profile,
            permission__in={"view", "change", "admin"},
        ).values_list("group_id", flat=True)

        return Point.objects.filter(groups__id__in=allowed_group_ids).distinct()

    def can_edit_point(self, user, point: Point) -> bool:
        """Retorna True si el usuario puede editar el punto."""
        profile = getattr(user, "void_profile", None)
        if profile is None:
            return False
        if profile.role in {"admin", "operator"}:
            return True
        if profile.role != "client_admin":
            return False
        group_ids = point.groups.values_list("id", flat=True)
        return PointPermission.objects.filter(
            user=profile,
            group_id__in=group_ids,
            permission__in={"change", "admin"},
        ).exists()

    def get_point_summary(self, point_id: int) -> Optional[dict]:
        """Retorna resumen completo de un punto."""
        try:
            point = Point.objects.select_related(
                "client_fk",
                "project_fk",
                "device__provider",
            ).get(pk=point_id)
        except Point.DoesNotExist:
            return None

        device = getattr(point, "device", None)
        provider = getattr(device, "provider", None)

        last_reading = None
        if device is not None:
            reading = device.processed_readings.order_by("-timestamp").first()
            if reading is not None:
                last_reading = {
                    "timestamp": reading.timestamp.isoformat(),
                    "total": str(reading.total) if reading.total is not None else None,
                    "flow": str(reading.flow) if reading.flow is not None else None,
                    "nivel": str(reading.nivel) if reading.nivel is not None else None,
                    "water_table": str(reading.water_table) if reading.water_table is not None else None,
                }

        return {
            "id": point.id,
            "name": point.name,
            "code_internal": point.code_internal,
            "client": point.client_fk.name if point.client_fk else None,
            "project": point.project_fk.name if point.project_fk else None,
            "frequency_minutes": point.frequency_minutes,
            "is_active": point.is_active,
            "migration_status": point.migration_status,
            "device": {
                "id": device.id if device else None,
                "serial_number": device.serial_number if device else None,
                "provider": provider.name if provider else None,
            },
            "last_reading": last_reading,
        }

    def get_point_config(self, point_id: int) -> Optional[dict]:
        """Retorna configuración del punto + variables del device."""
        try:
            point = Point.objects.select_related("device").get(pk=point_id)
        except Point.DoesNotExist:
            return None

        device = getattr(point, "device", None)
        configs = []
        if device is not None:
            configs = [
                {
                    "id": c.id,
                    "source_variable": c.source_variable,
                    "internal_variable": c.internal_variable,
                    "processing_type": c.processing_type,
                    "pulses_factor": c.pulses_factor,
                    "offset": str(c.offset),
                    "scale": str(c.scale),
                    "compute_flow": c.compute_flow,
                    "formula": c.formula,
                    "is_active": c.is_active,
                }
                for c in device.variable_configs.all()
            ]

        return {
            "point_id": point.id,
            "constants": point.constants,
            "frequency_minutes": point.frequency_minutes,
            "replicate_on_missing": point.replicate_on_missing,
            "max_replication_hours": point.max_replication_hours,
            "variable_configs": configs,
        }

    def update_point_config(self, point: Point, data: dict) -> Point:
        """Actualiza campos de configuración de un punto."""
        allowed = {
            "name",
            "code_internal",
            "description",
            "lat",
            "lon",
            "frequency_minutes",
            "is_active",
            "constants",
            "replicate_on_missing",
            "max_replication_hours",
            "extra_data",
            "client_fk",
            "project_fk",
        }
        for key, value in data.items():
            if key in allowed:
                setattr(point, key, value)
        point.save(update_fields=list(data.keys()) & allowed)
        return point
