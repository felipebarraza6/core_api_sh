"""
ViewSet unificado para Dashboard.

Consolida la lógica de:
- api/core/views/v2_views.py (DashboardSummaryView, RealtimeDashboardView)
- api/telemetry/views.py (TelemetryViewSet.dashboard_summary)
"""

from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response

from api.unified.services.dashboard_service import DashboardService
from api.unified.services.status_service import StatusService


class DashboardViewSet(viewsets.ViewSet):
    """
    ViewSet para endpoints de dashboard.

    Endpoints:
        GET /dashboard/summary/     - Resumen ejecutivo
        GET /dashboard/realtime/    - Datos en tiempo real
        GET /dashboard/stats/       - Estadísticas del sistema
        GET /dashboard/health/      - Salud del sistema
    """

    permission_classes = [permissions.IsAuthenticated]

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """
        Resumen ejecutivo del dashboard.

        Consolida toda la información relevante en una sola llamada:
        - Información del usuario
        - Lista de puntos con status
        - Estadísticas
        - Alertas activas

        Query params:
            - hours: Horas hacia atrás para estadísticas (default: 24)
        """
        hours_back = int(request.query_params.get('hours', 24))

        summary = DashboardService.get_executive_summary(
            user=request.user,
            hours_back=hours_back
        )

        return Response(summary)

    @action(detail=False, methods=['get'])
    def realtime(self, request):
        """
        Datos en tiempo real para dashboard.

        Query params:
            - point_ids: Lista de IDs separados por coma (opcional)
        """
        point_ids_param = request.query_params.get('point_ids')
        point_ids = None

        if point_ids_param:
            try:
                point_ids = [int(id.strip()) for id in point_ids_param.split(',')]
            except ValueError:
                pass

        realtime_data = DashboardService.get_realtime_data(
            user=request.user,
            point_ids=point_ids
        )

        return Response(realtime_data)

    @action(detail=False, methods=['get'])
    def stats(self, request):
        """
        Estadísticas del sistema.

        Query params:
            - hours: Horas hacia atrás (default: 24)
        """
        hours_back = int(request.query_params.get('hours', 24))

        point_ids = DashboardService.get_user_point_ids(request.user)
        stats = DashboardService._calculate_stats(point_ids, hours_back)

        return Response({
            "user_id": request.user.id,
            "stats": stats,
        })

    @action(detail=False, methods=['get'])
    def health(self, request):
        """
        Salud del sistema completo.

        Para usuarios staff: muestra salud de todos los puntos.
        Para usuarios normales: muestra salud de sus puntos.
        """
        if request.user.is_staff:
            health = StatusService.get_system_health_summary()
        else:
            point_ids = DashboardService.get_user_point_ids(request.user)
            batch_status = StatusService.get_batch_status(point_ids)

            online_count = sum(1 for s in batch_status.values() if s.get("online"))
            total = len(batch_status)

            health = {
                "total_points": total,
                "online_count": online_count,
                "offline_count": total - online_count,
                "error_count": sum(1 for s in batch_status.values() if s.get("is_error")),
                "health_percentage": round((online_count / total) * 100, 1) if total > 0 else 0,
            }

        return Response({
            "user_id": request.user.id,
            "is_staff": request.user.is_staff,
            "health": health,
        })
