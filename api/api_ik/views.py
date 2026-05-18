"""
API IK Views - Optimized Endpoints
===================================

Vistas optimizadas que retornan solo los datos necesarios.
Endpoints bajo /api/ik/
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework import status
from rest_framework.authtoken.models import Token
from django.contrib.auth import authenticate
from django.db.models import (
    OuterRef, Subquery, Count, Q, Prefetch
)

from api.core.models import (
    User,
    CatchmentPoint,
    InteractionDetail,
    ProfileDataConfigCatchment,
    DgaDataConfigCatchment,
    NotificationsCatchment,
    SchemesCatchment,
    Variable,
)
from .throttles import LoginRateThrottle


class OptimizedLoginView(APIView):
    """
    Login optimizado que retorna solo datos esenciales.

    POST /api/ik/login/
    Body: { "email": "...", "password": "..." }

    Response (éxito):
    {
        "success": true,
        "message": "Login exitoso",
        "access_token": "...",
        "user": { "id", "email", "username", "first_name", "last_name",
                  "is_staff", "is_superuser", "is_client_admin" },
        "points_summary": {
            "total": 5,
            "owned_ids": [1, 2],
            "viewed_ids": [3, 4, 5],
            "all_ids": [1, 2, 3, 4, 5]
        }
    }
    """
    permission_classes = [AllowAny]
    throttle_classes = [LoginRateThrottle]

    def post(self, request):
        email = request.data.get('email', '').strip()
        password = request.data.get('password', '')

        if not email or not password:
            return Response(
                {"success": False, "message": "Email y contraseña son requeridos"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Usar authenticate() para respetar backends de auth de Django
        # y disparar señales como user_logged_in (actualiza last_login, etc.)
        user = authenticate(username=email, password=password)

        if not user:
            return Response(
                {"success": False, "message": "Credenciales inválidas"},
                status=status.HTTP_401_UNAUTHORIZED
            )

        if not user.is_verified:
            return Response(
                {"success": False, "message": "Cuenta de usuario aún no verificada"},
                status=status.HTTP_401_UNAUTHORIZED
            )

        token, _ = Token.objects.get_or_create(user=user)

        owned_point_ids = list(user.owned_catchment_points.values_list('id', flat=True))
        viewed_point_ids = list(user.viewed_catchment_points.values_list('id', flat=True))
        all_point_ids = list(set(owned_point_ids + viewed_point_ids))

        data = {
            "success": True,
            "message": "Login exitoso",
            "access_token": token.key,
            "user": {
                "id": user.id,
                "email": user.email,
                "username": user.username,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "is_staff": user.is_staff,
                "is_superuser": user.is_superuser,
                "is_client_admin": user.is_client_admin,
            },
            "points_summary": {
                "total": len(all_point_ids),
                "owned_ids": owned_point_ids,
                "viewed_ids": viewed_point_ids,
                "all_ids": all_point_ids
            }
        }

        response = Response(data, status=status.HTTP_200_OK)
        response['Authorization'] = f'Bearer {token.key}'
        return response


class PointsSummaryView(APIView):
    """
    Resumen de todos los puntos del usuario logueado con última telemetría.

    GET /api/ik/points_summary/
    Auth: Token

    Reemplaza la necesidad de cargar get_profile() con todos los datos.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        # Subquery: última InteractionDetail por punto
        latest_interaction = InteractionDetail.objects.filter(
            catchment_point=OuterRef('pk')
        ).order_by('-date_time_medition')

        # Queryset optimizado
        # Staff/superuser ven todos los puntos; usuarios normales solo los suyos
        if user.is_staff or user.is_superuser:
            points_qs = CatchmentPoint.objects.all()
        else:
            points_qs = CatchmentPoint.objects.filter(
                Q(owner_user=user) | Q(users_viewers=user)
            ).distinct()

        points = points_qs.select_related(
            'project', 'project__client', 'owner_user'
        ).prefetch_related(
            Prefetch(
                'data_config_profiles',
                queryset=ProfileDataConfigCatchment.objects.only(
                    'point_catchment_id', 'is_telemetry'
                )
            ),
            Prefetch(
                'dga_data_config_profiles',
                queryset=DgaDataConfigCatchment.objects.only(
                    'point_catchment_id', 'send_dga', 'standard', 'type_dga', 'code_dga'
                )
            ),
            Prefetch(
                'schemes',
                queryset=SchemesCatchment.objects.prefetch_related(
                    Prefetch(
                        'variables',
                        queryset=Variable.objects.only(
                            'scheme_catchment_id', 'type_variable'
                        )
                    )
                )
            ),
        ).annotate(
            latest_flow=Subquery(latest_interaction.values('flow')[:1]),
            latest_total=Subquery(latest_interaction.values('total')[:1]),
            latest_nivel=Subquery(latest_interaction.values('nivel')[:1]),
            latest_water_table=Subquery(latest_interaction.values('water_table')[:1]),
            latest_is_error=Subquery(latest_interaction.values('is_error')[:1]),
            latest_days_not_conection=Subquery(latest_interaction.values('days_not_conection')[:1]),
            latest_date_time_medition=Subquery(latest_interaction.values('date_time_medition')[:1]),
            latest_variable_values=Subquery(latest_interaction.values('variable_values')[:1]),
            alerts_count=Count('notifications', filter=Q(notifications__is_active=True)),
        )

        points_data = []
        active_points = 0
        points_with_alerts = 0

        for p in points:
            # Config data (telemetry)
            config = p.data_config_profiles.first()
            is_telemetry = config.is_telemetry if config else False

            # Variables del punto
            variables = []
            for scheme in p.schemes.all():
                for v in scheme.variables.all():
                    if v.type_variable and v.type_variable not in variables:
                        variables.append(v.type_variable)

            # DGA config
            dga_config = p.dga_data_config_profiles.first()

            # Provider (nuevo: telemetry_provider, legacy: booleanos)
            provider = None
            if p.telemetry_provider:
                provider = p.telemetry_provider.handler_name
            elif p.is_tdata:
                provider = 'twin'
            elif p.is_thethings:
                provider = 'nettra'
            elif p.is_novus:
                provider = 'novus'

            # Última telemetría
            latest = {
                'date_time_medition': p.latest_date_time_medition.isoformat() if p.latest_date_time_medition else None,
                'flow': str(p.latest_flow) if p.latest_flow is not None else None,
                'total': p.latest_total,
                'nivel': str(p.latest_nivel) if p.latest_nivel is not None else None,
                'water_table': str(p.latest_water_table) if p.latest_water_table is not None else None,
                'is_error': p.latest_is_error if p.latest_is_error is not None else False,
                'days_not_connection': p.latest_days_not_conection if p.latest_days_not_conection is not None else 0,
                'variable_values': p.latest_variable_values or {},
            }

            # Activo: sin días de desconexión
            is_active = (p.latest_days_not_conection == 0) if p.latest_days_not_conection is not None else True
            if is_active:
                active_points += 1
            if p.alerts_count > 0:
                points_with_alerts += 1

            points_data.append({
                'id': p.id,
                'title': p.title,
                'frecuency': p.frecuency,
                'lat': p.lat,
                'lon': p.lon,
                'active': is_active,
                'project_id': p.project.id if p.project else None,
                'project_name': p.project.name if p.project else None,
                'client_name': p.project.client.name if p.project and p.project.client else None,
                'provider': provider,
                'is_telemetry': is_telemetry,
                'config_data': {
                    'variables': variables,
                },
                'dga': {
                    'code_dga': dga_config.code_dga if dga_config else None,
                    'type_dga': dga_config.type_dga if dga_config else None,
                    'send_dga': dga_config.send_dga if dga_config else False,
                } if dga_config else None,
                'latest_telemetry': latest,
                'alerts_count': p.alerts_count,
            })

        return Response({
            'points': points_data,
            'total_points': len(points_data),
            'active_points': active_points,
            'points_with_alerts': points_with_alerts,
        })


