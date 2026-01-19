"""
Vistas de Gestión y Administración del Sistema de Telemetría (V3).
Proporciona endpoints para administrar y monitorear el servicio V3 dinámico.
"""

from django.db.models import Count, Q, Max, Min, Avg, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone
from datetime import timedelta
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from api.telemetry.models.catchment_points import (
    CatchmentPoint,
    ProfileDataConfigCatchment,
    DgaDataConfigCatchment,
)
from api.crm.models import Client, Project
from api.notifications.models import Notification
from api.telemetry.models.telemetry import TelemetryRecord


class ManagementViewSet(viewsets.ViewSet):
    """
    ViewSet para gestión y administración del sistema V3.
    """
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'])
    def system_status(self, request):
        """Estado general del sistema V3"""
        try:
            total_points = CatchmentPoint.objects.count()
            active_telemetry = CatchmentPoint.objects.filter(
                data_config_profiles__is_telemetry=True
            ).distinct().count()
            
            yesterday = timezone.now() - timedelta(days=1)
            disconnected_points = CatchmentPoint.objects.filter(
                telemetry_v3__is_error=True,
                telemetry_v3__timestamp__gte=yesterday
            ).distinct().count()
            
            last_24h = timezone.now() - timedelta(hours=24)
            records_24h = TelemetryRecord.objects.filter(
                timestamp__gte=last_24h
            ).count()
            
            active_notifications = Notification.objects.filter(is_active=True).count()
            dga_queue = TelemetryRecord.objects.filter(send_dga=True).count()
            error_records = TelemetryRecord.objects.filter(is_error=True, timestamp__gte=last_24h).count()
            
            return Response({
                'status': 'operational',
                'statistics': {
                    'total_points': total_points,
                    'active_telemetry': active_telemetry,
                    'inactive_telemetry': total_points - active_telemetry,
                    'disconnected_points_v3': disconnected_points,
                    'records_last_24h_v3': records_24h,
                    'active_notifications': active_notifications,
                    'dga_queue_size_v3': dga_queue,
                    'error_records_24h_v3': error_records,
                },
                'timestamp': timezone.now().isoformat()
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['get'])
    def points_status(self, request):
        """Estado detallado de puntos V3"""
        try:
            queryset = CatchmentPoint.objects.all()
            project_id = request.query_params.get('project')
            if project_id: queryset = queryset.filter(project_id=project_id)
            
            client_id = request.query_params.get('client')
            if client_id: queryset = queryset.filter(project__client_id=client_id)
            
            disconnected_only = request.query_params.get('disconnected', 'false').lower() == 'true'
            if disconnected_only:
                yesterday = timezone.now() - timedelta(days=1)
                queryset = queryset.filter(telemetry_v3__is_error=True, telemetry_v3__timestamp__gte=yesterday).distinct()
            
            active_only = request.query_params.get('active_telemetry', 'false').lower() == 'true'
            if active_only: queryset = queryset.filter(data_config_profiles__is_telemetry=True).distinct()
            
            points_data = []
            for point in queryset.select_related('project', 'project__client', 'owner_user'):
                last_v3 = TelemetryRecord.objects.filter(point=point).order_by('-timestamp').first()
                point_data = {
                    'id': point.id,
                    'title': point.title,
                    'project': point.project.name if point.project else None,
                    'client': point.project.client.name if point.project and point.project.client else None,
                    'frecuency': point.frecuency,
                    'telemetry_active': ProfileDataConfigCatchment.objects.filter(point_catchment=point, is_telemetry=True).exists(),
                    'last_interaction_v3': None,
                }
                if last_v3:
                    data = last_v3.data
                    point_data['last_interaction_v3'] = {
                        'date_time': last_v3.timestamp.isoformat(),
                        'flow': float(data.get('flow', data.get('caudal', 0))),
                        'total': data.get('total', 0),
                        'nivel': float(data.get('nivel', 0)),
                        'is_error': last_v3.is_error,
                    }
                points_data.append(point_data)
            
            return Response({'points': points_data, 'total': len(points_data), 'timestamp': timezone.now().isoformat()}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['get'])
    def telemetry_metrics(self, request):
        """Métricas de telemetría V3"""
        try:
            point_id = request.query_params.get('point')
            days = int(request.query_params.get('days', 7))
            start_date = timezone.now() - timedelta(days=days)
            queryset = TelemetryRecord.objects.filter(timestamp__gte=start_date)
            if point_id: queryset = queryset.filter(point_id=point_id)
            
            metrics = queryset.aggregate(
                total_records=Count('id'),
                avg_flow=Avg('data__flow'),
                max_flow=Max('data__flow'),
                min_flow=Min('data__flow'),
                total_consumption=Sum('data__total_diff'),
                avg_nivel=Avg('data__nivel'),
                error_count=Count('id', filter=Q(is_error=True)),
            )
            
            daily_records = queryset.annotate(date=TruncDate('timestamp')).values('date').annotate(count=Count('id')).order_by('date')
            
            return Response({
                'metrics': {
                    'total_records_v3': metrics['total_records'] or 0,
                    'avg_flow': float(metrics['avg_flow'] or 0),
                    'total_consumption': float(metrics['total_consumption'] or 0),
                    'error_count': metrics['error_count'] or 0,
                },
                'daily_records_v3': list(daily_records),
                'period': {'start_date': start_date.isoformat(), 'end_date': timezone.now().isoformat(), 'days': days},
                'timestamp': timezone.now().isoformat()
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['post'])
    def toggle_telemetry(self, request):
        """Activa o desactiva telemetría"""
        try:
            point_id = request.data.get('point_id')
            enabled = request.data.get('enabled', True)
            if not point_id: return Response({'error': 'point_id es requerido'}, status=status.HTTP_400_BAD_REQUEST)
            
            config = ProfileDataConfigCatchment.objects.filter(point_catchment_id=point_id).first()
            if not config: return Response({'error': 'Configuración no encontrada'}, status=status.HTTP_404_NOT_FOUND)
            
            config.is_telemetry = enabled
            config.save()
            return Response({'message': f'Telemetría {"activada" if enabled else "desactivada"}', 'point_id': point_id, 'enabled': enabled}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['get'])
    def dga_queue_status(self, request):
        """Estado cola DGA V3"""
        try:
            queue = TelemetryRecord.objects.filter(send_dga=True)
            total = queue.count()
            by_point = queue.values('point__title', 'point__id').annotate(count=Count('id')).order_by('-count')
            errors = queue.filter(is_error=True).count()
            
            return Response({
                'queue_status_v3': {'total': total, 'errors': errors},
                'by_point': list(by_point),
                'timestamp': timezone.now().isoformat()
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['post'])
    def clear_dga_queue(self, request):
        """Limpia cola DGA V3"""
        try:
            point_id = request.data.get('point_id')
            only_errors = request.data.get('only_errors', False)
            queryset = TelemetryRecord.objects.filter(send_dga=True)
            if point_id: queryset = queryset.filter(point_id=point_id)
            if only_errors: queryset = queryset.filter(is_error=True)
            
            count = queryset.count()
            queryset.update(send_dga=False)
            return Response({'message': f'{count} registros removidos de la cola V3', 'removed_count': count}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['post'])
    def requeue_dga(self, request):
        """Reagrega a cola DGA V3"""
        try:
            point_id = request.data.get('point_id')
            start_date = request.data.get('start_date')
            end_date = request.data.get('end_date')
            queryset = TelemetryRecord.objects.filter(send_dga=False)
            if point_id: queryset = queryset.filter(point_id=point_id)
            if start_date: queryset = queryset.filter(timestamp__gte=start_date)
            if end_date: queryset = queryset.filter(timestamp__lte=end_date)
            
            count = queryset.count()
            queryset.update(send_dga=True)
            return Response({'message': f'{count} registros reagregados a cola V3', 'added_count': count}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['post'])
    def update_point_frequency(self, request):
        """Actualiza frecuencia punto"""
        try:
            point_id = request.data.get('point_id')
            frequency = request.data.get('frequency')
            if not point_id or frequency not in ['1', '5', '10', '60']:
                return Response({'error': 'Datos inválidos'}, status=status.HTTP_400_BAD_REQUEST)
            
            point = CatchmentPoint.objects.get(id=point_id)
            point.frecuency = frequency
            point.save()
            return Response({'message': 'Frecuencia actualizada', 'frequency': frequency}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['get'])
    def notifications_summary(self, request):
        """Resumen notificaciones"""
        try:
            days = int(request.query_params.get('days', 7))
            start_date = timezone.now() - timedelta(days=days)
            notifications = Notification.objects.filter(created__gte=start_date)
            summary = notifications.values('type_notification').annotate(count=Count('id'))
            
            return Response({
                'summary': {
                    'total': notifications.count(),
                    'active': notifications.filter(is_active=True).count(),
                    'unread': notifications.filter(is_read=False).count(),
                },
                'by_type': list(summary),
                'timestamp': timezone.now().isoformat()
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
