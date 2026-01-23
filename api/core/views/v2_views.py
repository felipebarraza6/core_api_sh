"""
API V2 - Endpoints Granulares y Optimizados.
Resuelve problemas de carga de datos del frontend actual.
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.utils import timezone
from django.db.models import Count, Avg, Max, Q
from datetime import timedelta

from api.telemetry.services.telemetry_service import TelemetryService
from api.core.services.stats_service import StatsService
from api.core.services.action_service import ActionService
from api.telemetry.models.catchment_points import CatchmentPoint
from api.compliance.models import PointComplianceConfig
from api.telemetry.models.telemetry import TelemetryRecord
from api.infrastructure.models import Device
from api.crm.models import Client, Project
from api.notifications.models import Notification


class DashboardSummaryView(APIView):
    """
    Dashboard Ejecutivo - Un solo endpoint para todo lo necesario.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        GET /api/v2/dashboard/summary/
        Retorna resumen completo del dashboard en UNA sola llamada.
        """
        user = request.user

        if not ActionService.user_can_perform_action(user, 'DASHBOARD_VIEW'):
            return Response(
                {"error": "No tienes permisos para ver el dashboard"},
                status=status.HTTP_403_FORBIDDEN
            )

        try:
            user_points = self._get_user_points(user)
            point_ids = [p['id'] for p in user_points]

            if not point_ids:
                return Response({
                    "user": self._format_user_data(user),
                    "points": [],
                    "telemetry": {},
                    "stats": StatsService.get_empty_stats(),
                    "alerts": [],
                    "system_status": "no_points"
                })

            telemetry_data = TelemetryService.get_batch_telemetry_data(
                point_ids, hours_back=24, user=user
            )

            alerts_data = self._get_active_alerts(point_ids)
            system_stats = StatsService.get_realtime_stats()
            user_permissions = ActionService.get_user_permissions_summary(user)

            return Response({
                "user": self._format_user_data(user),
                "points": user_points,
                "telemetry": telemetry_data,
                "stats": system_stats,
                "alerts": alerts_data,
                "permissions": user_permissions,
                "last_updated": timezone.now().isoformat(),
                "data_freshness": "realtime"
            })

        except Exception as exc:
            return Response(
                {"error": f"Error obteniendo datos del dashboard: {str(exc)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _get_user_points(self, user):
        """Obtener puntos del usuario con datos optimizados."""
        if user.is_staff:
            points = CatchmentPoint.objects.select_related(
                'project', 'project__client'
            ).order_by('project__client__name', 'project__name', 'title')
        else:
            points = CatchmentPoint.objects.filter(
                Q(owner_user=user) | Q(users_viewers=user)
            ).select_related('project', 'project__client').distinct()

        return [{
            'id': p.id,
            'title': p.title,
            'project': p.project.name if p.project else None,
            'client': p.project.client.name if p.project and p.project.client else None,
            'is_online': self._check_point_online(p.id),
            'last_reading': self._get_last_reading_time(p.id)
        } for p in points]

    def _check_point_online(self, point_id):
        """Verificar si un punto está online."""
        one_hour_ago = timezone.now() - timedelta(hours=1)
        return TelemetryRecord.objects.filter(
            point_id=point_id,
            timestamp__gte=one_hour_ago
        ).exists()

    def _get_last_reading_time(self, point_id):
        """Obtener timestamp de última lectura."""
        last_reading = TelemetryRecord.objects.filter(
            point_id=point_id
        ).aggregate(last_time=Max('timestamp'))

        return last_reading['last_time'].isoformat() if last_reading['last_time'] else None

    def _get_active_alerts(self, point_ids):
        """Obtener alertas activas para los puntos."""
        alerts = Notification.objects.filter(
            point_catchment_id__in=point_ids,
            is_active=True,
            is_read=False
        ).select_related('point_catchment').order_by('-created')[:10]

        return [{
            'id': alert.id,
            'point_id': alert.point_catchment.id,
            'point_name': alert.point_catchment.title,
            'title': alert.title,
            'message': alert.message[:100] + '...' if len(alert.message) > 100 else alert.message,
            'type': alert.type_notification,
            'severity': alert.type_notification,
            'created': alert.created.isoformat()
        } for alert in alerts]

    def _format_user_data(self, user):
        """Formatear datos del usuario."""
        return {
            'id': user.id,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'is_staff': user.is_staff,
            'last_login': user.last_login.isoformat() if user.last_login else None
        }


class OptimizedBatchTelemetryView(APIView):
    """
    Telemetría Batch Optimizada.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """
        POST /api/v2/telemetry/batch/
        """
        point_ids = request.data.get('point_ids', [])
        hours_back = min(request.data.get('hours_back', 24), 168)
        include_stats = request.data.get('include_stats', False)
        include_trends = request.data.get('include_trends', False)

        if not point_ids or len(point_ids) > 50:
            return Response(
                {"error": "point_ids required (max 50)"},
                status=status.HTTP_400_BAD_REQUEST
            )

        point_ids = TelemetryService.validate_user_access_to_points(request.user, point_ids)
        if not point_ids:
            return Response({"error": "No access to requested points"})

        try:
            telemetry_data = TelemetryService.get_batch_telemetry_data(
                point_ids, hours_back, request.user
            )

            response_data = {
                "telemetry": telemetry_data,
                "metadata": {
                    "points_requested": len(request.data.get('point_ids', [])),
                    "points_returned": len(telemetry_data),
                    "hours_window": hours_back,
                    "timestamp": timezone.now().isoformat()
                }
            }

            if include_stats:
                stats_data = TelemetryService.get_aggregated_stats(point_ids, hours_back)
                response_data["stats"] = stats_data

            if include_trends:
                trends_data = self._calculate_trends(point_ids, hours_back)
                response_data["trends"] = trends_data

            return Response(response_data)

        except Exception as exc:
            return Response(
                {"error": f"Error obteniendo datos de telemetría: {str(exc)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _calculate_trends(self, point_ids, hours_back):
        """Calcular tendencias simples para los puntos."""
        trends = {}
        for point_id in point_ids:
            try:
                current_period = timezone.now() - timedelta(hours=hours_back)
                previous_period = current_period - timedelta(hours=hours_back)

                current_data = TelemetryRecord.objects.filter(
                    point_id=point_id,
                    timestamp__gte=current_period
                ).aggregate(
                    avg_flow=Avg('data__flow'),
                    avg_level=Avg('data__nivel'),
                    count=Count('id')
                )

                previous_data = TelemetryRecord.objects.filter(
                    point_id=point_id,
                    timestamp__gte=previous_period,
                    timestamp__lt=current_period
                ).aggregate(
                    avg_flow=Avg('data__flow'),
                    avg_level=Avg('data__nivel'),
                    count=Count('id')
                )

                trends[str(point_id)] = {
                    'flow_change_percent': self._calculate_percent_change(
                        current_data['avg_flow'], previous_data['avg_flow']
                    ),
                    'level_change_percent': self._calculate_percent_change(
                        current_data['avg_level'], previous_data['avg_level']
                    ),
                    'data_points_current': current_data['count'],
                    'data_points_previous': previous_data['count']
                }
            except Exception as exc:
                trends[str(point_id)] = {'error': str(exc)}
        return trends

    def _calculate_percent_change(self, current, previous):
        if not previous or previous == 0:
            return None
        return ((current - previous) / previous) * 100 if current else 0


class RealtimeDashboardView(APIView):
    """
    Dashboard en Tiempo Real.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        point_ids = request.GET.getlist('point_ids', [])
        user_points = TelemetryService.validate_user_access_to_points(user, [int(pid) for pid in point_ids] if point_ids else [])

        if not user_points:
            return Response({"data": [], "timestamp": timezone.now().isoformat()})

        realtime_data = []
        for point_id in user_points:
            latest = TelemetryRecord.objects.filter(
                point_id=point_id
            ).select_related('point').order_by('-timestamp').first()

            if latest:
                data = latest.data
                realtime_data.append({
                    'point_id': point_id,
                    'point_name': latest.point.title,
                    'timestamp': latest.timestamp.isoformat(),
                    'flow': float(data.get('flow', data.get('caudal', 0))),
                    'level': float(data.get('nivel', 0)),
                    'status': 'error' if latest.is_error else 'ok',
                    'is_online': self._is_point_online(point_id)
                })

        return Response({
            "data": realtime_data,
            "timestamp": timezone.now().isoformat()
        })

    def _is_point_online(self, point_id):
        five_minutes_ago = timezone.now() - timedelta(minutes=5)
        return TelemetryRecord.objects.filter(
            point_id=point_id,
            timestamp__gte=five_minutes_ago
        ).exists()


class UserActionControlView(APIView):
    """
    Control de Acciones del Usuario.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        permissions = ActionService.get_user_permissions_summary(user)
        return Response({
            "user_id": user.id,
            "permissions": permissions,
            "available_actions": ActionService.get_available_actions()
        })

    def post(self, request):
        user = request.user
        action_code = request.data.get('action')
        resource_id = request.data.get('resource_id')
        params = request.data.get('params', {})

        if not action_code:
            return Response({"error": "action code required"}, status=status.HTTP_400_BAD_REQUEST)

        if not ActionService.user_can_perform_action(user, action_code, resource_id):
            return Response({"error": "Insufficient permissions"}, status=status.HTTP_403_FORBIDDEN)

        try:
            result = self._execute_action(user, action_code, resource_id, params)
            ActionService.log_user_action(user, action_code, resource_id, {'params': params, 'result': 'success'})
            return Response({
                "action": action_code,
                "resource_id": resource_id,
                "result": result,
                "timestamp": timezone.now().isoformat()
            })
        except Exception as exc:
            return Response({"error": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def _execute_action(self, user, action_code, resource_id, params):
        if action_code == 'DGA_SEND':
            return self._toggle_dga_send(user, resource_id, params.get('enable', True))
        elif action_code == 'REPORTS_GENERATE':
            return self._generate_user_report(user, params)
        elif action_code == 'ALERTS_MANAGE':
            return self._manage_alerts(user, resource_id, params)
        else:
            raise ValueError(f"Unknown action: {action_code}")

    def _toggle_dga_send(self, user, point_id, enable):
        config = PointComplianceConfig.objects.filter(
            point_id=point_id, 
            provider__name='dga'
        ).first()
        if not config:
            raise ValueError(f"No DGA configuration found for point {point_id}")
        config.send_compliance = enable
        config.save()
        return {"message": f"DGA {'enabled' if enable else 'disabled'}", "point_id": point_id}

    def _generate_user_report(self, user, params):
        from api.telemetry.tasks.reports import generate_custom_report
        task = generate_custom_report.delay(user_id=user.id, report_type=params.get('type', 'summary'))
        return {"message": "Report generation started", "task_id": task.id}

    def _manage_alerts(self, user, point_id, params):
        action = params.get('action', 'list')
        if action == 'list':
            alerts = Notification.objects.filter(point_catchment_id=point_id, is_active=True).values('id', 'title')
            return {"alerts": list(alerts)}
        elif action in ['activate', 'deactivate']:
            alert_ids = params.get('alert_ids', [])
            Notification.objects.filter(id__in=alert_ids).update(is_active=(action == 'activate'))
            return {"message": f"Alerts {action}d"}


class SystemStatsView(APIView):
    """
    Estadísticas del Sistema en Tiempo Real.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        if not user.is_staff and not ActionService.user_can_perform_action(user, 'SYSTEM_STATS_VIEW'):
            return Response({"error": "No permission"}, status=status.HTTP_403_FORBIDDEN)

        try:
            stats = StatsService.get_realtime_stats()
            return Response({"system_stats": stats, "timestamp": timezone.now().isoformat()})
        except Exception as exc:
            return Response({"error": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)