class PointSummaryView(APIView):
    """
    Resumen de un punto específico con última telemetría.

    GET /api/ik/point/{id}/summary/
    Auth: Token
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, point_id):
        user = request.user

        try:
            # Staff/superuser pueden ver cualquier punto
            if user.is_staff or user.is_superuser:
                point_qs = CatchmentPoint.objects.all()
            else:
                point_qs = CatchmentPoint.objects.filter(
                    Q(owner_user=user) | Q(users_viewers=user)
                ).distinct()

            point = point_qs.select_related(
                'project', 'project__client', 'owner_user'
            ).prefetch_related(
                Prefetch(
                    'data_config_profiles',
                    queryset=ProfileDataConfigCatchment.objects.only(
                        'point_catchment_id', 'is_telemetry'
                    )
                ),
                Prefetch(
                    'dga_data_config_profiles',
                    queryset=DgaDataConfigCatchment.objects.only(
                        'point_catchment_id', 'send_dga', 'standard', 'type_dga', 'code_dga'
                    )
                ),
                Prefetch(
                    'schemes',
                    queryset=SchemesCatchment.objects.prefetch_related(
                        Prefetch(
                            'variables',
                            queryset=Variable.objects.only(
                                'scheme_catchment_id', 'type_variable'
                            )
                        )
                    )
                ),
            ).annotate(
                latest_flow=Subquery(
                    InteractionDetail.objects.filter(
                        catchment_point=OuterRef('pk')
                    ).order_by('-date_time_medition').values('flow')[:1]
                ),
                latest_total=Subquery(
                    InteractionDetail.objects.filter(
                        catchment_point=OuterRef('pk')
                    ).order_by('-date_time_medition').values('total')[:1]
                ),
                latest_nivel=Subquery(
                    InteractionDetail.objects.filter(
                        catchment_point=OuterRef('pk')
                    ).order_by('-date_time_medition').values('nivel')[:1]
                ),
                latest_water_table=Subquery(
                    InteractionDetail.objects.filter(
                        catchment_point=OuterRef('pk')
                    ).order_by('-date_time_medition').values('water_table')[:1]
                ),
                latest_is_error=Subquery(
                    InteractionDetail.objects.filter(
                        catchment_point=OuterRef('pk')
                    ).order_by('-date_time_medition').values('is_error')[:1]
                ),
                latest_days_not_conection=Subquery(
                    InteractionDetail.objects.filter(
                        catchment_point=OuterRef('pk')
                    ).order_by('-date_time_medition').values('days_not_conection')[:1]
                ),
                latest_date_time_medition=Subquery(
                    InteractionDetail.objects.filter(
                        catchment_point=OuterRef('pk')
                    ).order_by('-date_time_medition').values('date_time_medition')[:1]
                ),
                latest_variable_values=Subquery(
                    InteractionDetail.objects.filter(
                        catchment_point=OuterRef('pk')
                    ).order_by('-date_time_medition').values('variable_values')[:1]
                ),
                alerts_count=Count('notifications', filter=Q(notifications__is_active=True)),
            ).get(id=point_id)
        except CatchmentPoint.DoesNotExist:
            return Response(
                {"error": "Punto no encontrado o sin permisos"},
                status=status.HTTP_404_NOT_FOUND
            )

        # Config data
        config = point.data_config_profiles.first()
        is_telemetry = config.is_telemetry if config else False

        # Variables
        variables = []
        for scheme in point.schemes.all():
            for v in scheme.variables.all():
                if v.type_variable and v.type_variable not in variables:
                    variables.append(v.type_variable)

        # DGA
        dga_config = point.dga_data_config_profiles.first()

        # Provider (nuevo: telemetry_provider, legacy: booleanos)
        provider = None
        if point.telemetry_provider:
            provider = point.telemetry_provider.handler_name
        elif point.is_tdata:
            provider = 'twin'
        elif point.is_thethings:
            provider = 'nettra'
        elif point.is_novus:
            provider = 'novus'

        is_active = (point.latest_days_not_conection == 0) if point.latest_days_not_conection is not None else True

        return Response({
            'id': point.id,
            'title': point.title,
            'frecuency': point.frecuency,
            'lat': point.lat,
            'lon': point.lon,
            'active': is_active,
            'project_id': point.project.id if point.project else None,
            'project_name': point.project.name if point.project else None,
            'client_name': point.project.client.name if point.project and point.project.client else None,
            'provider': provider,
            'is_telemetry': is_telemetry,
            'config_data': {
                'variables': variables,
            },
            'dga': {
                'code_dga': dga_config.code_dga if dga_config else None,
                'type_dga': dga_config.type_dga if dga_config else None,
                'send_dga': dga_config.send_dga if dga_config else False,
            } if dga_config else None,
            'latest_telemetry': {
                'date_time_medition': point.latest_date_time_medition.isoformat() if point.latest_date_time_medition else None,
                'flow': str(point.latest_flow) if point.latest_flow is not None else None,
                'total': point.latest_total,
                'nivel': str(point.latest_nivel) if point.latest_nivel is not None else None,
                'water_table': str(point.latest_water_table) if point.latest_water_table is not None else None,
                'is_error': point.latest_is_error if point.latest_is_error is not None else False,
                'days_not_connection': point.latest_days_not_conection if point.latest_days_not_conection is not None else 0,
                'variable_values': point.latest_variable_values or {},
            },
            'alerts_count': point.alerts_count,
        })



class MyPointsView(APIView):
    """
    Lista ultra-liviana de puntos del usuario autenticado.
    Ideal para poblar selects/dropdowns.

    GET /api/ik/my_points/
    Auth: Token

    Response:
    [
      {
        "id": 1,
        "title": "PC Descarga",
        "project_name": "SMA",
        "client_name": "Lecheria Valle Verde",
        "frecuency": "1",
        "is_telemetry": true,
        "is_owner": true,
        "is_viewer": false
      }
    ]
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        def _point_dict(p, is_owner, is_viewer):
            config = p.data_config_profiles.first()
            dga_config = p.dga_data_config_profiles.first()
            code_dga = dga_config.code_dga if dga_config else None
            has_code = bool(code_dga and str(code_dga).strip())
            return {
                'id': p.id,
                'title': p.title,
                'project_name': p.project.name if p.project else None,
                'client_name': p.project.client.name if p.project and p.project.client else None,
                'frecuency': p.frecuency,
                'is_telemetry': config.is_telemetry if config else False,
                'is_dga_compliance': bool(dga_config and dga_config.send_dga and has_code),
                'code_dga': code_dga if has_code else None,
                'is_owner': is_owner,
                'is_viewer': is_viewer,
            }

        # Staff/superuser ven todos los puntos marcados como owner
        if user.is_staff or user.is_superuser:
            points = CatchmentPoint.objects.select_related(
                'project', 'project__client'
            ).order_by('title').prefetch_related(
                Prefetch(
                    'data_config_profiles',
                    queryset=ProfileDataConfigCatchment.objects.only('point_catchment_id', 'is_telemetry')
                ),
                Prefetch(
                    'dga_data_config_profiles',
                    queryset=DgaDataConfigCatchment.objects.only('point_catchment_id', 'send_dga', 'code_dga')
                )
            ).only(
                'id', 'title', 'frecuency', 'project__name', 'project__client__name'
            )
            result = [_point_dict(p, True, False) for p in points]
            return Response(result)

        # Usuarios normales: owner + viewer
        owned = CatchmentPoint.objects.filter(
            owner_user=user
        ).select_related('project', 'project__client').order_by('title').prefetch_related(
            Prefetch(
                'data_config_profiles',
                queryset=ProfileDataConfigCatchment.objects.only('point_catchment_id', 'is_telemetry')
            ),
            Prefetch(
                'dga_data_config_profiles',
                queryset=DgaDataConfigCatchment.objects.only('point_catchment_id', 'send_dga', 'code_dga')
            )
        ).only(
            'id', 'title', 'frecuency', 'project__name', 'project__client__name'
        )

        viewed = CatchmentPoint.objects.filter(
            users_viewers=user
        ).select_related('project', 'project__client').order_by('title').prefetch_related(
            Prefetch(
                'data_config_profiles',
                queryset=ProfileDataConfigCatchment.objects.only('point_catchment_id', 'is_telemetry')
            ),
            Prefetch(
                'dga_data_config_profiles',
                queryset=DgaDataConfigCatchment.objects.only('point_catchment_id', 'send_dga', 'code_dga')
            )
        ).only(
            'id', 'title', 'frecuency', 'project__name', 'project__client__name'
        )

        owned_ids = set(p.id for p in owned)
        result = []

        for p in owned:
            result.append(_point_dict(p, True, False))

        for p in viewed:
            if p.id not in owned_ids:
                result.append(_point_dict(p, False, True))

        return Response(result)



