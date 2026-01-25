"""
StatusService - Servicio centralizado para determinar estado de entidades.

Reemplaza lógica duplicada en:
- api/core/views/v2_views.py (_check_point_online, _get_last_reading_time)
- api/telemetry/serializers.py (UnifiedCatchmentPointSerializer.get_status)
- api/core/views/v3_views.py (SystemStatusDynamicView)
"""

from datetime import timedelta
from typing import Dict, List, Optional, Any

from django.db.models import Max
from django.utils import timezone


class StatusService:
    """Servicio centralizado para determinar estado online/offline de entidades."""

    DEFAULT_THRESHOLD_MINUTES = 10

    @staticmethod
    def get_point_status(
        point_id: int,
        threshold_minutes: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Determina si un punto está online basado en su última lectura.

        Args:
            point_id: ID del punto de captación
            threshold_minutes: Minutos para considerar offline (default: frequency * 2)

        Returns:
            Dict con: online, last_seen, is_error, offline_reason, last_record_id
        """
        from api.telemetry.models import TelemetryRecord
        from api.telemetry.models.catchment_points import CatchmentPoint

        try:
            point = CatchmentPoint.objects.get(id=point_id)
        except CatchmentPoint.DoesNotExist:
            return {
                "online": False,
                "last_seen": None,
                "is_error": True,
                "offline_reason": "POINT_NOT_FOUND",
                "last_record_id": None,
            }

        # Calcular threshold dinámico basado en frecuencia del punto
        if threshold_minutes is None:
            threshold_minutes = point.frequency_minutes * 2
            if threshold_minutes < StatusService.DEFAULT_THRESHOLD_MINUTES:
                threshold_minutes = StatusService.DEFAULT_THRESHOLD_MINUTES

        # Obtener último registro
        last_record = (
            TelemetryRecord.objects
            .filter(point_id=point_id)
            .order_by('-timestamp')
            .first()
        )

        if not last_record:
            return {
                "online": False,
                "last_seen": None,
                "is_error": False,
                "offline_reason": "NO_DATA",
                "last_record_id": None,
            }

        # Calcular si está online
        threshold_time = timezone.now() - timedelta(minutes=threshold_minutes)
        is_online = last_record.timestamp >= threshold_time

        return {
            "online": is_online,
            "last_seen": last_record.timestamp.isoformat(),
            "is_error": last_record.is_error,
            "offline_reason": None if is_online else "TIMEOUT",
            "last_record_id": last_record.id,
        }

    @staticmethod
    def get_device_status(device_id: int) -> Dict[str, Any]:
        """
        Determina estado de un dispositivo.

        Args:
            device_id: ID del dispositivo

        Returns:
            Dict con: online, last_seen, status, points_count
        """
        from api.infrastructure.models import Device

        try:
            device = Device.objects.get(id=device_id)
        except Device.DoesNotExist:
            return {
                "online": False,
                "last_seen": None,
                "status": "NOT_FOUND",
                "points_count": 0,
            }

        # Contar puntos asociados
        points_count = device.catchment_points.filter(is_active=True).count()

        return {
            "online": device.status == "ONLINE",
            "last_seen": device.last_seen.isoformat() if device.last_seen else None,
            "status": device.status,
            "points_count": points_count,
        }

    @staticmethod
    def get_batch_status(
        point_ids: List[int],
        threshold_minutes: Optional[int] = None
    ) -> Dict[int, Dict[str, Any]]:
        """
        Estado de múltiples puntos en una sola consulta optimizada.

        Args:
            point_ids: Lista de IDs de puntos
            threshold_minutes: Threshold común (si None, usa frecuencia de cada punto)

        Returns:
            Dict con point_id como key y status como value
        """
        from api.telemetry.models import TelemetryRecord
        from api.telemetry.models.catchment_points import CatchmentPoint

        if not point_ids:
            return {}

        # Obtener puntos con su frecuencia
        points = CatchmentPoint.objects.filter(id__in=point_ids).select_related('frequency')
        points_dict = {p.id: p for p in points}

        # Obtener última lectura de cada punto en una sola query
        last_records = (
            TelemetryRecord.objects
            .filter(point_id__in=point_ids)
            .values('point_id')
            .annotate(
                last_timestamp=Max('timestamp'),
            )
        )
        last_records_dict = {r['point_id']: r['last_timestamp'] for r in last_records}

        # Construir resultado
        result = {}
        now = timezone.now()

        for point_id in point_ids:
            point = points_dict.get(point_id)
            last_timestamp = last_records_dict.get(point_id)

            if not point:
                result[point_id] = {
                    "online": False,
                    "last_seen": None,
                    "is_error": False,
                    "offline_reason": "POINT_NOT_FOUND",
                }
                continue

            if not last_timestamp:
                result[point_id] = {
                    "online": False,
                    "last_seen": None,
                    "is_error": False,
                    "offline_reason": "NO_DATA",
                }
                continue

            # Calcular threshold
            if threshold_minutes:
                th = threshold_minutes
            else:
                th = point.frequency_minutes * 2
                if th < StatusService.DEFAULT_THRESHOLD_MINUTES:
                    th = StatusService.DEFAULT_THRESHOLD_MINUTES

            threshold_time = now - timedelta(minutes=th)
            is_online = last_timestamp >= threshold_time

            result[point_id] = {
                "online": is_online,
                "last_seen": last_timestamp.isoformat(),
                "is_error": False,
                "offline_reason": None if is_online else "TIMEOUT",
            }

        return result

    @staticmethod
    def get_system_health_summary() -> Dict[str, Any]:
        """
        Resumen de salud del sistema completo.

        Returns:
            Dict con estadísticas globales de online/offline
        """
        from api.telemetry.models.catchment_points import CatchmentPoint

        # Obtener todos los puntos activos
        active_points = CatchmentPoint.objects.filter(is_active=True).values_list('id', flat=True)

        if not active_points:
            return {
                "total_points": 0,
                "online_count": 0,
                "offline_count": 0,
                "error_count": 0,
                "health_percentage": 0,
            }

        # Obtener estado de todos
        batch_status = StatusService.get_batch_status(list(active_points))

        online_count = sum(1 for s in batch_status.values() if s.get("online"))
        error_count = sum(1 for s in batch_status.values() if s.get("is_error"))
        total = len(batch_status)

        return {
            "total_points": total,
            "online_count": online_count,
            "offline_count": total - online_count,
            "error_count": error_count,
            "health_percentage": round((online_count / total) * 100, 1) if total > 0 else 0,
        }
