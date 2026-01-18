"""
API V2 - Endpoints Granulares y Optimizados
Resuelve problemas de carga de datos del frontend actual
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.utils import timezone
from django.db.models import Count, Sum, Avg, Max, Min, Q
from datetime import timedelta
import json

from api.telemetry.services.telemetry_service import TelemetryService
from ..services.stats_service import StatsService
from ..services.action_service import ActionService
from api.telemetry.models import (
    CatchmentPoint, Client, TelemetryRecord, SystemConfiguration, AlertRule, IoTDevice
)


class DashboardSummaryView(APIView):
    """
    Dashboard Ejecutivo - Un solo endpoint para todo lo necesario
    Reemplaza 5-10 llamadas individuales del frontend actual
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        GET /api/v2/dashboard/summary/
        Retorna resumen completo del dashboard en UNA sola llamada
        """
        user = request.user

        # Verificar permisos
        if not ActionService.user_can_perform_action(user, 'DASHBOARD_VIEW'):
            return Response(
                {"error": "No tienes permisos para ver el dashboard"},
                status=status.HTTP_403_FORBIDDEN
            )

        try:
            # Obtener datos del usuario y sus puntos
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

            # Obtener datos en paralelo (no secuencial como hace el frontend actual)
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
        """Obtener puntos del usuario con datos optimizados"""
        if user.is_staff:
            # Staff ve todos los puntos
            points = CatchmentPoint.objects.select_related(
                'project', 'project__client'
            ).order_by('project__client__name', 'project__name', 'title')
        else:
            # Usuario normal ve solo sus puntos
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
        """Verificar si un punto está online (lectura en última hora)"""
        one_hour_ago = timezone.now() - timedelta(hours=1)
        return TelemetryRecord.objects.filter(
            point_id=point_id,
            timestamp__gte=one_hour_ago
        ).exists()

    def _get_last_reading_time(self, point_id):
        """Obtener timestamp de última lectura"""
        last_reading = TelemetryRecord.objects.filter(
            point_id=point_id
        ).aggregate(last_time=Max('timestamp'))

        return last_reading['last_time'].isoformat() if last_reading['last_time'] else None

    def _get_active_alerts(self, point_ids):
        """Obtener alertas activas para los puntos"""
        from ..models import NotificationsCatchment

        alerts = NotificationsCatchment.objects.filter(
            point_catchment_id__in=point_ids,
            is_active=True,
            is_read=False
        ).select_related('point_catchment').order_by('-created')[:10]  # Últimas 10

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
        """Formatear datos del usuario"""
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
    Telemetría Batch Optimizada - Versión mejorada del batch actual
    Reduce llamadas del frontend de N a 1
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """
        POST /api/v2/telemetry/batch/
        Body: {
            "point_ids": [1, 2, 3, 4, 5],
            "hours_back": 24,
            "metrics": ["flow", "level", "total"],  // Opcional: qué métricas incluir
            "include_stats": true,  // Incluir estadísticas agregadas
            "include_trends": false  // Incluir análisis de tendencias
        }
        """
        point_ids = request.data.get('point_ids', [])
        hours_back = min(request.data.get('hours_back', 24), 168)  # Máx 7 días
        metrics = request.data.get('metrics', ['flow', 'level', 'total'])
        include_stats = request.data.get('include_stats', False)
        include_trends = request.data.get('include_trends', False)

        if not point_ids or len(point_ids) > 50:
            return Response(
                {"error": "point_ids required (max 50)"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validar acceso del usuario
        point_ids = TelemetryService.validate_user_access_to_points(request.user, point_ids)
        if not point_ids:
            return Response({"error": "No access to requested points"})

        try:
            # Obtener datos de telemetría
            telemetry_data = TelemetryService.get_batch_telemetry_data(
                point_ids, hours_back, request.user
            )

            response_data = {
                "telemetry": telemetry_data,
                "metadata": {
                    "points_requested": len(request.data.get('point_ids', [])),
                    "points_returned": len(telemetry_data),
                    "hours_window": hours_back,
                    "metrics_included": metrics,
                    "timestamp": timezone.now().isoformat()
                }
            }

            # Agregar estadísticas si se solicita
            if include_stats:
                stats_data = TelemetryService.get_aggregated_stats(point_ids, hours_back)
                response_data["stats"] = stats_data

            # Agregar análisis de tendencias si se solicita
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
        """Calcular tendencias simples para los puntos"""
        trends = {}

        for point_id in point_ids:
            try:
                # Obtener datos de las últimas horas vs horas anteriores
                current_period = timezone.now() - timedelta(hours=hours_back)
                previous_period = current_period - timedelta(hours=hours_back)

                current_data = TelemetryRecord.objects.filter(
                    point_id=point_id,
                    timestamp__gte=current_period
                ).aggregate(
                    avg_flow=Avg('flow'),
                    avg_level=Avg('nivel'),
                    count=Count('id')
                )

                previous_data = TelemetryRecord.objects.filter(
                    point_id=point_id,
                    timestamp__gte=previous_period,
                    timestamp__lt=current_period
                ).aggregate(
                    avg_flow=Avg('flow'),
                    avg_level=Avg('nivel'),
                    count=Count('id')
                )

                # Calcular cambios porcentuales
                trends[str(point_id)] = {
                    'flow_change_percent': self._calculate_percent_change(
                        current_data['avg_flow'], previous_data['avg_flow']
                    ),
                    'level_change_percent': self._calculate_percent_change(
                        current_data['avg_level'], previous_data['avg_level']
                    ),
                    'data_points_current': current_data['count'],
                    'data_points_previous': previous_data['count'],
                    'trend_direction': self._get_trend_direction(
                        current_data['avg_flow'], previous_data['avg_flow']
                    )
                }

            except Exception as exc:
                trends[str(point_id)] = {'error': str(exc)}

        return trends

    def _calculate_percent_change(self, current, previous):
        """Calcular cambio porcentual"""
        if not previous or previous == 0:
            return None
        return ((current - previous) / previous) * 100 if current else 0

    def _get_trend_direction(self, current, previous):
        """Determinar dirección de la tendencia"""
        if not current or not previous:
            return 'unknown'
        if current > previous * 1.05:  # 5% aumento
            return 'increasing'
        elif current < previous * 0.95:  # 5% disminución
            return 'decreasing'
        else:
            return 'stable'


class RealtimeDashboardView(APIView):
    """
    Dashboard en Tiempo Real - Para conexiones WebSocket/SSE
    Proporciona actualizaciones en tiempo real sin polling
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        GET /api/v2/dashboard/realtime/
        Retorna datos optimizados para actualizaciones frecuentes
        """
        user = request.user

        # Obtener puntos del usuario (simplificado para realtime)
        user_points = TelemetryService.validate_user_access_to_points(
            user, request.GET.getlist('point_ids', [])
        )

        if not user_points:
            return Response({"data": [], "timestamp": timezone.now().isoformat()})

        # Datos optimizados para realtime (menos datos, más frecuencia)
        realtime_data = []

        for point_id in user_points:
            # Último registro de cada punto
            latest = TelemetryRecord.objects.filter(
                point_id=point_id
            ).select_related('point').order_by('-timestamp').first()

            if latest:
                realtime_data.append({
                    'point_id': point_id,
                    'point_name': latest.point.title,
                    'timestamp': latest.timestamp.isoformat(),
                    'flow': float(latest.flow) if latest.flow else None,
                    'level': float(latest.nivel) if latest.nivel else None,
                    'status': 'error' if latest.is_error else 'ok',
                    'is_online': self._is_point_online(point_id)
                })

        return Response({
            "data": realtime_data,
            "timestamp": timezone.now().isoformat(),
            "update_frequency": "30_seconds"  # Sugerencia para el frontend
        })

    def _is_point_online(self, point_id):
        """Verificar si punto está online (lectura en últimos 5 minutos)"""
        five_minutes_ago = timezone.now() - timedelta(minutes=5)
        return TelemetryRecord.objects.filter(
            point_id=point_id,
            timestamp__gte=five_minutes_ago
        ).exists()


class UserActionControlView(APIView):
    """
    Control de Acciones del Usuario - ERP integrado
    Permite activar/desactivar funcionalidades por usuario
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        GET /api/v2/control/user-actions/
        Obtener estado actual de permisos y acciones del usuario
        """
        user = request.user

        # Obtener permisos del usuario
        permissions = ActionService.get_user_permissions_summary(user)

        # Obtener configuraciones del usuario
        user_configs = self._get_user_configurations(user)

        # Obtener acciones recientes del usuario
        recent_actions = ActionService.get_recent_user_actions(user, limit=10)

        return Response({
            "user_id": user.id,
            "permissions": permissions,
            "configurations": user_configs,
            "recent_actions": recent_actions,
            "available_actions": ActionService.get_available_actions()
        })

    def post(self, request):
        """
        POST /api/v2/control/user-actions/
        Ejecutar una acción específica
        """
        user = request.user
        action_code = request.data.get('action')
        resource_id = request.data.get('resource_id')
        params = request.data.get('params', {})

        if not action_code:
            return Response(
                {"error": "action code required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Verificar permisos
        if not ActionService.user_can_perform_action(user, action_code, resource_id):
            ActionService.log_user_action(user, f"FORBIDDEN_{action_code}", resource_id, {
                'reason': 'insufficient_permissions'
            })
            return Response(
                {"error": "Insufficient permissions for this action"},
                status=status.HTTP_403_FORBIDDEN
            )

        try:
            # Ejecutar acción
            result = self._execute_action(user, action_code, resource_id, params)

            # Log de la acción
            ActionService.log_user_action(user, action_code, resource_id, {
                'params': params,
                'result': 'success'
            })

            return Response({
                "action": action_code,
                "resource_id": resource_id,
                "result": result,
                "timestamp": timezone.now().isoformat()
            })

        except Exception as exc:
            # Log del error
            ActionService.log_user_action(user, f"ERROR_{action_code}", resource_id, {
                'error': str(exc),
                'params': params
            })

            return Response(
                {"error": f"Action execution failed: {str(exc)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _execute_action(self, user, action_code, resource_id, params):
        """Ejecutar la acción específica"""

        if action_code == 'DGA_SEND':
            return self._toggle_dga_send(user, resource_id, params.get('enable', True))

        elif action_code == 'DGA_DISABLE':
            return self._toggle_dga_send(user, resource_id, False)

        elif action_code == 'REPORTS_GENERATE':
            return self._generate_user_report(user, params)

        elif action_code == 'ALERTS_MANAGE':
            return self._manage_alerts(user, resource_id, params)

        elif action_code == 'DEVICES_CONFIG':
            return self._configure_device(user, resource_id, params)

        else:
            raise ValueError(f"Unknown action: {action_code}")

    def _toggle_dga_send(self, user, point_id, enable):
        """Activar/desactivar envío a DGA para un punto"""
        from ..models import DgaDataConfigCatchment

        if not point_id:
            raise ValueError("point_id required for DGA actions")

        config = DgaDataConfigCatchment.objects.filter(
            point_catchment_id=point_id
        ).first()

        if not config:
            raise ValueError(f"No DGA configuration found for point {point_id}")

        config.send_dga = enable
        config.save()

        return {
            "message": f"DGA {'enabled' if enable else 'disabled'} for point {point_id}",
            "point_id": point_id,
            "dga_enabled": enable
        }

    def _generate_user_report(self, user, params):
        """Generar reporte personalizado para el usuario"""
        from ..tasks.reports import generate_custom_report

        # Crear tarea asíncrona
        task = generate_custom_report.delay(
            user_id=user.id,
            report_type=params.get('type', 'summary'),
            date_from=params.get('date_from'),
            date_to=params.get('date_to'),
            point_ids=params.get('point_ids', [])
        )

        return {
            "message": "Report generation started",
            "task_id": task.id,
            "estimated_time": "2-5 minutes"
        }

    def _manage_alerts(self, user, point_id, params):
        """Gestionar alertas de un punto"""
        from ..models import NotificationsCatchment

        action = params.get('action', 'list')

        if action == 'list':
            alerts = NotificationsCatchment.objects.filter(
                point_catchment_id=point_id,
                is_active=True
            ).values('id', 'title', 'type_notification', 'is_read')

            return {"alerts": list(alerts)}

        elif action in ['activate', 'deactivate']:
            alert_ids = params.get('alert_ids', [])
            if not alert_ids:
                raise ValueError("alert_ids required")

            NotificationsCatchment.objects.filter(
                id__in=alert_ids,
                point_catchment__owner_user=user  # Solo alertas de sus puntos
            ).update(is_active=(action == 'activate'))

            return {
                "message": f"Alerts {action}d",
                "alert_ids": alert_ids,
                "count": len(alert_ids)
            }

    def _configure_device(self, user, device_id, params):
        """Configurar dispositivo IoT"""
        device = IoTDevice.objects.filter(
            id=device_id,
            point__owner_user=user
        ).first()

        if not device:
            raise ValueError(f"Device {device_id} not found or no access")

        # Actualizar configuración
        if 'publish_interval' in params:
            device.mqtt_publish_interval = params['publish_interval']

        if 'config_parameters' in params:
            device.config_parameters.update(params['config_parameters'])

        device.save()

        return {
            "message": f"Device {device.name} configured",
            "device_id": device_id,
            "changes": params
        }

    def _get_user_configurations(self, user):
        """Obtener configuraciones personalizadas del usuario"""
        # Configuraciones de usuario (ejemplo)
        return {
            'theme': 'light',
            'language': 'es',
            'timezone': 'America/Santiago',
            'notifications_email': True,
            'notifications_push': False,
            'dashboard_refresh_interval': 30,  # segundos
            'default_chart_period': '24h'
        }


class SystemStatsView(APIView):
    """
    Estadísticas del Sistema en Tiempo Real
    Proporciona métricas automáticas para el frontend
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        GET /api/v2/stats/system/
        Retorna estadísticas del sistema en tiempo real
        """
        user = request.user

        # Verificar si usuario puede ver stats del sistema
        if not user.is_staff and not ActionService.user_can_perform_action(user, 'SYSTEM_STATS_VIEW'):
            return Response(
                {"error": "No tienes permisos para ver estadísticas del sistema"},
                status=status.HTTP_403_FORBIDDEN
            )

        try:
            # Obtener stats en tiempo real
            stats = StatsService.get_realtime_stats()

            # Agregar información específica del usuario
            user_stats = self._get_user_specific_stats(user)

            return Response({
                "system_stats": stats,
                "user_stats": user_stats,
                "timestamp": timezone.now().isoformat(),
                "data_freshness": "realtime"
            })

        except Exception as exc:
            return Response(
                {"error": f"Error obteniendo estadísticas: {str(exc)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _get_user_specific_stats(self, user):
        """Estadísticas específicas del usuario"""
        # Puntos del usuario
        user_points = TelemetryService.validate_user_access_to_points(
            user, []  # Todos los puntos del usuario
        )

        if user_points:
            # Stats de telemetría del usuario
            telemetry_stats = TelemetryService.get_aggregated_stats(
                user_points, days_back=1
            )

            # Contar puntos online
            online_points = sum(
                1 for point_id in user_points
                if self._is_point_online(point_id)
            )
        else:
            telemetry_stats = {}
            online_points = 0

        return {
            "total_points": len(user_points),
            "online_points": online_points,
            "offline_points": len(user_points) - online_points,
            "telemetry_stats_today": telemetry_stats,
            "recent_activity": self._get_recent_activity(user)
        }

    def _is_point_online(self, point_id):
        """Verificar si punto está online (lectura en última hora)"""
        one_hour_ago = timezone.now() - timedelta(hours=1)
        return TelemetryRecord.objects.filter(
            point_id=point_id,
            timestamp__gte=one_hour_ago
        ).exists()

    def _get_recent_activity(self, user):
        """Obtener actividad reciente del usuario"""
        # Simular actividad reciente (se puede implementar con un modelo de auditoría)
        return {
            "last_login": user.last_login.isoformat() if user.last_login else None,
            "api_calls_today": 0,  # Se puede implementar con middleware
            "reports_generated_today": 0,  # Se puede implementar con signals
            "alerts_viewed_today": 0
        }