class DashboardStatsView(APIView):
    """
    Stats generales para el Centro de Control (KPIs del dashboard).

    GET /api/ik/dashboard_stats/
    Auth: Token

    - Usuario normal: stats solo de sus puntos (owner + viewer)
    - Staff/Superuser: stats de todos los puntos
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        from django.utils import timezone
        from datetime import date, timedelta

        # Filtrar puntos según permisos
        if user.is_staff or user.is_superuser:
            point_ids = list(CatchmentPoint.objects.values_list('id', flat=True))
        else:
            owned = list(user.owned_catchment_points.values_list('id', flat=True))
            viewed = list(user.viewed_catchment_points.values_list('id', flat=True))
            point_ids = list(set(owned + viewed))

        total_points = len(point_ids)

        if total_points == 0:
            return Response({
                'meta': {
                    'date': str(date.today()),
                    'date_formatted': self._format_date(date.today()),
                    'generated_at': timezone.now().isoformat(),
                    'timezone': str(timezone.get_default_timezone()),
                },
                'points': {
                    'total': 0,
                    'with_telemetry': 0,
                    'without_telemetry': 0,
                    'with_gps': 0,
                    'with_dga_compliance': 0,
                },
                'telemetry_today': {
                    'connected': 0,
                    'disconnected': 0,
                    'without_telemetry': 0,
                },
                'notifications': {
                    'total_active': 0,
                    'unread': 0,
                    'by_type': {},
                    'by_variable': {},
                },
                'dga_summary': {
                    'by_type': {},
                    'by_standard': {},
                },
            })

        # Puntos base queryset
        points_qs = CatchmentPoint.objects.filter(id__in=point_ids)

        # --- Stats de puntos ---
        with_telemetry = ProfileDataConfigCatchment.objects.filter(
            point_catchment_id__in=point_ids,
            is_telemetry=True
        ).values('point_catchment_id').distinct().count()

        with_gps = points_qs.exclude(
            Q(lat__isnull=True) | Q(lat='') | Q(lon__isnull=True) | Q(lon='')
        ).count()

        with_dga = DgaDataConfigCatchment.objects.filter(
            point_catchment_id__in=point_ids,
            send_dga=True
        ).exclude(
            Q(code_dga__isnull=True) | Q(code_dga='')
        ).values('point_catchment_id').distinct().count()

        # --- Telemetry hoy ---
        today = date.today()
        yesterday = today - timedelta(days=1)

        # Puntos con registros hoy
        connected_today = InteractionDetail.objects.filter(
            catchment_point_id__in=point_ids,
            date_time_medition__date=today
        ).values('catchment_point_id').distinct().count()

        # Puntos sin telemetría
        without_telemetry = total_points - with_telemetry

        # Puntos con telemetría pero sin datos hoy = disconnected
        disconnected_today = max(0, with_telemetry - connected_today)

        # --- Notificaciones (solo de los puntos del usuario) ---
        notifications_qs = NotificationsCatchment.objects.filter(
            point_catchment_id__in=point_ids
        )

        total_active = notifications_qs.filter(is_active=True).count()
        unread = notifications_qs.filter(is_read=False).count()

        by_type = {
            item['type_notification']: item['count']
            for item in notifications_qs.filter(is_active=True).values('type_notification').annotate(count=Count('id'))
        }

        by_variable = {
            item['type_variable']: item['count']
            for item in notifications_qs.filter(is_active=True).values('type_variable').annotate(count=Count('id'))
        }

        # --- DGA summary ---
        dga_qs = DgaDataConfigCatchment.objects.filter(point_catchment_id__in=point_ids)

        by_dga_type = {
            item['type_dga']: item['count']
            for item in dga_qs.values('type_dga').annotate(count=Count('id'))
        }

        by_standard = {
            item['standard']: item['count']
            for item in dga_qs.values('standard').annotate(count=Count('id'))
        }

        return Response({
            'meta': {
                'date': str(today),
                'date_formatted': self._format_date(today),
                'generated_at': timezone.now().isoformat(),
                'timezone': str(timezone.get_default_timezone()),
            },
            'points': {
                'total': total_points,
                'with_telemetry': with_telemetry,
                'without_telemetry': without_telemetry,
                'with_gps': with_gps,
                'with_dga_compliance': with_dga,
            },
            'telemetry_today': {
                'connected': connected_today,
                'disconnected': disconnected_today,
                'without_telemetry': without_telemetry,
            },
            'notifications': {
                'total_active': total_active,
                'unread': unread,
                'by_type': by_type,
                'by_variable': by_variable,
            },
            'dga_summary': {
                'by_type': by_dga_type,
                'by_standard': by_standard,
            },
        })

    def _format_date(self, d):
        """Formatea fecha en español sin depender del locale del sistema."""
        from datetime import datetime
        DIAS = ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo']
        MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
                 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']
        dt = datetime(d.year, d.month, d.day)
        dia_semana = DIAS[dt.weekday()]
        mes = MESES[d.month - 1]
        return f"{dia_semana.capitalize()} {d.day} de {mes}, {d.year}"



class PointCalendarView(APIView):
    """
    Calendario de los últimos N días para un punto específico.
    Muestra consumo, caudal promedio, nivel freático y variables presentes por día.

    GET /api/ik/point/<id>/calendar/?days=7
    Auth: Token

    - Usuario normal: solo si es owner o viewer del punto
    - Staff/Superuser: cualquier punto
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, point_id):
        user = request.user
        from django.utils import timezone
        from datetime import date, timedelta
        from django.db.models import Avg, Sum, Count, Min, Max

        # Verificar permisos
        if user.is_staff or user.is_superuser:
            point_qs = CatchmentPoint.objects.all()
        else:
            point_qs = CatchmentPoint.objects.filter(
                Q(owner_user=user) | Q(users_viewers=user)
            ).distinct()

        try:
            point = point_qs.select_related('project', 'project__client').prefetch_related(
                Prefetch(
                    'schemes',
                    queryset=SchemesCatchment.objects.prefetch_related(
                        Prefetch(
                            'variables',
                            queryset=Variable.objects.only('scheme_catchment_id', 'type_variable')
                        )
                    )
                )
            ).get(id=point_id)
        except CatchmentPoint.DoesNotExist:
            return Response(
                {"error": "Punto no encontrado o sin permisos"},
                status=status.HTTP_404_NOT_FOUND
            )

        # Determinar variables activas del punto
        variables = set()
        for scheme in point.schemes.all():
            for v in scheme.variables.all():
                if v.type_variable:
                    variables.add(v.type_variable)

        # Parámetro days (default 7, max 30)
        try:
            days = int(request.query_params.get('days', 7))
            if days < 1:
                days = 1
            elif days > 30:
                days = 30
        except ValueError:
            days = 7

        # Rango de fechas
        end_date = date.today()
        start_date = end_date - timedelta(days=days - 1)

        # Obtener agregaciones por día
        daily_records = InteractionDetail.objects.filter(
            catchment_point=point,
            date_time_medition__date__gte=start_date,
            date_time_medition__date__lte=end_date
        ).values('date_time_medition__date').annotate(
            consumption=Sum('total_diff'),
            avg_flow=Avg('flow'),
            max_flow=Max('flow'),
            avg_nivel=Avg('nivel'),
            avg_water_table=Avg('water_table'),
            records_count=Count('id'),
            first_record=Min('date_time_medition'),
            last_record=Max('date_time_medition'),
        ).order_by('date_time_medition__date')

        # Indexar por fecha para lookup rápido
        daily_by_date = {}
        for d in daily_records:
            day = d['date_time_medition__date']
            daily_by_date[day] = d

        # Construir calendario día por día
        calendar = []
        for i in range(days):
            day = end_date - timedelta(days=(days - 1 - i))
            day_data = daily_by_date.get(day)

            entry = {
                'date': str(day),
                'date_formatted': self._format_date_short(day),
                'has_data': day_data is not None,
            }

            if day_data:
                entry['consumption_m3'] = round(day_data['consumption'], 2) if day_data['consumption'] else 0.0
                entry['records_count'] = day_data['records_count']
                entry['first_record'] = day_data['first_record'].isoformat() if day_data['first_record'] else None
                entry['last_record'] = day_data['last_record'].isoformat() if day_data['last_record'] else None
                entry['variables_present'] = list(variables)

                # Solo incluir campos si la variable está activa en el punto
                if 'CAUDAL' in variables or 'CAUDAL_PROMEDIO' in variables:
                    entry['avg_flow_lps'] = round(float(day_data['avg_flow']), 2) if day_data['avg_flow'] else None
                    entry['max_flow_lps'] = round(float(day_data['max_flow']), 2) if day_data['max_flow'] else None

                if 'NIVEL' in variables:
                    entry['avg_nivel_m'] = round(float(day_data['avg_nivel']), 2) if day_data['avg_nivel'] else None

                if 'NIVEL' in variables or 'TOTALIZADO' in variables:
                    entry['avg_water_table_m'] = round(float(day_data['avg_water_table']), 2) if day_data['avg_water_table'] else None
            else:
                entry['consumption_m3'] = 0.0
                entry['records_count'] = 0
                entry['first_record'] = None
                entry['last_record'] = None
                entry['variables_present'] = []

            calendar.append(entry)

        return Response({
            'point_id': point.id,
            'point_title': point.title,
            'project_name': point.project.name if point.project else None,
            'client_name': point.project.client.name if point.project and point.project.client else None,
            'variables': list(variables),
            'days': days,
            'start_date': str(start_date),
            'end_date': str(end_date),
            'calendar': calendar,
        })

    def _format_date_short(self, d):
        """Formatea fecha corta en español: 'Vie 9 May'."""
        from datetime import datetime
        DIAS = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom']
        MESES = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun',
                 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']
        dt = datetime(d.year, d.month, d.day)
        dia = DIAS[dt.weekday()]
        mes = MESES[d.month - 1]
        return f"{dia} {d.day} {mes}"


