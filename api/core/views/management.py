"""
Vistas de Gestión y Administración del Sistema de Telemetría.

Este módulo proporciona endpoints para administrar y monitorear
el servicio de telemetría, incluyendo estadísticas, control de
cronjobs, y gestión de puntos de captación.
"""

from django.db.models import Count, Q, Max, Min, Avg, Sum
from django.db.models.functions import TruncDate, TruncHour
from django.utils import timezone
from datetime import timedelta
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters import rest_framework as filters

from api.core.models import (
    CatchmentPoint,
    InteractionDetail,
    NotificationsCatchment,
    ProfileDataConfigCatchment,
    DgaDataConfigCatchment,
    Client,
    ProjectCatchments,
)
from api.core.serializers.catchment_points import CatchmentPointSerializer


class ManagementViewSet(viewsets.ViewSet):
    """
    ViewSet para gestión y administración del sistema.
    
    Proporciona endpoints para:
    - Estadísticas del sistema
    - Monitoreo de puntos de captación
    - Control de telemetría
    - Gestión de cola DGA
    - Estado de cronjobs
    """
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'])
    def system_status(self, request):
        """
        Obtiene el estado general del sistema.
        
        Returns:
            - Total de puntos de captación
            - Puntos activos/inactivos
            - Puntos con telemetría activa
            - Registros de telemetría (últimas 24h)
            - Puntos con problemas de conexión
        """
        try:
            # Estadísticas generales
            total_points = CatchmentPoint.objects.count()
            active_telemetry = CatchmentPoint.objects.filter(
                data_config_profiles__is_telemetry=True
            ).distinct().count()
            
            # Puntos con problemas de conexión (último registro > 1 día sin conexión)
            yesterday = timezone.now() - timedelta(days=1)
            disconnected_points = CatchmentPoint.objects.filter(
                interactiondetail__days_not_conection__gt=0,
                interactiondetail__date_time_medition__gte=yesterday
            ).distinct().count()
            
            # Registros en últimas 24 horas
            last_24h = timezone.now() - timedelta(hours=24)
            records_24h = InteractionDetail.objects.filter(
                date_time_medition__gte=last_24h
            ).count()
            
            # Notificaciones activas
            active_notifications = NotificationsCatchment.objects.filter(
                is_active=True
            ).count()
            
            # Registros en cola DGA
            dga_queue = InteractionDetail.objects.filter(
                send_dga=True
            ).count()
            
            # Registros con error
            error_records = InteractionDetail.objects.filter(
                is_error=True,
                date_time_medition__gte=last_24h
            ).count()
            
            return Response({
                'status': 'operational',
                'statistics': {
                    'total_points': total_points,
                    'active_telemetry': active_telemetry,
                    'inactive_telemetry': total_points - active_telemetry,
                    'disconnected_points': disconnected_points,
                    'records_last_24h': records_24h,
                    'active_notifications': active_notifications,
                    'dga_queue_size': dga_queue,
                    'error_records_24h': error_records,
                },
                'timestamp': timezone.now().isoformat()
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['get'])
    def points_status(self, request):
        """
        Obtiene el estado detallado de los puntos de captación.
        
        Query params:
            - project: Filtrar por proyecto (ID)
            - client: Filtrar por cliente (ID)
            - disconnected: Solo puntos desconectados (true/false)
            - active_telemetry: Solo con telemetría activa (true/false)
        """
        try:
            queryset = CatchmentPoint.objects.all()
            
            # Filtros opcionales
            project_id = request.query_params.get('project')
            if project_id:
                queryset = queryset.filter(project_id=project_id)
            
            client_id = request.query_params.get('client')
            if client_id:
                queryset = queryset.filter(project__client_id=client_id)
            
            disconnected_only = request.query_params.get('disconnected', 'false').lower() == 'true'
            if disconnected_only:
                yesterday = timezone.now() - timedelta(days=1)
                queryset = queryset.filter(
                    interactiondetail__days_not_conection__gt=0,
                    interactiondetail__date_time_medition__gte=yesterday
                ).distinct()
            
            active_only = request.query_params.get('active_telemetry', 'false').lower() == 'true'
            if active_only:
                queryset = queryset.filter(
                    data_config_profiles__is_telemetry=True
                ).distinct()
            
            # Obtener último registro de cada punto
            points_data = []
            for point in queryset.select_related('project', 'project__client', 'owner_user'):
                last_interaction = InteractionDetail.objects.filter(
                    catchment_point=point
                ).order_by('-date_time_medition').first()
                
                point_data = {
                    'id': point.id,
                    'title': point.title,
                    'project': point.project.name if point.project else None,
                    'client': point.project.client.name if point.project and point.project.client else None,
                    'frecuency': point.frecuency,
                    'provider': {
                        'twin': point.is_tdata,
                        'nettra': point.is_thethings,
                        'novus': point.is_novus,
                    },
                    'telemetry_active': ProfileDataConfigCatchment.objects.filter(
                        point_catchment=point,
                        is_telemetry=True
                    ).exists(),
                    'last_interaction': None,
                }
                
                if last_interaction:
                    point_data['last_interaction'] = {
                        'date_time': last_interaction.date_time_medition.isoformat() if last_interaction.date_time_medition else None,
                        'days_not_connection': last_interaction.days_not_conection,
                        'flow': float(last_interaction.flow) if last_interaction.flow else 0,
                        'total': last_interaction.total,
                        'nivel': float(last_interaction.nivel) if last_interaction.nivel else 0,
                        'is_error': last_interaction.is_error,
                    }
                
                points_data.append(point_data)
            
            return Response({
                'points': points_data,
                'total': len(points_data),
                'timestamp': timezone.now().isoformat()
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['get'])
    def telemetry_metrics(self, request):
        """
        Obtiene métricas de telemetría.
        
        Query params:
            - point: ID del punto de captación (opcional)
            - days: Días a consultar (default: 7)
        """
        try:
            point_id = request.query_params.get('point')
            days = int(request.query_params.get('days', 7))
            
            start_date = timezone.now() - timedelta(days=days)
            queryset = InteractionDetail.objects.filter(
                date_time_medition__gte=start_date
            )
            
            if point_id:
                queryset = queryset.filter(catchment_point_id=point_id)
            
            # Métricas agregadas
            metrics = queryset.aggregate(
                total_records=Count('id'),
                avg_flow=Avg('flow'),
                max_flow=Max('flow'),
                min_flow=Min('flow'),
                total_consumption=Sum('total_diff'),
                avg_nivel=Avg('nivel'),
                error_count=Count('id', filter=Q(is_error=True)),
            )
            
            # Registros por día
            daily_records = queryset.annotate(
                date=TruncDate('date_time_medition')
            ).values('date').annotate(
                count=Count('id')
            ).order_by('date')
            
            # Registros por hora (últimas 24h)
            last_24h = timezone.now() - timedelta(hours=24)
            hourly_records = queryset.filter(
                date_time_medition__gte=last_24h
            ).annotate(
                hour=TruncHour('date_time_medition')
            ).values('hour').annotate(
                count=Count('id')
            ).order_by('hour')
            
            return Response({
                'metrics': {
                    'total_records': metrics['total_records'] or 0,
                    'avg_flow': float(metrics['avg_flow']) if metrics['avg_flow'] else 0,
                    'max_flow': float(metrics['max_flow']) if metrics['max_flow'] else 0,
                    'min_flow': float(metrics['min_flow']) if metrics['min_flow'] else 0,
                    'total_consumption': metrics['total_consumption'] or 0,
                    'avg_nivel': float(metrics['avg_nivel']) if metrics['avg_nivel'] else 0,
                    'error_count': metrics['error_count'] or 0,
                    'error_percentage': round(
                        (metrics['error_count'] / metrics['total_records'] * 100) 
                        if metrics['total_records'] else 0, 2
                    ),
                },
                'daily_records': list(daily_records),
                'hourly_records': list(hourly_records),
                'period': {
                    'start_date': start_date.isoformat(),
                    'end_date': timezone.now().isoformat(),
                    'days': days,
                },
                'timestamp': timezone.now().isoformat()
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['post'])
    def toggle_telemetry(self, request):
        """
        Activa o desactiva la telemetría de un punto de captación.
        
        Body:
            - point_id: ID del punto de captación
            - enabled: true/false para activar/desactivar
        """
        try:
            point_id = request.data.get('point_id')
            enabled = request.data.get('enabled', True)
            
            if not point_id:
                return Response({
                    'error': 'point_id es requerido'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            point = CatchmentPoint.objects.get(id=point_id)
            config = ProfileDataConfigCatchment.objects.filter(
                point_catchment=point
            ).first()
            
            if not config:
                return Response({
                    'error': 'No existe configuración de datos para este punto'
                }, status=status.HTTP_404_NOT_FOUND)
            
            config.is_telemetry = enabled
            config.save()
            
            return Response({
                'message': f'Telemetría {"activada" if enabled else "desactivada"} correctamente',
                'point_id': point_id,
                'telemetry_enabled': enabled,
                'timestamp': timezone.now().isoformat()
            }, status=status.HTTP_200_OK)
            
        except CatchmentPoint.DoesNotExist:
            return Response({
                'error': 'Punto de captación no encontrado'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['get'])
    def dga_queue_status(self, request):
        """
        Obtiene el estado de la cola de envío DGA.
        
        Returns:
            - Total de registros en cola
            - Registros por punto
            - Registros con error
        """
        try:
            queue = InteractionDetail.objects.filter(send_dga=True)
            
            total = queue.count()
            
            # Agrupar por punto
            by_point = queue.values('catchment_point__title', 'catchment_point__id').annotate(
                count=Count('id')
            ).order_by('-count')
            
            # Registros con error
            errors = queue.filter(is_error=True).count()
            
            # Registros antiguos (> 7 días)
            week_ago = timezone.now() - timedelta(days=7)
            old_records = queue.filter(date_time_medition__lt=week_ago).count()
            
            return Response({
                'queue_status': {
                    'total': total,
                    'errors': errors,
                    'old_records': old_records,
                },
                'by_point': list(by_point),
                'timestamp': timezone.now().isoformat()
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['post'])
    def clear_dga_queue(self, request):
        """
        Limpia la cola de envío DGA.
        
        Body opcional:
            - point_id: Limpiar solo para un punto específico
            - only_errors: Limpiar solo registros con error (true/false)
        """
        try:
            point_id = request.data.get('point_id')
            only_errors = request.data.get('only_errors', False)
            
            queryset = InteractionDetail.objects.filter(send_dga=True)
            
            if point_id:
                queryset = queryset.filter(catchment_point_id=point_id)
            
            if only_errors:
                queryset = queryset.filter(is_error=True)
            
            count = queryset.count()
            queryset.update(send_dga=False)
            
            return Response({
                'message': f'{count} registros removidos de la cola DGA',
                'removed_count': count,
                'timestamp': timezone.now().isoformat()
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['post'])
    def requeue_dga(self, request):
        """
        Reagrega registros a la cola DGA.
        
        Body:
            - point_id: ID del punto (opcional)
            - start_date: Fecha inicio (opcional)
            - end_date: Fecha fin (opcional)
            - only_errors: Solo registros con error (opcional)
        """
        try:
            point_id = request.data.get('point_id')
            start_date = request.data.get('start_date')
            end_date = request.data.get('end_date')
            only_errors = request.data.get('only_errors', False)
            
            queryset = InteractionDetail.objects.filter(send_dga=False)
            
            if point_id:
                queryset = queryset.filter(catchment_point_id=point_id)
            
            if start_date:
                queryset = queryset.filter(date_time_medition__gte=start_date)
            
            if end_date:
                queryset = queryset.filter(date_time_medition__lte=end_date)
            
            if only_errors:
                queryset = queryset.filter(is_error=True)
            
            count = queryset.count()
            queryset.update(send_dga=True)
            
            return Response({
                'message': f'{count} registros agregados a la cola DGA',
                'added_count': count,
                'timestamp': timezone.now().isoformat()
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['post'])
    def update_point_frequency(self, request):
        """
        Actualiza la frecuencia de un punto de captación.
        
        Body:
            - point_id: ID del punto
            - frequency: '1', '5', o '60' (minutos)
        """
        try:
            point_id = request.data.get('point_id')
            frequency = request.data.get('frequency')
            
            if not point_id or not frequency:
                return Response({
                    'error': 'point_id y frequency son requeridos'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            if frequency not in ['1', '5', '10', '60']:
                return Response({
                    'error': 'frequency debe ser: 1, 5, 10, o 60'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            point = CatchmentPoint.objects.get(id=point_id)
            point.frecuency = frequency
            point.save()
            
            return Response({
                'message': f'Frecuencia actualizada a {frequency} minutos',
                'point_id': point_id,
                'frequency': frequency,
                'timestamp': timezone.now().isoformat()
            }, status=status.HTTP_200_OK)
            
        except CatchmentPoint.DoesNotExist:
            return Response({
                'error': 'Punto de captación no encontrado'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['get'])
    def notifications_summary(self, request):
        """
        Obtiene un resumen de notificaciones.
        
        Query params:
            - days: Días a consultar (default: 7)
        """
        try:
            days = int(request.query_params.get('days', 7))
            start_date = timezone.now() - timedelta(days=days)
            
            notifications = NotificationsCatchment.objects.filter(
                created__gte=start_date
            )
            
            summary = notifications.values('type_notification').annotate(
                count=Count('id')
            )
            
            active = notifications.filter(is_active=True).count()
            unread = notifications.filter(is_read=False).count()
            finished = notifications.filter(is_finish=True).count()
            
            return Response({
                'summary': {
                    'total': notifications.count(),
                    'active': active,
                    'unread': unread,
                    'finished': finished,
                },
                'by_type': list(summary),
                'period': {
                    'days': days,
                    'start_date': start_date.isoformat(),
                },
                'timestamp': timezone.now().isoformat()
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

