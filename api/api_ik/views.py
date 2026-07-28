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
from rest_framework.pagination import PageNumberPagination
from django.contrib.auth import authenticate
from django.db.models import (
    Count, Q, Prefetch, Sum, Avg, F, FloatField
)
from django.db.models.functions import TruncDate
from django.utils import timezone

from api.core.models import (
    User,
    CatchmentPoint,
    InteractionDetail,
    ProfileDataConfigCatchment,
    ProfileIkoluCatchment,
    DgaDataConfigCatchment,
    NotificationsCatchment,
    SchemesCatchment,
    Variable,
    CounterResetLog,
)
from api.core.models.alerts import AlertRule, SystemEvent
from .throttles import (
    LoginRateThrottle, BatchRateThrottle, SummaryRateThrottle,
    DashboardRateThrottle, PublicReadRateThrottle,
)


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

    throttle_classes = [SummaryRateThrottle]
    def get(self, request):
        user = request.user

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
            Prefetch(
                'interactiondetail_set',
                queryset=InteractionDetail.objects.order_by('-date_time_medition')[:1],
                to_attr='latest_interaction'
            ),
        ).annotate(
            alerts_count=Count('notifications', filter=Q(notifications__is_active=True)),
        )

        # ── Conteo de alertas del nuevo subsistema por punto ──
        point_ids = [p.id for p in points]
        alert_rule_counts = {
            item['point_catchment']: item['count']
            for item in AlertRule.objects.filter(
                point_catchment_id__in=point_ids,
                is_active=True,
                legacy_notification_id__isnull=True,
            ).values('point_catchment').annotate(count=Count('id'))
        }

        points_list = list(points)
        total_count = len(points_list)

        points_data = []
        active_points = 0
        points_with_alerts = 0

        for p in points_list:
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

            # Última telemetría (precargada vía Prefetch)
            li = p.latest_interaction[0] if p.latest_interaction else None
            latest = {
                'date_time_medition': li.date_time_medition.isoformat() if li and li.date_time_medition else None,
                'flow': str(li.flow) if li and li.flow is not None else None,
                'total': li.total if li else None,
                'nivel': str(li.nivel) if li and li.nivel is not None else None,
                'water_table': str(li.water_table) if li and li.water_table is not None else None,
                'is_error': li.is_error if li and li.is_error is not None else False,
                'days_not_connection': li.days_not_conection if li and li.days_not_conection is not None else 0,
                'variable_values': li.variable_values if li else {},
            }

            # Activo: sin días de desconexión
            total_alerts = p.alerts_count + alert_rule_counts.get(p.id, 0)
            is_active = (li.days_not_conection == 0) if li and li.days_not_conection is not None else True
            if is_active:
                active_points += 1
            if total_alerts > 0:
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
                'alerts_count': total_alerts,
            })

        # Paginación opcional (no rompe compatibilidad hacia atrás)
        limit = request.query_params.get('limit')
        offset = request.query_params.get('offset')
        pagination_meta = None
        if limit is not None:
            try:
                limit = min(int(limit), 200)
                offset = max(int(offset or 0), 0)
                points_data = points_data[offset:offset + limit]
                pagination_meta = {
                    'limit': limit,
                    'offset': offset,
                    'total': total_count,
                }
            except (ValueError, TypeError):
                pass

        response = {
            'points': points_data,
            'total_points': total_count,
            'active_points': active_points,
            'points_with_alerts': points_with_alerts,
        }
        if pagination_meta:
            response['meta'] = pagination_meta
        return Response(response)


class PointSummaryView(APIView):
    """
    Resumen de un punto específico con última telemetría.

    GET /api/ik/point/{id}/summary/
    Auth: Token
    """
    permission_classes = [IsAuthenticated]

    throttle_classes = [SummaryRateThrottle]
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
                Prefetch(
                    'interactiondetail_set',
                    queryset=InteractionDetail.objects.order_by('-date_time_medition')[:1],
                    to_attr='latest_interaction'
                ),
            ).annotate(
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

        li = point.latest_interaction[0] if point.latest_interaction else None
        is_active = (li.days_not_conection == 0) if li and li.days_not_conection is not None else True

        # ── Sumar alertas del nuevo subsistema ──
        new_alerts = AlertRule.objects.filter(
            point_catchment_id=point.id, is_active=True, legacy_notification_id__isnull=True
        ).count()
        total_alerts = point.alerts_count + new_alerts

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
                'date_time_medition': li.date_time_medition.isoformat() if li and li.date_time_medition else None,
                'flow': str(li.flow) if li and li.flow is not None else None,
                'total': li.total if li else None,
                'nivel': str(li.nivel) if li and li.nivel is not None else None,
                'water_table': str(li.water_table) if li and li.water_table is not None else None,
                'is_error': li.is_error if li and li.is_error is not None else False,
                'days_not_connection': li.days_not_conection if li and li.days_not_conection is not None else 0,
                'variable_values': li.variable_values if li else {},
            },
            'alerts_count': total_alerts,
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

    throttle_classes = [SummaryRateThrottle]
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

            # Paginación opcional (no rompe compatibilidad)
            limit = request.query_params.get('limit')
            offset = request.query_params.get('offset')
            if limit is not None:
                try:
                    limit = min(int(limit), 200)
                    offset = max(int(offset or 0), 0)
                    result = result[offset:offset + limit]
                except (ValueError, TypeError):
                    pass

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

        # Paginación opcional (no rompe compatibilidad)
        limit = request.query_params.get('limit')
        offset = request.query_params.get('offset')
        if limit is not None:
            try:
                limit = min(int(limit), 200)
                offset = max(int(offset or 0), 0)
                result = result[offset:offset + limit]
            except (ValueError, TypeError):
                pass

        return Response(result)



class DashboardPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100

    def get_paginated_response(self, data):
        return Response({
            'count': self.page.paginator.count,
            'next': self.get_next_link(),
            'previous': self.get_previous_link(),
            'points': data['points'],
            'status_today': data['status_today'],
            'last_7': data['last_7'],
            'chat_quota': data['chat_quota'],
        })


class DashboardStatsView(APIView):
    """
    Stats generales para el Centro de Control (KPIs del dashboard).

    GET /api/ik/dashboard_stats/
    Auth: Token

    - Usuario normal: stats solo de sus puntos (owner + viewer)
    - Staff/Superuser: stats de todos los puntos
    """
    permission_classes = [IsAuthenticated]

    throttle_classes = [DashboardRateThrottle]
    def get(self, request):
        user = request.user
        from django.utils import timezone
        from datetime import date, datetime, timedelta
        from django.db.models import Avg, Sum
        from collections import defaultdict

        # Filtrar puntos según permisos (ordenados alfabéticamente por nombre)
        if user.is_staff or user.is_superuser:
            point_ids = list(
                CatchmentPoint.objects.order_by('title').values_list('id', flat=True)
            )
        else:
            owned_ids = set(
                user.owned_catchment_points.values_list('id', flat=True)
            )
            viewed_ids = set(
                user.viewed_catchment_points.values_list('id', flat=True)
            )
            all_ids = owned_ids | viewed_ids
            point_ids = list(
                CatchmentPoint.objects.filter(id__in=all_ids)
                .order_by('title')
                .values_list('id', flat=True)
            )

        total_points = len(point_ids)
        today = timezone.now().date()

        if total_points == 0:
            return Response({
                'points': {
                    'total': 0,
                    'with_telemetry': 0,
                    'with_gps': 0,
                    'with_compliance': 0,
                },
                'status_today': {
                    'connected': 0,
                    'disconnected': 0,
                },
                'count': 0,
                'next': None,
                'previous': None,
                'last_7': [],
                'chat_quota': get_chat_quota(request.user.id),
            })

        # --- Stats de puntos (siempre de TODOS los puntos) ---
        with_telemetry = ProfileDataConfigCatchment.objects.filter(
            point_catchment_id__in=point_ids,
            is_telemetry=True
        ).values('point_catchment_id').distinct().count()

        points_qs = CatchmentPoint.objects.filter(id__in=point_ids)
        with_gps = points_qs.exclude(
            Q(lat__isnull=True) | Q(lat='') | Q(lon__isnull=True) | Q(lon='')
        ).count()

        # Compliance = DGA o SMA configurado
        with_compliance = DgaDataConfigCatchment.objects.filter(
            Q(point_catchment_id__in=point_ids),
            Q(send_dga=True) | Q(send_sma=True)
        ).filter(
            Q(send_dga=True, code_dga__isnull=False, code_dga__gt='') |
            Q(send_sma=True, sma_device_id__isnull=False, sma_device_id__gt='')
        ).values('point_catchment_id').distinct().count()

        # --- Status hoy ---
        today_start = timezone.make_aware(datetime.combine(today, datetime.min.time()))
        today_end = timezone.make_aware(datetime.combine(today, datetime.max.time()))
        connected_today = InteractionDetail.objects.filter(
            catchment_point_id__in=point_ids,
            date_time_medition__gte=today_start,
            date_time_medition__lte=today_end,
        ).values('catchment_point_id').distinct().count()
        disconnected_today = max(0, with_telemetry - connected_today)

        # --- Paginar puntos para last_7 ---
        paginator = DashboardPagination()
        page_qs = CatchmentPoint.objects.filter(id__in=point_ids).order_by('title')
        page = paginator.paginate_queryset(page_qs, request, view=self)
        page_points = list(page)
        page_point_ids = [p.id for p in page_points]

        # --- Precargar relaciones de la página para evitar N+1 ---
        page_points = CatchmentPoint.objects.filter(
            id__in=page_point_ids
        ).prefetch_related(
            Prefetch(
                'schemes',
                queryset=SchemesCatchment.objects.prefetch_related(
                    Prefetch(
                        'variables',
                        queryset=Variable.objects.only('scheme_catchment_id', 'type_variable'),
                        to_attr='_vars',
                    )
                ),
                to_attr='_page_schemes',
            ),
            Prefetch(
                'data_config_profiles',
                queryset=ProfileDataConfigCatchment.objects.only(
                    'point_catchment_id', 'is_telemetry', 'd1', 'd3'
                ),
                to_attr='_page_data_configs',
            ),
            Prefetch(
                'ikolu_profiles',
                queryset=ProfileIkoluCatchment.objects.only('point_catchment_id', 'entry_by_form'),
                to_attr='_page_ikolu_configs',
            ),
        )
        # Mantener el orden original de la página
        page_points_by_id = {p.id: p for p in page_points}
        page_points = [page_points_by_id[pid] for pid in page_point_ids]

        point_vars = {}
        for cp in page_points:
            var_types = set()
            for scheme in cp._page_schemes:
                for v in scheme._vars:
                    if v.type_variable:
                        var_types.add(v.type_variable.upper())

            # Si existen múltiples perfiles (legacy crea uno por defecto), usar el más reciente.
            profile = (
                max(cp._page_data_configs, key=lambda p: p.id)
                if cp._page_data_configs else None
            )
            d1_val = profile.d1 if profile else None
            d3_val = profile.d3 if profile else None
            is_telemetry = any(p.is_telemetry for p in cp._page_data_configs)
            is_form = any(p.entry_by_form for p in cp._page_ikolu_configs)

            point_vars[cp.id] = {
                'point_id': cp.id,
                'title': cp.title,
                'is_telemetry': is_telemetry,
                'is_form': is_form,
                'created_at': cp.created.isoformat() if hasattr(cp, 'created') and cp.created else None,
                'has_flow': any(v in ('CAUDAL', 'CAUDAL_PROMEDIO') for v in var_types),
                'has_level': any(v == 'NIVEL' for v in var_types),
                'variables': sorted(list(var_types)),
                'd1': float(d1_val) if d1_val is not None and d1_val > 0 else None,
                'd3': float(d3_val) if d3_val is not None and d3_val > 0 else None,
            }

        # --- Últimos 7 días: agregado en DB por punto/día ---
        start_date = today - timedelta(days=6)
        start_dt = timezone.make_aware(datetime.combine(start_date, datetime.min.time()))
        end_dt = timezone.make_aware(datetime.combine(today, datetime.max.time()))

        week_aggregated = InteractionDetail.objects.filter(
            catchment_point_id__in=page_point_ids,
            date_time_medition__gte=start_dt,
            date_time_medition__lte=end_dt,
            is_error=False,
        ).annotate(
            day=TruncDate('date_time_medition')
        ).values('catchment_point_id', 'day').annotate(
            consumption=Sum('total_diff'),
            avg_flow=Avg('flow'),
            avg_level=Avg('water_table'),
            measurements_count=Count('id'),
        ).order_by('catchment_point_id', 'day')

        by_point_date = {
            (row['catchment_point_id'], row['day']): row
            for row in week_aggregated
        }

        last_7 = []
        for pid in page_point_ids:
            pv = point_vars[pid]
            days = []
            week_flow_sum = 0.0
            week_flow_count = 0
            week_level_sum = 0.0
            week_level_count = 0
            total_m3 = 0.0
            total_measurements_week = 0

            for i in range(6, -1, -1):
                d = today - timedelta(days=i)
                row = by_point_date.get((pid, d))

                if row and row['measurements_count']:
                    mcount = row['measurements_count']
                    consumo = float(row['consumption'] or 0)
                    total_m3 += consumo
                    total_measurements_week += mcount

                    day_data = {
                        'date': str(d),
                        'consumption': round(consumo, 2),
                        'measurements_count': mcount,
                        'has_data': True,
                    }

                    if pv['has_flow']:
                        avg_f = float(row['avg_flow'] or 0)
                        day_data['avg_flow'] = round(max(0.0, avg_f), 2)
                        week_flow_sum += avg_f * mcount
                        week_flow_count += mcount
                    else:
                        day_data['avg_flow'] = None

                    if pv['has_level']:
                        avg_l = float(row['avg_level'] or 0)
                        day_data['avg_level'] = round(max(0.0, avg_l), 2)
                        week_level_sum += avg_l * mcount
                        week_level_count += mcount
                    else:
                        day_data['avg_level'] = None

                    days.append(day_data)
                else:
                    days.append({
                        'date': str(d),
                        'consumption': 0.0,
                        'measurements_count': 0,
                        'has_data': False,
                        'avg_flow': None,
                        'avg_level': None,
                    })

            last_7.append({
                'point_id': pv['point_id'],
                'title': pv['title'],
                'is_telemetry': pv['is_telemetry'],
                'is_form': pv['is_form'],
                'created_at': pv['created_at'],
                'variables': pv['variables'],
                'd1': pv['d1'],
                'd3': pv['d3'],
                'total_m3': round(total_m3, 2),
                'total_measurements_week': total_measurements_week,
                'avg_flow_week': round(week_flow_sum / week_flow_count, 2) if week_flow_count else None,
                'avg_level_week': round(week_level_sum / week_level_count, 2) if week_level_count else None,
                'days': days,
            })

        # --- Warnings (solo para puntos de esta página) ---
        week_ago = today - timedelta(days=7)

        all_resets = CounterResetLog.objects.filter(
            point_catchment_id__in=page_point_ids,
            created__date__gte=week_ago,
        ).order_by('-created')

        all_system_events = SystemEvent.objects.filter(
            point_catchment_id__in=page_point_ids,
            severity__in=['WARNING', 'CRITICAL'],
            created__date__gte=week_ago,
        ).order_by('-created')

        by_point_resets = defaultdict(list)
        for r in all_resets:
            by_point_resets[r.point_catchment_id].append(r)

        by_point_events = defaultdict(list)
        for e in all_system_events:
            by_point_events[e.point_catchment_id].append(e)

        for entry in last_7:
            pid = entry['point_id']
            point_warnings = []

            for r in by_point_resets.get(pid, []):
                msg = r.get_reset_type_display() or r.reset_type
                if r.total_before is not None:
                    msg += f" (total: {r.total_before})"
                point_warnings.append({
                    'time': r.created.isoformat() if r.created else None,
                    'date': timezone.localdate(r.created),
                    'type': 'Reinicio de contador',
                    'severity': 'Advertencia',
                    'message': msg,
                })

            for e in by_point_events.get(pid, []):
                point_warnings.append({
                    'time': e.created.isoformat() if e.created else None,
                    'date': timezone.localdate(e.created),
                    'type': e.get_event_type_display() or e.event_type,
                    'severity': e.get_severity_display() or e.severity,
                    'message': e.message or e.title,
                })

            for day in entry['days']:
                d = date.fromisoformat(day['date'])
                day_warnings = [w for w in point_warnings if w['date'] == d]
                day_warnings.sort(key=lambda x: x['time'] or '', reverse=True)
                day['warnings'] = [{k: v for k, v in w.items() if k != 'date'} for w in day_warnings]

        chat_quota = get_chat_quota(request.user.id)

        return paginator.get_paginated_response({
            'points': {
                'total': total_points,
                'with_telemetry': with_telemetry,
                'with_gps': with_gps,
                'with_compliance': with_compliance,
            },
            'status_today': {
                'connected': connected_today,
                'disconnected': disconnected_today,
            },
            'last_7': last_7,
            'chat_quota': chat_quota,
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

    throttle_classes = [DashboardRateThrottle]
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

    throttle_classes = [PublicReadRateThrottle]
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
    throttle_classes = [SummaryRateThrottle]

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


import json
import os
import logging
from datetime import timedelta
from django.conf import settings
from django.utils import timezone
from rest_framework import serializers

logger = logging.getLogger(__name__)

CHAT_DAILY_LIMIT = 12


def get_chat_quota(user_id: int) -> dict:
    """Obtiene la cuota diaria de chat para un usuario."""
    try:
        from django_redis import get_redis_connection
        con = get_redis_connection("default")
        today = timezone.now().strftime("%Y-%m-%d")
        key = f"chat_daily_limit:{user_id}:{today}"
        used = int(con.get(key) or 0)
        return {
            "limit": CHAT_DAILY_LIMIT,
            "used": used,
            "remaining": max(0, CHAT_DAILY_LIMIT - used),
        }
    except Exception:
        return {"limit": CHAT_DAILY_LIMIT, "used": 0, "remaining": CHAT_DAILY_LIMIT}


class ClientStatsChatSerializer(serializers.Serializer):
    """Validador para el endpoint de chat con stats del cliente."""
    message = serializers.CharField(required=True, min_length=1, max_length=2000)


class ClientStatsChatView(APIView):
    """
    Endpoint de interpretación de datos para el cliente.

    El backend calcula automáticamente los stats del dashboard del usuario
    autenticado y usa Gemini para responder basándose estrictamente en esos datos.

    POST /api/ik/chat/client/general_stats/
    Body: {
        "message": "¿Por qué P2 tiene 78601% de consumo?"
    }
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [DashboardRateThrottle]

    DAILY_LIMIT = CHAT_DAILY_LIMIT

    def _check_daily_limit(self, user_id: int) -> tuple[bool, int]:
        """Verifica si el usuario aún tiene preguntas disponibles hoy."""
        quota = get_chat_quota(user_id)
        used = quota["used"]
        if used >= self.DAILY_LIMIT:
            return False, used

        try:
            from django_redis import get_redis_connection
            con = get_redis_connection("default")
            today = timezone.now().strftime("%Y-%m-%d")
            key = f"chat_daily_limit:{user_id}:{today}"
            new_count = con.incr(key)
            if new_count == 1:
                con.expire(key, 86400)  # 24 horas
            return True, int(new_count)
        except Exception:
            # Si Redis falla, no bloqueamos el servicio
            return True, used

    def _call_gemini(self, prompt: str) -> str:
        """Llama a Gemini con el prompt construido."""
        api_key = getattr(settings, 'GEMINI_API_KEY', os.environ.get('GEMINI_API_KEY'))
        if not api_key:
            return "Error de configuración: falta GEMINI_API_KEY. Contacta a soporte."

        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel('gemini-2.0-flash')
            response = model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.2,
                    max_output_tokens=250,
                ),
            )
            return response.text.strip()
        except Exception as e:
            logger.exception("Error llamando a Gemini en ClientStatsChatView")
            return f"No pude procesar tu consulta en este momento. Error: {str(e)}"

    def _build_prompt(self, stats: dict, message: str) -> str:
        """Construye el prompt para Gemini enfocado en educación del cliente."""
        stats_json = json.dumps(stats, indent=2, ensure_ascii=False, default=str)
        return (
            "Eres el asistente virtual de Ikolu (Centro de Control), especializado en telemetría hidrológica.\n"
            "SmartHydro es el proveedor de telemetría y cumplimiento DGA; tú eres el asistente dentro de la app Ikolu.\n"
            "Tu único objetivo es ayudar al usuario a entender mejor sus datos de telemetría.\n"
            "NO eres un agente de soporte: NO realizas acciones, NO gestionas trámites y NO modificas configuraciones.\n"
            "Solo respondes preguntas para mejorar la interpretación de los datos.\n\n"
            "REGLAS IMPORTANTES:\n"
            "- NO te presentes en cada mensaje. El usuario ya sabe quién eres. Ve directo a la respuesta.\n"
            "- Si el usuario tiene un problema técnico o necesita gestión, indícale brevemente que escriba a soporte@smarthydro.cl.\n"
            "- Prioriza la EDUCACIÓN: explica qué es cada variable (caudal, totalizador, nivel freático, pulsos, consumo, addition, resets, vouchers DGA, etc.).\n"
            "- Usa lenguaje claro y accesible, como si le explicaras a alguien que no es experto pero necesita entender su operación.\n"
            "- Relaciona los datos del cliente con los conceptos: 'tu caudal de 46.6 L/s significa que estás extrayendo...'\n"
            "- Solo menciona problemas o alertas si el usuario pregunta específicamente por ellos o si sirven como ejemplo para explicar un concepto.\n"
            "- NO hagas inventario de alertas. NO listes punto por punto.\n"
            "- PROHIBIDO hacer listas con viñetas, asteriscos o numeración.\n"
            "- Sé EXTREMADAMENTE conciso: máximo 2 oraciones cortas. Salvo que el usuario pida una explicación detallada, responde en una sola frase si es posible.\n"
            "- No inventes datos. No halucines.\n\n"
            f"DATOS DEL CLIENTE:\n```json\n{stats_json}\n```\n\n"
            f"PREGUNTA DEL CLIENTE: {message}\n\n"
            "Responde en español."
        )

    def post(self, request):
        serializer = ClientStatsChatSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"error": "Datos inválidos", "details": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Verificar límite diario de 12 preguntas
        can_ask, used = self._check_daily_limit(request.user.id)
        if not can_ask:
            return Response(
                {
                    "error": "Has alcanzado el límite diario de 12 preguntas.",
                    "limit": self.DAILY_LIMIT,
                    "used": used,
                    "reset_at": (timezone.now() + timedelta(days=1)).strftime("%Y-%m-%d"),
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )

        message = serializer.validated_data["message"].strip()

        # Obtener stats directamente del dashboard (misma lógica, sin duplicar código)
        dashboard_view = DashboardStatsView()
        dashboard_response = dashboard_view.get(request)
        stats = dashboard_response.data

        prompt = self._build_prompt(stats, message)
        response_text = self._call_gemini(prompt)

        remaining = max(0, self.DAILY_LIMIT - used)

        return Response({
            "response": response_text,
            "daily_limit": self.DAILY_LIMIT,
            "used_today": used,
            "remaining_today": remaining,
            "timestamp": timezone.now().isoformat(),
        }, status=status.HTTP_200_OK)


class PointRecordsView(APIView):
    """
    Endpoint para obtener registros de telemetría de un punto en un rango de fechas.

    GET /api/ik/point/<id>/records/?start_date=2026-05-25&end_date=2026-05-25&limit=100

    Devuelve solo los campos esenciales para gráficos/tablas:
    - date_time, flow, total, total_diff, nivel, water_table, is_error

    - start_date / end_date: formato ISO (YYYY-MM-DD). Si no se envían, últimas 24h.
    - limit: máximo 500 registros (default 100).
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [DashboardRateThrottle]

    def get(self, request, point_id):
        from datetime import date, timedelta
        user = request.user

        # Verificar permisos
        if user.is_staff or user.is_superuser:
            point_qs = CatchmentPoint.objects.all()
        else:
            point_qs = CatchmentPoint.objects.filter(
                Q(owner_user=user) | Q(users_viewers=user)
            ).distinct()

        try:
            point = point_qs.get(id=point_id)
        except CatchmentPoint.DoesNotExist:
            return Response(
                {"error": "Punto no encontrado o sin permisos"},
                status=status.HTTP_404_NOT_FOUND
            )

        # Parámetros de fecha
        today = date.today()
        start_date_str = request.query_params.get('start_date')
        end_date_str = request.query_params.get('end_date')

        if start_date_str:
            try:
                start_date = date.fromisoformat(start_date_str)
            except ValueError:
                return Response({"error": "start_date inválido. Usa YYYY-MM-DD."}, status=400)
        else:
            start_date = today

        if end_date_str:
            try:
                end_date = date.fromisoformat(end_date_str)
            except ValueError:
                return Response({"error": "end_date inválido. Usa YYYY-MM-DD."}, status=400)
        else:
            end_date = today

        if start_date > end_date:
            return Response({"error": "start_date no puede ser mayor que end_date."}, status=400)

        # Límite de días (protección)
        if (end_date - start_date).days > 31:
            return Response({"error": "Rango máximo permitido: 31 días."}, status=400)

        # Limit
        try:
            limit = int(request.query_params.get('limit', 100))
            if limit < 1:
                limit = 1
            elif limit > 500:
                limit = 500
        except ValueError:
            limit = 100

        # Obtener addition del perfil para calcular total_raw (sin offset/addition)
        # DGA requiere el total sin la corrección acumulada por resets
        profile = ProfileDataConfigCatchment.objects.filter(point_catchment=point).first()
        addition = float(profile.addition) if profile and profile.addition else 0.0

        # Query optimizada
        records = InteractionDetail.objects.filter(
            catchment_point=point,
            date_time_medition__date__gte=start_date,
            date_time_medition__date__lte=end_date,
        ).order_by('-date_time_medition')[:limit]

        import pytz
        chile_tz = pytz.timezone('America/Santiago')

        data = []
        for r in records:
            total_raw = None
            if r.total:
                try:
                    total_val = float(r.total)
                    total_raw = round(total_val - addition, 2)
                    if total_raw < 0:
                        total_raw = 0
                except (ValueError, TypeError):
                    pass

            # Convertir a zona horaria Chile
            dt_chile = r.date_time_medition.astimezone(chile_tz) if r.date_time_medition else None
            dt_logger_chile = r.date_time_last_logger.astimezone(chile_tz) if r.date_time_last_logger else None

            data.append({
                'date_time': dt_chile.isoformat() if dt_chile else None,
                'date_time_last_logger': dt_logger_chile.isoformat() if dt_logger_chile else None,
                'days_not_connection': r.days_not_conection,
                'flow': float(r.flow) if r.flow is not None else None,
                'total': r.total,
                'total_raw': total_raw,
                'total_diff': r.total_diff,
                'pulses': r.pulses,
                'nivel': float(r.nivel) if r.nivel is not None else None,
                'water_table': float(r.water_table) if r.water_table is not None else None,
                'is_error': r.is_error,
            })

        return Response({
            'point_id': point.id,
            'point_name': point.title,
            'start_date': str(start_date),
            'end_date': str(end_date),
            'limit': limit,
            'count': len(data),
            'records': data,
        }, status=status.HTTP_200_OK)


class PointConfigView(APIView):
    """
    GET /api/ik/point/<id>/config/
    PATCH /api/ik/point/<id>/config/

    GET: Devuelve la config_data del punto (d1-d6, addition, is_telemetry,
    offsets y límites de procesamiento). Muy liviano, sin telemetría ni historial.

    PATCH: Actualiza los campos editables de la config. Solo owner del punto o
    staff/superuser. Body JSON con los campos a modificar.

    Auth: Token
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [DashboardRateThrottle]

    _EDITABLE_FIELDS = {
        'd1', 'd2', 'd3', 'd4', 'd5', 'd6',
        'addition', 'is_telemetry', 'nivel_offset',
        'max_diff_m3_per_hour', 'max_flow_ls', 'max_time_gap_hours',
        'reconnection_threshold_hours', 'replicate_on_missing',
        'use_transaction_atomic',
    }
    _DECIMAL_FIELDS = {
        'd1', 'd2', 'd3', 'd4', 'd5', 'addition', 'nivel_offset',
        'max_diff_m3_per_hour', 'max_flow_ls', 'max_time_gap_hours',
        'reconnection_threshold_hours',
    }
    _BOOLEAN_FIELDS = {'is_telemetry', 'replicate_on_missing', 'use_transaction_atomic'}
    _INTEGER_FIELDS = {'d6'}

    def _get_point(self, request, point_id, require_owner=False):
        user = request.user
        if user.is_staff or user.is_superuser:
            point_qs = CatchmentPoint.objects.all()
        else:
            if require_owner:
                point_qs = CatchmentPoint.objects.filter(owner_user=user)
            else:
                point_qs = CatchmentPoint.objects.filter(
                    Q(owner_user=user) | Q(users_viewers=user)
                ).distinct()

        try:
            return point_qs.get(id=point_id)
        except CatchmentPoint.DoesNotExist:
            return None

    def _get_profile(self, point):
        profile = ProfileDataConfigCatchment.objects.filter(point_catchment=point).first()
        if not profile:
            profile = ProfileDataConfigCatchment.objects.create(point_catchment=point)
        return profile

    def _serialize_profile(self, profile):
        return {
            "d1": str(profile.d1) if profile.d1 is not None else "0.00",
            "d2": str(profile.d2) if profile.d2 is not None else "0.00",
            "d3": str(profile.d3) if profile.d3 is not None else "0.00",
            "d4": str(profile.d4) if profile.d4 is not None else "0.00",
            "d5": str(profile.d5) if profile.d5 is not None else "0.00",
            "d6": profile.d6 if profile.d6 is not None else 0,
            "addition": str(profile.addition) if profile.addition is not None else "0.000",
            "is_telemetry": bool(profile.is_telemetry),
            "nivel_offset": str(profile.nivel_offset) if profile.nivel_offset is not None else "0.000",
            "max_diff_m3_per_hour": str(profile.max_diff_m3_per_hour) if profile.max_diff_m3_per_hour is not None else "500.00",
            "max_flow_ls": str(profile.max_flow_ls) if profile.max_flow_ls is not None else "150.00",
            "max_time_gap_hours": str(profile.max_time_gap_hours) if profile.max_time_gap_hours is not None else "2.00",
            "reconnection_threshold_hours": str(profile.reconnection_threshold_hours) if profile.reconnection_threshold_hours is not None else "2.00",
            "replicate_on_missing": bool(profile.replicate_on_missing),
            "use_transaction_atomic": bool(profile.use_transaction_atomic),
        }

    def get(self, request, point_id):
        point = self._get_point(request, point_id)
        if point is None:
            return Response(
                {"error": "Punto no encontrado o sin permisos"},
                status=status.HTTP_404_NOT_FOUND
            )

        profile = self._get_profile(point)
        return Response(self._serialize_profile(profile))

    def patch(self, request, point_id):
        from decimal import InvalidOperation, Decimal

        point = self._get_point(request, point_id, require_owner=True)
        if point is None:
            return Response(
                {"error": "Punto no encontrado o sin permisos"},
                status=status.HTTP_404_NOT_FOUND
            )

        if not request.data or not isinstance(request.data, dict):
            return Response(
                {"error": "Body JSON requerido."},
                status=status.HTTP_400_BAD_REQUEST
            )

        unknown = [k for k in request.data if k not in self._EDITABLE_FIELDS]
        if unknown:
            return Response(
                {"error": f"Campos no permitidos: {', '.join(unknown)}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        profile = self._get_profile(point)
        errors = {}

        for key, raw_value in request.data.items():
            if key in self._DECIMAL_FIELDS:
                try:
                    value = Decimal(str(raw_value))
                except (InvalidOperation, TypeError, ValueError):
                    errors[key] = "Debe ser un número decimal válido."
                    continue
            elif key in self._INTEGER_FIELDS:
                try:
                    value = int(raw_value)
                except (TypeError, ValueError):
                    errors[key] = "Debe ser un entero válido."
                    continue
            elif key in self._BOOLEAN_FIELDS:
                if isinstance(raw_value, str):
                    value = raw_value.lower() in ('true', '1', 'yes', 'on')
                else:
                    value = bool(raw_value)
            else:
                continue

            setattr(profile, key, value)

        if errors:
            return Response({"error": errors}, status=status.HTTP_400_BAD_REQUEST)

        profile.save()
        return Response(self._serialize_profile(profile))


class SystemEventsSummaryView(APIView):
    """
    GET /api/ik/system-events/summary/

    Resumen de eventos del sistema (SystemEvent) para informes y auditoría.
    Staff ve todos los puntos; usuarios normales solo los suyos.

    Query params:
        - days: int (default 7) — días hacia atrás desde hoy
        - point_id: int (opcional) — filtrar por punto específico

    Response:
    {
        "period_days": 7,
        "total_events": 45,
        "by_severity": {"CRITICAL": 3, "WARNING": 20, "INFO": 22},
        "by_type": {"MEASUREMENT_ERROR": 15, ...},
        "by_point": [
            {"point_id": 152, "point_title": "P2", "event_count": 12, "critical_count": 1, "warning_count": 8}
        ],
        "timeline": [
            {"date": "2026-05-25", "count": 5, "by_type": {"MEASUREMENT_ERROR": 3}}
        ],
        "recent_events": [
            {"id": 123, "event_type": "...", "title": "...", "severity": "...",
             "created": "...", "point_id": 152, "point_title": "P2", "extra_data": {...}}
        ]
    }
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [DashboardRateThrottle]

    def get(self, request):
        from django.db.models.functions import TruncDate
        from django.utils import timezone
        from datetime import timedelta

        user = request.user
        days = int(request.query_params.get("days", 7))
        point_id = request.query_params.get("point_id")

        # Determinar puntos visibles
        if user.is_staff or user.is_superuser:
            visible_points = CatchmentPoint.objects.all()
        else:
            visible_points = CatchmentPoint.objects.filter(
                Q(owner_user=user) | Q(users_viewers=user)
            ).distinct()

        visible_point_ids = list(visible_points.values_list("id", flat=True))
        if not visible_point_ids:
            return Response({
                "period_days": days,
                "total_events": 0,
                "by_severity": {},
                "by_type": {},
                "by_point": [],
                "timeline": [],
                "recent_events": [],
            })

        # Filtro base de eventos
        cutoff = timezone.now() - timedelta(days=days)
        events_qs = SystemEvent.objects.filter(
            created__gte=cutoff,
            point_catchment_id__in=visible_point_ids,
        )
        if point_id:
            try:
                pid = int(point_id)
                if pid in visible_point_ids:
                    events_qs = events_qs.filter(point_catchment_id=pid)
                else:
                    return Response(
                        {"error": "Punto no encontrado o sin permisos"},
                        status=status.HTTP_403_FORBIDDEN,
                    )
            except (ValueError, TypeError):
                pass

        # Total
        total_events = events_qs.count()

        # Por severidad
        by_severity = dict(
            events_qs.values("severity")
            .annotate(count=Count("id"))
            .values_list("severity", "count")
        )

        # Por tipo
        by_type = dict(
            events_qs.values("event_type")
            .annotate(count=Count("id"))
            .values_list("event_type", "count")
        )

        # Por punto
        by_point_raw = (
            events_qs.values("point_catchment_id", "point_catchment__title")
            .annotate(
                event_count=Count("id"),
                critical_count=Count("id", filter=Q(severity="CRITICAL")),
                warning_count=Count("id", filter=Q(severity="WARNING")),
            )
            .order_by("-event_count")[:20]
        )
        by_point = [
            {
                "point_id": row["point_catchment_id"],
                "point_title": row["point_catchment__title"] or f"Punto {row['point_catchment_id']}",
                "event_count": row["event_count"],
                "critical_count": row["critical_count"],
                "warning_count": row["warning_count"],
            }
            for row in by_point_raw
        ]

        # Timeline (por día)
        timeline_raw = (
            events_qs.annotate(date=TruncDate("created"))
            .values("date")
            .annotate(count=Count("id"))
            .order_by("date")
        )
        # También necesitamos conteos por tipo por día
        timeline = []
        for row in timeline_raw:
            date_str = str(row["date"])
            day_qs = events_qs.filter(created__date=row["date"])
            day_by_type = dict(
                day_qs.values("event_type")
                .annotate(count=Count("id"))
                .values_list("event_type", "count")
            )
            timeline.append({
                "date": date_str,
                "count": row["count"],
                "by_type": day_by_type,
            })

        # Eventos recientes (últimos 50)
        recent_qs = events_qs.order_by("-created")[:50]
        recent_events = []
        for ev in recent_qs:
            recent_events.append({
                "id": ev.id,
                "event_type": ev.event_type,
                "title": ev.title,
                "message": ev.message,
                "severity": ev.severity,
                "created": ev.created.isoformat() if ev.created else None,
                "point_id": ev.point_catchment_id,
                "point_title": ev.point_catchment.title if ev.point_catchment else None,
                "extra_data": ev.extra_data,
            })

        return Response({
            "period_days": days,
            "total_events": total_events,
            "by_severity": by_severity,
            "by_type": by_type,
            "by_point": by_point,
            "timeline": timeline,
            "recent_events": recent_events,
        })


class StaffUsersListView(APIView):
    """
    Lista de usuarios staff/superuser.

    GET /api/ik/staff_users/
    Auth: Token

    Response:
    [
      {
        "id": 1,
        "email": "admin@smarthydro.app",
        "username": "admin",
        "first_name": "Admin",
        "last_name": "Smarthydro",
        "is_staff": true,
        "is_superuser": true,
        "is_client_admin": false
      }
    ]
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [SummaryRateThrottle]

    def get(self, request):
        user = request.user
        if not (user.is_staff or user.is_superuser):
            return Response(
                {'error': 'No tiene permisos para ver esta lista.'},
                status=status.HTTP_403_FORBIDDEN
            )

        staff_users = User.objects.filter(
            Q(is_staff=True) | Q(is_superuser=True)
        ).order_by('first_name', 'last_name', 'email').only(
            'id', 'email', 'username', 'first_name', 'last_name',
            'is_staff', 'is_superuser', 'is_client_admin'
        )

        data = [
            {
                'id': u.id,
                'email': u.email,
                'username': u.username,
                'first_name': u.first_name,
                'last_name': u.last_name,
                'is_staff': u.is_staff,
                'is_superuser': u.is_superuser,
                'is_client_admin': u.is_client_admin,
            }
            for u in staff_users
        ]

        return Response(data)