class PublicAnnouncementsView(APIView):
    """
    Anuncios globales públicos (sin autenticación).
    Lista notificaciones sin punto de captación y activas.
    Ideal para banners de mantenimiento o página de estado.

    GET /api/ik/announcements/public/?limit=10
    """
    permission_classes = [AllowAny]

    def get(self, request):
        from django.utils import timezone
        from datetime import date

        try:
            limit = int(request.query_params.get('limit', 20))
            if limit < 1:
                limit = 1
            elif limit > 100:
                limit = 100
        except ValueError:
            limit = 20

        today = date.today()

        # Solo anuncios globales: sin punto de captación, activos, y vigentes
        announcements = NotificationsCatchment.objects.filter(
            point_catchment__isnull=True,
            is_active=True,
        ).filter(
            Q(end_date__isnull=True) | Q(end_date__gte=today)
        ).order_by('-created')[:limit]

        data = []
        for a in announcements:
            data.append({
                'id': a.id,
                'title': a.title,
                'message': a.message,
                'type': a.type_notification,
                'is_read': a.is_read,
                'created': a.created.isoformat() if a.created else None,
                'start_date': str(a.start_date) if a.start_date else None,
                'end_date': str(a.end_date) if a.end_date else None,
            })

        return Response({
            'count': len(data),
            'announcements': data,
        })


