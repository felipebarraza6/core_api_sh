"""
DashboardService - Servicio centralizado para agregación de datos del dashboard.

Reemplaza lógica duplicada en:
- api/core/views/v2_views.py (DashboardSummaryView)
- api/telemetry/views.py (TelemetryViewSet.dashboard_summary)
"""

from datetime import timedelta
from typing import Dict, List, Optional, Any

from django.db.models import Q, Count, Max
from django.utils import timezone

from api.unified.services.status_service import StatusService


class DashboardService:
    """Servicio centralizado para agregación de datos del dashboard."""

    @staticmethod
    def get_user_point_ids(user) -> List[int]:
        """
        Obtiene los IDs de puntos accesibles por un usuario.

        Args:
            user: Usuario Django

        Returns:
            Lista de IDs de puntos
        """
        from api.telemetry.models.catchment_points import CatchmentPoint

        if user.is_staff:
            return list(
                CatchmentPoint.objects
                .filter(is_active=True)
                .values_list('id', flat=True)
            )

        return list(
            CatchmentPoint.objects
            .filter(is_active=True)
            .filter(Q(owner_user=user) | Q(users_viewers=user))
            .distinct()
            .values_list('id', flat=True)
        )

    @staticmethod
    def get_executive_summary(user, hours_back: int = 24) -> Dict[str, Any]:
        """
        Genera resumen ejecutivo del dashboard.

        Consolida la lógica de DashboardSummaryView y TelemetryViewSet.dashboard_summary

        Args:
            user: Usuario Django
            hours_back: Horas hacia atrás para estadísticas

        Returns:
            Dict con: user, points, stats, alerts, last_updated
        """
        point_ids = DashboardService.get_user_point_ids(user)

        if not point_ids:
            return DashboardService._empty_dashboard(user)

        # Obtener datos en paralelo (queries optimizadas)
        batch_status = StatusService.get_batch_status(point_ids)
        points_data = DashboardService._get_points_summary(point_ids, batch_status)
        stats = DashboardService._calculate_stats(point_ids, hours_back)
        alerts = DashboardService._get_active_alerts(point_ids)

        return {
            "user": DashboardService._format_user(user),
            "points": points_data,
            "stats": stats,
            "alerts": alerts,
            "last_updated": timezone.now().isoformat(),
            "status": "ready",
        }

    @staticmethod
    def get_realtime_data(
        user,
        point_ids: Optional[List[int]] = None
    ) -> Dict[str, Any]:
        """
        Datos en tiempo real para dashboard.

        Args:
            user: Usuario Django
            point_ids: Lista opcional de IDs (si None, usa todos los del usuario)

        Returns:
            Dict con datos en tiempo real por punto
        """
        from api.telemetry.models import TelemetryRecord

        if point_ids is None:
            point_ids = DashboardService.get_user_point_ids(user)

        if not point_ids:
            return {"points": [], "last_updated": timezone.now().isoformat()}

        # Obtener últimos registros
        latest_records = {}
        for point_id in point_ids:
            record = (
                TelemetryRecord.objects
                .filter(point_id=point_id)
                .select_related('point')
                .order_by('-timestamp')
                .first()
            )
            if record:
                latest_records[point_id] = {
                    "point_id": point_id,
                    "point_title": record.point.title,
                    "timestamp": record.timestamp.isoformat(),
                    "data": record.data,
                    "is_error": record.is_error,
                    "flow": record.flow,
                    "total": record.total,
                    "nivel": record.nivel,
                }

        # Agregar status
        batch_status = StatusService.get_batch_status(point_ids)

        result = []
        for point_id in point_ids:
            point_data = latest_records.get(point_id, {"point_id": point_id})
            point_data["status"] = batch_status.get(point_id, {"online": False})
            result.append(point_data)

        return {
            "points": result,
            "last_updated": timezone.now().isoformat(),
        }

    @staticmethod
    def _empty_dashboard(user) -> Dict[str, Any]:
        """Retorna dashboard vacío para usuarios sin puntos."""
        return {
            "user": DashboardService._format_user(user),
            "points": [],
            "stats": {
                "total_points": 0,
                "online_count": 0,
                "offline_count": 0,
                "records_24h": 0,
            },
            "alerts": [],
            "last_updated": timezone.now().isoformat(),
            "status": "empty",
        }

    @staticmethod
    def _format_user(user) -> Dict[str, Any]:
        """Formatea datos del usuario para respuesta."""
        return {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "is_staff": user.is_staff,
        }

    @staticmethod
    def _get_points_summary(
        point_ids: List[int],
        batch_status: Dict[int, Dict]
    ) -> List[Dict[str, Any]]:
        """Obtiene resumen de puntos con su status."""
        from api.telemetry.models.catchment_points import CatchmentPoint

        points = (
            CatchmentPoint.objects
            .filter(id__in=point_ids)
            .select_related('project', 'project__client', 'device')
        )

        result = []
        for point in points:
            status = batch_status.get(point.id, {"online": False})
            result.append({
                "id": point.id,
                "title": point.title,
                "point_code": point.point_code,
                "lat": point.lat,
                "lon": point.lon,
                "is_active": point.is_active,
                "client_name": point.project.client.name if point.project and point.project.client else None,
                "project_name": point.project.name if point.project else None,
                "device_name": point.device.name if point.device else None,
                "status": status,
            })

        return result

    @staticmethod
    def _calculate_stats(point_ids: List[int], hours_back: int) -> Dict[str, Any]:
        """Calcula estadísticas de los puntos."""
        from api.telemetry.models import TelemetryRecord

        batch_status = StatusService.get_batch_status(point_ids)

        online_count = sum(1 for s in batch_status.values() if s.get("online"))

        # Contar registros en las últimas horas
        since = timezone.now() - timedelta(hours=hours_back)
        records_count = TelemetryRecord.objects.filter(
            point_id__in=point_ids,
            timestamp__gte=since
        ).count()

        return {
            "total_points": len(point_ids),
            "online_count": online_count,
            "offline_count": len(point_ids) - online_count,
            "records_24h": records_count,
            "health_percentage": round((online_count / len(point_ids)) * 100, 1) if point_ids else 0,
        }

    @staticmethod
    def _get_active_alerts(point_ids: List[int]) -> List[Dict[str, Any]]:
        """Obtiene alertas activas para los puntos."""
        from api.notifications.models import Notification

        try:
            alerts = (
                Notification.objects
                .filter(
                    catchment_point_id__in=point_ids,
                    is_active=True,
                    is_read=False
                )
                .order_by('-created')[:10]
            )

            return [
                {
                    "id": alert.id,
                    "point_id": alert.catchment_point_id,
                    "message": alert.message,
                    "level": alert.level,
                    "created": alert.created.isoformat(),
                }
                for alert in alerts
            ]
        except Exception:
            # Si el modelo de notificaciones no existe o hay error
            return []
