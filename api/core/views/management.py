"""
Vistas de Gestión y Administración del Sistema de Telemetría.

Este módulo proporciona endpoints para administrar y monitorear
el servicio de telemetría, incluyendo estadísticas, control de
cronjobs, y gestión de puntos de captación.
"""

from django.apps import apps
from django.conf import settings
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
    Client,
    ProjectCatchments,
    User,
)
from api.core.permissions import IsStaffOrSuperUser


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
            # ✅ OPTIMIZACIÓN: Precalcular en 2 queries en vez de N+1
            point_ids = list(queryset.values_list('id', flat=True))

            # Precalcular última interacción por punto (una sola query con DISTINCT ON)
            last_interactions = {
                interaction.catchment_point_id: interaction
                for interaction in InteractionDetail.objects.filter(
                    catchment_point_id__in=point_ids
                ).order_by('catchment_point_id', '-date_time_medition').distinct('catchment_point_id')
            }

            # Precalcular puntos con telemetría activa (una sola query)
            telemetry_active_ids = set(
                ProfileDataConfigCatchment.objects.filter(
                    point_catchment_id__in=point_ids,
                    is_telemetry=True
                ).values_list('point_catchment_id', flat=True)
            )

            points_data = []
            for point in queryset.select_related('project', 'project__client', 'owner_user'):
                last_interaction = last_interactions.get(point.id)

                point_data = {
                    'id': point.id,
                    'title': point.title,
                    'project': point.project.name if point.project else None,
                    'client': point.project.client.name if point.project and point.project.client else None,
                    'frecuency': point.frecuency,
                    'provider': {
                        'handler': point.telemetry_provider.handler_name if point.telemetry_provider else None,
                        'name': point.telemetry_provider.name if point.telemetry_provider else None,
                        'twin': point.is_tdata,
                        'nettra': point.is_thethings,
                        'novus': point.is_novus,
                    },
                    'telemetry_active': point.id in telemetry_active_ids,
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



    @action(detail=False, methods=['get'], permission_classes=[IsStaffOrSuperUser])
    def system_map(self, request):
        """
        Devuelve el mapa completo del sistema para administradores.
        Incluye modelos, endpoints, cronjobs y estado del sistema.
        Solo accesible para staff o superusers.
        """
        try:
            # 1. Modelos del proyecto
            project_models = []
            for model in apps.get_models():
                app_label = model._meta.app_label
                # Solo modelos del proyecto (excluir auth, sessions, admin, etc.)
                if app_label in ['core']:
                    fields = []
                    relations = []
                    for field in model._meta.get_fields():
                        field_info = {
                            'name': field.name,
                            'type': field.get_internal_type() if hasattr(field, 'get_internal_type') else type(field).__name__,
                        }
                        if field.is_relation:
                            field_info['relation_type'] = type(field).__name__
                            field_info['related_model'] = field.related_model.__name__ if field.related_model else None
                            relations.append(field_info)
                        else:
                            fields.append(field_info)
                    
                    try:
                        record_count = model.objects.count()
                    except Exception:
                        record_count = 0
                    
                    project_models.append({
                        'name': model.__name__,
                        'app': app_label,
                        'table': model._meta.db_table,
                        'record_count': record_count,
                        'fields': fields,
                        'relations': relations,
                    })

            # 2. Endpoints registrados
            endpoints = [
                {'namespace': 'api', 'url': '/api/users/', 'methods': ['GET','POST','PUT','PATCH','DELETE'], 'viewset': 'UserViewSet'},
                {'namespace': 'api', 'url': '/api/users/login/', 'methods': ['POST'], 'description': 'Login con email/password'},
                {'namespace': 'api', 'url': '/api/users/signup/', 'methods': ['POST'], 'description': 'Registro de usuario'},
                {'namespace': 'api', 'url': '/api/interaction_detail/', 'methods': ['GET'], 'description': 'Telemetría con export XLSX'},
                {'namespace': 'api', 'url': '/api/interaction_detail_dga/', 'methods': ['GET'], 'description': 'Telemetría DGA sin procesamiento'},
                {'namespace': 'api', 'url': '/api/interaction_detail_override/', 'methods': ['GET','POST','PUT','PATCH','DELETE']},
                {'namespace': 'api', 'url': '/api/interaction_detail_override_month/', 'methods': ['GET','POST','PUT','PATCH','DELETE']},
                {'namespace': 'api', 'url': '/api/interaction_detail_json/', 'methods': ['GET','POST','PUT','PATCH','DELETE']},
                {'namespace': 'api', 'url': '/api/client/', 'methods': ['GET','POST','PUT','PATCH','DELETE']},
                {'namespace': 'api', 'url': '/api/client/all/', 'methods': ['GET'], 'description': 'Todos los clientes sin paginación'},
                {'namespace': 'api', 'url': '/api/client/with-projects/', 'methods': ['GET'], 'description': 'Clientes con proyectos anidados'},
                {'namespace': 'api', 'url': '/api/project_catchments/', 'methods': ['GET','POST','PUT','PATCH','DELETE']},
                {'namespace': 'api', 'url': '/api/project_catchments/all/', 'methods': ['GET'], 'description': 'Proyectos sin paginación'},
                {'namespace': 'api', 'url': '/api/catchment_point/', 'methods': ['GET','POST','PUT','PATCH','DELETE']},
                {'namespace': 'api', 'url': '/api/catchment_point/all/', 'methods': ['GET'], 'description': 'Puntos sin paginación'},
                {'namespace': 'api', 'url': '/api/profile_ikolu_catchment/', 'methods': ['GET','POST','PUT','PATCH','DELETE']},
                {'namespace': 'api', 'url': '/api/notifications_catchment/', 'methods': ['GET','POST','PUT','PATCH','DELETE']},
                {'namespace': 'api', 'url': '/api/response_notifications_catchment/', 'methods': ['GET','POST','PUT','PATCH','DELETE']},
                {'namespace': 'api', 'url': '/api/type_file_catchment/', 'methods': ['GET','POST','PUT','PATCH','DELETE']},
                {'namespace': 'api', 'url': '/api/file_catchment/', 'methods': ['GET','POST','PUT','PATCH','DELETE']},
                {'namespace': 'api', 'url': '/api/profile_data_config_catchment/', 'methods': ['GET','POST','PUT','PATCH','DELETE']},
                {'namespace': 'api', 'url': '/api/dga_data_config_catchment/', 'methods': ['GET','POST','PUT','PATCH','DELETE']},
                {'namespace': 'api', 'url': '/api/schemes_catchment/', 'methods': ['GET','POST','PUT','PATCH','DELETE']},
                {'namespace': 'api', 'url': '/api/variable/', 'methods': ['GET','POST','PUT','PATCH','DELETE']},
                {'namespace': 'api', 'url': '/api/register_persons/', 'methods': ['GET','POST','PUT','PATCH','DELETE']},
                {'namespace': 'api', 'url': '/api/management/system_status/', 'methods': ['GET']},
                {'namespace': 'api', 'url': '/api/management/points_status/', 'methods': ['GET']},
                {'namespace': 'api', 'url': '/api/management/telemetry_metrics/', 'methods': ['GET']},
                {'namespace': 'api', 'url': '/api/management/toggle_telemetry/', 'methods': ['POST']},
                {'namespace': 'api', 'url': '/api/management/dga_queue_status/', 'methods': ['GET']},
                {'namespace': 'api', 'url': '/api/management/clear_dga_queue/', 'methods': ['POST']},
                {'namespace': 'api', 'url': '/api/management/requeue_dga/', 'methods': ['POST']},
                {'namespace': 'api', 'url': '/api/management/update_point_frequency/', 'methods': ['POST']},
                {'namespace': 'api', 'url': '/api/management/notifications_summary/', 'methods': ['GET']},
                {'namespace': 'api', 'url': '/api/management/system_map/', 'methods': ['GET'], 'description': 'Mapa completo del sistema (este endpoint)'},
                {'namespace': 'api', 'url': '/api/management/resources_status/', 'methods': ['GET'], 'description': 'Estado de recursos del servidor'},
                {'namespace': 'api_ik', 'url': '/api/ik/batch/telemetry/', 'methods': ['POST']},
                {'namespace': 'api_ik', 'url': '/api/ik/batch/stats/', 'methods': ['POST']},
                {'namespace': 'api_ik', 'url': '/api/ik/login/', 'methods': ['POST']},
                {'namespace': 'root', 'url': '/health/', 'methods': ['GET']},
                {'namespace': 'root', 'url': '/status/', 'methods': ['GET']},
                {'namespace': 'root', 'url': '/status/dashboard/', 'methods': ['GET']},
                {'namespace': 'root', 'url': '/admin/dashboard/', 'methods': ['GET']},
                {'namespace': 'root', 'url': '/admin/telemetry-monitoring/', 'methods': ['GET']},
                {'namespace': 'root', 'url': '/reports/active-points/', 'methods': ['GET']},
                {'namespace': 'root', 'url': '/api/password_reset/', 'methods': ['POST']},
                {'namespace': 'root', 'url': '/api/chat-bot/', 'methods': ['POST']},
            ]

            # 3. Cronjobs desde settings
            cronjobs = []
            for job in getattr(settings, 'CRONJOBS', []):
                cronjobs.append({
                    'schedule': job[0],
                    'function': job[1],
                    'log': job[2] if len(job) > 2 else None,
                })

            # 4. Estado del sistema
            system_status = {
                'django_version': getattr(settings, 'VERSION', 'unknown'),
                'debug': getattr(settings, 'DEBUG', False),
                'database_engine': settings.DATABASES.get('default', {}).get('ENGINE', 'unknown'),
                'database_host': settings.DATABASES.get('default', {}).get('HOST', 'unknown'),
                'redis_location': settings.CACHES.get('default', {}).get('LOCATION', 'unknown'),
                'timestamp': timezone.now().isoformat(),
            }

            return Response({
                'models': project_models,
                'endpoints': endpoints,
                'cronjobs': cronjobs,
                'system_status': system_status,
                'total_models': len(project_models),
                'total_endpoints': len(endpoints),
                'total_cronjobs': len(cronjobs),
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['get'], permission_classes=[IsStaffOrSuperUser])
    def resources_status(self, request):
        """
        Devuelve estado completo del sistema: servidor, servicios externos, cronjobs, DB, Redis.
        Solo accesible para staff o superusers.
        """
        import subprocess
        import os
        import shutil
        import urllib.request
        import urllib.error
        import time

        data = {
            'server': {},
            'external_services': {},
            'cronjobs': {},
            'database': {},
            'redis': {},
            'django': {},
            'timestamp': timezone.now().isoformat(),
        }

        # 1. CPU Usage via /proc/stat (no psutil needed, works inside containers)
        def get_cpu_times():
            with open('/proc/stat', 'r') as f:
                line = f.readline()
            fields = list(map(int, line.split()[1:8]))
            return sum(fields), fields[0] + fields[1] + fields[2] + fields[5] + fields[6]

        try:
            total1, busy1 = get_cpu_times()
            time.sleep(0.5)
            total2, busy2 = get_cpu_times()
            cpu_percent = ((busy2 - busy1) / (total2 - total1)) * 100 if (total2 - total1) > 0 else 0
            data['server']['cpu_percent'] = round(cpu_percent, 2)
        except Exception as e:
            data['server']['cpu_percent'] = f'Error: {str(e)}'

        # 2. Memory Usage via /proc/meminfo
        try:
            meminfo = {}
            with open('/proc/meminfo', 'r') as f:
                for line in f:
                    key, value = line.split(':', 1)
                    meminfo[key.strip()] = int(value.strip().split()[0]) * 1024  # convert kB to bytes
            mem_total = meminfo.get('MemTotal', 0)
            mem_available = meminfo.get('MemAvailable', meminfo.get('MemFree', 0) + meminfo.get('Buffers', 0) + meminfo.get('Cached', 0))
            mem_used = mem_total - mem_available
            mem_percent = (mem_used / mem_total) * 100 if mem_total > 0 else 0

            def human_bytes(b):
                for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
                    if abs(b) < 1024.0:
                        return f"{b:.2f} {unit}"
                    b /= 1024.0
                return f"{b:.2f} PB"

            data['server']['memory_percent'] = round(mem_percent, 2)
            data['server']['memory_total'] = human_bytes(mem_total)
            data['server']['memory_used'] = human_bytes(mem_used)
            data['server']['memory_available'] = human_bytes(mem_available)
        except Exception as e:
            data['server']['memory_percent'] = f'Error: {str(e)}'

        # 3. Disk Usage
        try:
            disk = shutil.disk_usage('/')
            data['server']['disk_total_gb'] = round(disk.total / (1024**3), 2)
            data['server']['disk_used_gb'] = round(disk.used / (1024**3), 2)
            data['server']['disk_free_gb'] = round(disk.free / (1024**3), 2)
            data['server']['disk_percent'] = round((disk.used / disk.total) * 100, 2)
        except Exception as e:
            data['server']['disk'] = f'Error: {str(e)}'

        # 4. Uptime via /proc/uptime
        try:
            with open('/proc/uptime', 'r') as f:
                uptime_seconds = float(f.readline().split()[0])
            days = int(uptime_seconds // 86400)
            hours = int((uptime_seconds % 86400) // 3600)
            minutes = int((uptime_seconds % 3600) // 60)
            data['server']['uptime'] = f"{days}d {hours}h {minutes}m"
            data['server']['uptime_seconds'] = round(uptime_seconds, 1)
        except Exception as e:
            data['server']['uptime'] = f'Error: {str(e)}'

        # 5. Docker Containers (only if docker socket/cmd available)
        try:
            docker_path = shutil.which('docker')
            if docker_path and os.path.exists('/var/run/docker.sock'):
                docker_result = subprocess.run(
                    [docker_path, "ps", "--format", "{{.Names}}|{{.Status}}|{{.Image}}"],
                    capture_output=True, text=True, timeout=10
                )
                containers = []
                for line in docker_result.stdout.strip().split('\n'):
                    if line:
                        parts = line.split('|')
                        containers.append({
                            'name': parts[0],
                            'status': parts[1] if len(parts) > 1 else 'unknown',
                            'image': parts[2] if len(parts) > 2 else 'unknown',
                        })
                data['docker'] = {
                    'containers': containers,
                    'total': len(containers),
                    'running': sum(1 for c in containers if 'Up' in c['status'])
                }
            else:
                data['docker'] = {
                    'note': 'Docker no disponible desde este contenedor (requiere socket o grupo docker)',
                    'containers': [],
                    'total': 0,
                    'running': 0
                }
        except Exception as e:
            data['docker'] = {'error': str(e), 'note': 'Docker no disponible desde este contenedor'}

        # ========================================
        # 6. ESTADO DE SERVICIOS EXTERNOS (HEALTH CHECKS)
        # ========================================
        def check_url(url, timeout=10):
            """Helper para verificar si una URL responde."""
            try:
                req = urllib.request.Request(url, method='HEAD')
                req.add_header('User-Agent', 'SmartHydro-HealthCheck/1.0')
                with urllib.request.urlopen(req, timeout=timeout) as response:
                    return {
                        'status': 'up',
                        'http_status': response.status,
                    }
            except urllib.error.HTTPError as e:
                if e.code in [401, 403, 404, 405]:
                    return {
                        'status': 'up',
                        'http_status': e.code,
                        'note': 'Servicio responde pero requiere auth/método diferente'
                    }
                return {'status': 'down', 'error': f'HTTP {e.code}'}
            except Exception as e:
                return {'status': 'down', 'error': str(e)}

        # Twin / TData
        data['external_services']['twin_tdata'] = check_url('https://api.twindimension.com/tdata/v1/login')
        data['external_services']['twin_tdata']['name'] = 'Twin / TData'

        # Nettra / TheThingsIO
        data['external_services']['nettra_thethings'] = check_url('https://api.thethings.io/v2/things/')
        data['external_services']['nettra_thethings']['name'] = 'Nettra / TheThingsIO'

        # Tago
        # Usamos /analysis porque devuelve 200 con {"status":true,"result":"Authorization denied"}
        # mientras que /data/ devuelve 400 por falta de parámetros obligatorios
        data['external_services']['tago'] = check_url('https://api.tago.io/analysis')
        data['external_services']['tago']['name'] = 'Tago IO'

        # DGA (Ministerio de Obras Públicas)
        data['external_services']['dga'] = check_url('https://apimee.mop.gob.cl/api/v1')
        data['external_services']['dga']['name'] = 'DGA (MOP)'

        # SMA
        data['external_services']['sma'] = check_url('https://conexiones.sma.gob.cl/api/v1/auth')
        data['external_services']['sma']['name'] = 'SMA'

        # Resumen de servicios externos
        ext_services = {k: v for k, v in data['external_services'].items()}
        data['external_services_summary'] = {
            'total': len(ext_services),
            'up': sum(1 for v in ext_services.values() if v.get('status') == 'up'),
            'down': sum(1 for v in ext_services.values() if v.get('status') == 'down'),
        }

        # ========================================
        # 7. ESTADO DE CRONJOBS (basado en logs)
        # ========================================
        log_dir = '/app/cron_logs/'
        cronjobs_config = [
            {'name': 'twin_60', 'schedule': '0 * * * *', 'log': 'twin_60.log', 'description': 'Telemetría Twin 60 min'},
            {'name': 'twin_1', 'schedule': '* * * * *', 'log': 'twin_1.log', 'description': 'Telemetría Twin 1 min'},
            {'name': 'twin_5', 'schedule': '*/5 * * * *', 'log': 'twin_5.log', 'description': 'Telemetría Twin 5 min'},
            {'name': 'twin_10', 'schedule': '*/10 * * * *', 'log': 'twin_10.log', 'description': 'Telemetría Twin 10 min'},
            {'name': 'nettra_60', 'schedule': '0 * * * *', 'log': 'nettra_60.log', 'description': 'Telemetría Nettra 60 min'},
            {'name': 'nettra_5', 'schedule': '*/5 * * * *', 'log': 'nettra_5.log', 'description': 'Telemetría Nettra 5 min'},
            {'name': 'novus_60', 'schedule': '0 * * * *', 'log': 'novus_60.log', 'description': 'Telemetría Novus 60 min'},
            {'name': 'dga', 'schedule': '*/3 * * * *', 'log': 'dga.log', 'description': 'Cola DGA'},
            {'name': 'sma', 'schedule': '*/5 * * * *', 'log': 'sma.log', 'description': 'Cola SMA'},
            {'name': 'alerts', 'schedule': '*/10 * * * *', 'log': 'alerts.log', 'description': 'Alertas'},
            {'name': 'space_backup', 'schedule': '0 * * * *', 'log': 'space_backup.log', 'description': 'Backup cluster'},
            {'name': 'daily_bulletin', 'schedule': '0 1 * * *', 'log': 'daily_bulletin.log', 'description': 'Boletín diario'},
            {'name': 'daily_chat_report', 'schedule': '0 12 * * *', 'log': 'daily_chat_report.log', 'description': 'Reporte chat diario'},
            {'name': 'daily_active_tickets', 'schedule': '0 13 * * *', 'log': 'daily_active_tickets.log', 'description': 'Tickets activos diarios'},
            {'name': 'dga_mayor_hourly', 'schedule': '5 * * * *', 'log': 'dga_mayor_hourly.log', 'description': 'Reporte DGA MAYOR horario'},
        ]

        def human_bytes(b):
            for unit in ['B', 'KB', 'MB', 'GB']:
                if abs(b) < 1024.0:
                    return f"{b:.2f} {unit}"
                b /= 1024.0
            return f"{b:.2f} TB"

        cronjob_statuses = []
        now = timezone.now()

        for cron in cronjobs_config:
            status_info = {
                'name': cron['name'],
                'description': cron['description'],
                'schedule': cron['schedule'],
                'log_file': cron['log'],
            }

            log_path = os.path.join(log_dir, cron['log'])
            if os.path.exists(log_path):
                try:
                    # --- info del archivo ---
                    stat = os.stat(log_path)
                    status_info['log_size_bytes'] = stat.st_size
                    status_info['log_size_human'] = human_bytes(stat.st_size)
                    status_info['log_modified'] = timezone.datetime.fromtimestamp(
                        stat.st_mtime, tz=timezone.get_default_timezone()
                    ).isoformat()

                    mtime = stat.st_mtime
                    from datetime import datetime
                    last_run = datetime.fromtimestamp(mtime, tz=timezone.get_default_timezone())
                    minutes_since = (now - last_run).total_seconds() / 60

                    status_info['last_run'] = last_run.isoformat()
                    status_info['minutes_since_last_run'] = round(minutes_since, 1)

                    # --- frecuencia esperada más precisa ---
                    sched = cron['schedule']
                    parts = sched.split()
                    minute_field = parts[0] if len(parts) == 5 else '*'
                    if minute_field == '*':
                        expected_minutes = 5
                    elif minute_field.startswith('*/'):
                        step = int(minute_field.replace('*/', ''))
                        expected_minutes = step * 3 + 2  # e.g. */5 -> 17 min buffer
                    elif minute_field.isdigit() and parts[1] == '*':
                        # Ej: "0 * * * *" o "5 * * * *"  -> cada hora
                        expected_minutes = 90
                    elif parts[1].startswith('*/') or parts[1] == '*':
                        # Cada X horas o diario con minuto fijo
                        expected_minutes = 180
                    else:
                        # Diarios (ej: "0 1 * * *")
                        expected_minutes = 1620  # 27h buffer

                    # --- leer log ---
                    try:
                        with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
                            lines = f.readlines()
                        status_info['log_lines_total'] = len(lines)
                        status_info['log_is_empty'] = len(lines) == 0 or all(l.strip() == '' for l in lines)

                        # Últimas 10 líneas no vacías
                        non_empty = [l.rstrip('\n') for l in lines if l.strip()]
                        status_info['last_log_lines'] = non_empty[-10:] if len(non_empty) >= 10 else non_empty

                        # Contar errores en TODO el log (últimas 500 líneas como máximo)
                        sample = lines[-500:] if len(lines) > 500 else lines
                        error_keywords = ('error', 'exception', 'traceback', 'critical', 'failed')
                        error_count = sum(
                            1 for line in sample
                            if any(kw in line.lower() for kw in error_keywords)
                        )
                        status_info['errors_in_log'] = error_count
                        status_info['recent_errors'] = error_count > 0

                        # Determinar estado final
                        if minutes_since <= expected_minutes:
                            base_status = 'healthy'
                        elif minutes_since <= expected_minutes * 2:
                            base_status = 'warning'
                        else:
                            base_status = 'error'

                        # Si hay errores recientes, empeorar un healthy a warning
                        if error_count > 0 and base_status == 'healthy':
                            base_status = 'warning'

                        status_info['status'] = base_status
                        status_info['expected_minutes'] = expected_minutes

                    except Exception as e:
                        status_info['last_log_lines'] = []
                        status_info['recent_errors'] = False
                        status_info['errors_in_log'] = 0
                        status_info['log_lines_total'] = 0
                        status_info['status'] = 'unknown'
                        status_info['log_read_error'] = str(e)

                except Exception as e:
                    status_info['status'] = 'unknown'
                    status_info['error'] = str(e)
            else:
                status_info['status'] = 'no_log'
                status_info['last_run'] = None
                status_info['log_size_bytes'] = 0
                status_info['log_size_human'] = '0.00 B'
                status_info['log_lines_total'] = 0
                status_info['log_is_empty'] = True

            cronjob_statuses.append(status_info)

        data['cronjobs'] = {
            'jobs': cronjob_statuses,
            'healthy': sum(1 for c in cronjob_statuses if c.get('status') == 'healthy'),
            'warning': sum(1 for c in cronjob_statuses if c.get('status') == 'warning'),
            'error': sum(1 for c in cronjob_statuses if c.get('status') == 'error'),
            'no_log': sum(1 for c in cronjob_statuses if c.get('status') == 'no_log'),
            'unknown': sum(1 for c in cronjob_statuses if c.get('status') == 'unknown'),
            'total': len(cronjob_statuses),
        }

        # ========================================
        # 8. Database Status
        # ========================================
        try:
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            data['database']['status'] = 'connected'
            data['database']['engine'] = settings.DATABASES['default'].get('ENGINE', 'unknown')
            data['database']['host'] = settings.DATABASES['default'].get('HOST', 'unknown')
            data['database']['name'] = settings.DATABASES['default'].get('NAME', 'unknown')

            try:
                with connection.cursor() as cursor:
                    cursor.execute("""
                        SELECT pg_database.datname, pg_database_size(pg_database.datname)
                        FROM pg_database WHERE datname = current_database();
                    """)
                    row = cursor.fetchone()
                    if row:
                        db_size_mb = round(row[1] / (1024 * 1024), 2)
                        data['database']['size_mb'] = db_size_mb
            except Exception:
                data['database']['size_mb'] = 'N/A'
        except Exception as e:
            data['database']['status'] = 'error'
            data['database']['error'] = str(e)

        # ========================================
        # 9. Redis Status
        # ========================================
        try:
            from django_redis import get_redis_connection
            redis_conn = get_redis_connection("default")
            redis_info = redis_conn.info()
            data['redis']['status'] = 'connected'
            data['redis']['version'] = redis_info.get('redis_version', 'unknown')
            data['redis']['used_memory_human'] = redis_info.get('used_memory_human', 'unknown')
            data['redis']['connected_clients'] = redis_info.get('connected_clients', 0)
        except Exception as e:
            data['redis']['status'] = 'error'
            data['redis']['error'] = str(e)

        # ========================================
        # 10. Django Info
        # ========================================
        data['django']['version'] = getattr(settings, 'VERSION', 'unknown')
        data['django']['debug'] = getattr(settings, 'DEBUG', False)
        data['django']['time_zone'] = getattr(settings, 'TIME_ZONE', 'unknown')
        data['django']['allowed_hosts'] = getattr(settings, 'ALLOWED_HOSTS', [])
        data['django']['installed_apps_count'] = len(getattr(settings, 'INSTALLED_APPS', []))

        try:
            data['django']['model_counts'] = {
                'users': User.objects.count(),
                'clients': Client.objects.count(),
                'projects': ProjectCatchments.objects.count(),
                'catchment_points': CatchmentPoint.objects.count(),
                'interaction_details': InteractionDetail.objects.count(),
                'notifications': NotificationsCatchment.objects.count(),
            }
        except Exception as e:
            data['django']['model_counts_error'] = str(e)

        return Response(data, status=status.HTTP_200_OK)