class PointVariablesView(APIView):
    """
    Mapeo de variables de un punto para construir payload dinámico.

    GET /api/ik/point/{id}/variables/
    Auth: Token

    Response:
    {
        "point_id": 1,
        "point_title": "Pozo 1",
        "variables": [
            {
                "id": 42,
                "str_variable": "ai1ActualValue",
                "label": "Caudal",
                "type_variable": "CAUDAL",
                "display_key": "caudal",
                "min_value": "0.0000",
                "max_value": "5000.0000"
            }
        ],
        "mapping": {
            "42": "caudal"
        }
    }
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, point_id):
        user = request.user

        # Permisos
        if user.is_staff or user.is_superuser:
            point_qs = CatchmentPoint.objects.all()
        else:
            point_qs = CatchmentPoint.objects.filter(
                Q(owner_user=user) | Q(users_viewers=user)
            ).distinct()

        try:
            point = point_qs.select_related(
                'project', 'project__client'
            ).prefetch_related(
                Prefetch(
                    'schemes',
                    queryset=SchemesCatchment.objects.prefetch_related(
                        Prefetch(
                            'variables',
                            queryset=Variable.objects.all().order_by('type_variable', 'str_variable')
                        )
                    )
                ),
            ).get(id=point_id)
        except CatchmentPoint.DoesNotExist:
            return Response(
                {"error": "Punto no encontrado o sin permisos"},
                status=status.HTTP_404_NOT_FOUND
            )

        variables_data = []
        mapping = {}

        for scheme in point.schemes.all():
            for v in scheme.variables.all():
                var_info = {
                    "id": v.id,
                    "str_variable": v.str_variable,
                    "label": v.label,
                    "type_variable": v.type_variable,
                    "display_key": v.display_key or v.type_variable,
                    "min_value": str(v.min_value) if v.min_value is not None else None,
                    "max_value": str(v.max_value) if v.max_value is not None else None,
                }
                variables_data.append(var_info)
                mapping[str(v.id)] = v.display_key or v.type_variable

        return Response({
            "point_id": point.id,
            "point_title": point.title,
            "variables": variables_data,
            "mapping": mapping,
        })
