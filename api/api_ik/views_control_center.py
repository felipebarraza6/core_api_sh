from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from django.core.cache import cache
from django.utils import timezone
from django.db.models import Q, Sum, Count, Avg, Prefetch
from django.db.models.functions import TruncDate
from django.core.paginator import Paginator

from api.core.models import (
    CatchmentPoint,
    InteractionDetail,
    ProfileDataConfigCatchment,
    ProfileIkoluCatchment,
    DgaDataConfigCatchment,
    ProjectCatchments,
    SystemEvent,
    SchemesCatchment,
    Variable,
)
from .throttles import DashboardRateThrottle
from .views import get_chat_quota


class ControlCenterGeneralStatsView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [DashboardRateThrottle]

    WARNING_DAYS = 30
    CACHE_SECONDS = 300

    def get(self, request):
        user = request.user
        from datetime import date, datetime, timedelta

        cache_key = f"cc_general_stats:{user.id}"
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached)

        if user.is_staff or user.is_superuser:
            point_ids = list(
                CatchmentPoint.objects.order_by('title').values_list('id', flat=True)
            )
        else:
            owned = set(user.owned_catchment_points.values_list('id', flat=True))
            viewed = set(user.viewed_catchment_points.values_list('id', flat=True))
            point_ids = list(
                CatchmentPoint.objects.filter(id__in=owned | viewed)
                .order_by('title')
                .values_list('id', flat=True)
            )

        if not point_ids:
            payload = {
                'points': {
                    'total': 0,
                    'with_telemetry': 0,
                    'warnings': 0,
                    'with_compliance': 0,
                },
                'status_today': {
                    'connected': 0,
                    'disconnected': 0,
                },
                'projects': [],
                'chat_quota': get_chat_quota(request.user.id),
            }
            cache.set(cache_key, payload, self.CACHE_SECONDS)
            return Response(payload)

        today = date.today()
        warning_since = today - timedelta(days=self.WARNING_DAYS)

        # Rango de timestamps aware para hoy; evita cast a date en PostgreSQL.
        today_start = timezone.make_aware(datetime.combine(today, datetime.min.time()))
        tomorrow_start = today_start + timedelta(days=1)

        with_telemetry = ProfileDataConfigCatchment.objects.filter(
            point_catchment_id__in=point_ids,
            is_telemetry=True,
        ).values('point_catchment_id').distinct().count()

        warning_start = timezone.make_aware(datetime.combine(warning_since, datetime.min.time()))

        warnings = SystemEvent.objects.filter(
            point_catchment_id__in=point_ids,
            created__gte=warning_start,
        ).count()

        with_compliance = DgaDataConfigCatchment.objects.filter(
            Q(point_catchment_id__in=point_ids),
            Q(send_dga=True) | Q(send_sma=True),
        ).filter(
            Q(send_dga=True, code_dga__isnull=False, code_dga__gt='') |
            Q(send_sma=True, sma_device_id__isnull=False, sma_device_id__gt='')
        ).values('point_catchment_id').distinct().count()

        connected = InteractionDetail.objects.filter(
            catchment_point_id__in=point_ids,
            date_time_medition__gte=today_start,
            date_time_medition__lt=tomorrow_start,
        ).values('catchment_point_id').distinct().count()

        # Proyectos
        project_ids = CatchmentPoint.objects.filter(
            id__in=point_ids,
        ).values_list('project_id', flat=True).distinct()

        projects_qs = ProjectCatchments.objects.filter(
            id__in=project_ids,
        ).order_by('name').select_related('client')

        if user.is_staff or user.is_superuser:
            projects = [
                {
                    'id': p.id,
                    'name': f"{p.name} - {p.client.name}" if p.client else p.name,
                }
                for p in projects_qs
            ]
        else:
            projects = [{'id': p.id, 'name': p.name} for p in projects_qs]

        payload = {
            'points': {
                'total': len(point_ids),
                'with_telemetry': with_telemetry,
                'warnings': warnings,
                'with_compliance': with_compliance,
            },
            'status_today': {
                'connected': connected,
                'disconnected': max(0, with_telemetry - connected),
            },
            'projects': projects,
            'chat_quota': get_chat_quota(request.user.id),
        }
        cache.set(cache_key, payload, self.CACHE_SECONDS)
        return Response(payload)


class ControlCenterDailySummaryView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [DashboardRateThrottle]

    MAX_DAYS = 92

    def get(self, request):
        user = request.user
        from datetime import date, datetime, timedelta

        start_date_str = request.query_params.get('start_date')
        end_date_str = request.query_params.get('end_date')
        project_id = request.query_params.get('project_id')
        point_id = request.query_params.get('point_id')

        try:
            end_date = date.fromisoformat(end_date_str) if end_date_str else date.today()
            start_date = date.fromisoformat(start_date_str) if start_date_str else end_date - timedelta(days=6)
        except (ValueError, TypeError):
            return Response({'error': 'Formato de fecha inválido. Use YYYY-MM-DD.'}, status=400)

        if start_date > end_date:
            return Response({'error': 'start_date no puede ser posterior a end_date.'}, status=400)

        if (end_date - start_date).days > self.MAX_DAYS:
            return Response({'error': f'El rango máximo es {self.MAX_DAYS} días.'}, status=400)

        # Parse project_id / point_id antes de construir los querysets
        parsed_project_id = None
        parsed_point_id = None
        if project_id:
            try:
                parsed_project_id = int(project_id)
            except (ValueError, TypeError):
                return Response({'error': 'project_id debe ser un entero.'}, status=400)

        if point_id:
            try:
                parsed_point_id = int(point_id)
            except (ValueError, TypeError):
                return Response({'error': 'point_id debe ser un entero.'}, status=400)

        if user.is_staff or user.is_superuser:
            points_qs = CatchmentPoint.objects.order_by('title')
        else:
            owned = set(user.owned_catchment_points.values_list('id', flat=True))
            viewed = set(user.viewed_catchment_points.values_list('id', flat=True))
            points_qs = CatchmentPoint.objects.filter(id__in=owned | viewed).order_by('title')

        if parsed_project_id:
            points_qs = points_qs.filter(project_id=parsed_project_id)
        if parsed_point_id:
            points_qs = points_qs.filter(id=parsed_point_id)

        points = list(points_qs.values('id', 'title', 'project_id'))
        point_ids = [p['id'] for p in points]

        # Projects list — solo los proyectos de los puntos visibles
        all_project_ids = set(p['project_id'] for p in points if p['project_id'])
        projects_qs = ProjectCatchments.objects.filter(
            id__in=all_project_ids,
        ).order_by('name').select_related('client')

        if user.is_staff or user.is_superuser:
            projects = [
                {'id': p.id, 'name': f"{p.name} - {p.client.name}" if p.client else p.name}
                for p in projects_qs
            ]
        else:
            projects = [{'id': p.id, 'name': p.name} for p in projects_qs]

        date_range = []
        current = start_date
        while current <= end_date:
            date_range.append(current.isoformat())
            current += timedelta(days=1)

        days = {}
        for d in date_range:
            days[d] = {'total_consumption': 0}

        if point_ids:
            # Usar rango de timestamps aware para aprovechar el índice compuesto
            # (catchment_point_id, date_time_medition) y evitar el cast a date.
            start_dt = timezone.make_aware(datetime.combine(start_date, datetime.min.time()))
            end_dt = timezone.make_aware(datetime.combine(end_date, datetime.max.time()))

            daily_qs = InteractionDetail.objects.filter(
                catchment_point_id__in=point_ids,
                date_time_medition__gte=start_dt,
                date_time_medition__lte=end_dt,
            ).annotate(
                day=TruncDate('date_time_medition')
            ).values('day').annotate(
                total_consumption=Sum('total_diff'),
            ).order_by('day')

            for entry in daily_qs:
                d = entry['day']
                d_str = d.isoformat()
                consumption = entry['total_consumption']
                days[d_str] = {
                    'total_consumption': float(consumption) if consumption is not None else 0,
                }

        return Response({
            'date_range': date_range,
            'days': days,
            'projects': projects,
            'points': points,
        })


class ControlCenterProjectPointsView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [DashboardRateThrottle]

    def get(self, request):
        user = request.user
        project_id = request.query_params.get('project_id')

        if not project_id:
            return Response({'error': 'project_id es requerido.'}, status=400)

        try:
            project_id = int(project_id)
        except (ValueError, TypeError):
            return Response({'error': 'project_id debe ser un entero.'}, status=400)

        if user.is_staff or user.is_superuser:
            points_qs = CatchmentPoint.objects.order_by('title')
        else:
            owned = set(user.owned_catchment_points.values_list('id', flat=True))
            viewed = set(user.viewed_catchment_points.values_list('id', flat=True))
            points_qs = CatchmentPoint.objects.filter(id__in=owned | viewed).order_by('title')

        points_qs = points_qs.filter(project_id=project_id).prefetch_related(
            Prefetch(
                'dga_data_config_profiles',
                queryset=DgaDataConfigCatchment.objects.filter(
                    code_dga__isnull=False,
                ).exclude(code_dga=''),
                to_attr='_dga_configs',
            )
        )

        points = []
        for p in points_qs:
            code_obra = p._dga_configs[0].code_dga if p._dga_configs else None
            name = f"{p.title} ({code_obra})" if code_obra else p.title
            points.append({'id': p.id, 'name': name})

        return Response({'points': points})


# ---------------------------------------------------------------------------
# Control Center — List
# ---------------------------------------------------------------------------

VALID_ORDER_FIELDS = {
    'consumption':   ('consumption', True),   # (campo, descendente)
    '-consumption':  ('consumption', False),
    'avg_flow':      ('avg_flow',    True),
    '-avg_flow':     ('avg_flow',    False),
    'avg_level':     ('avg_level',   True),
    '-avg_level':    ('avg_level',   False),
    'warnings_count':      ('warnings_count', True),
    '-warnings_count':     ('warnings_count', False),
    'warnings_count_desc': ('warnings_count', True),
    'warnings_count_asc':  ('warnings_count', False),
}


class ControlCenterListView(APIView):
    """
    Lista paginada de puntos con datos agregados para un día específico.

    GET /api/ik/control_center/list/
        ?date=2025-06-24          (requerido)
        &project_id=2             (opcional)
        &order_by=consumption     (opcional: consumption/-consumption/avg_flow/-avg_flow/avg_level/-avg_level/warnings_count_desc/warnings_count_asc)
        &page=1
        &page_size=10             (max 50)
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [DashboardRateThrottle]

    def get(self, request):
        from datetime import date as date_type, datetime
        from django.core.paginator import Paginator

        # --- Validar date (requerido) ---
        date_str = request.query_params.get('date')
        if not date_str:
            return Response({'error': 'El parámetro date es requerido (YYYY-MM-DD).'}, status=400)
        try:
            query_date = date_type.fromisoformat(date_str)
        except (ValueError, TypeError):
            return Response({'error': 'Formato de fecha inválido. Use YYYY-MM-DD.'}, status=400)

        query_start = timezone.make_aware(datetime.combine(query_date, datetime.min.time()))
        query_end = timezone.make_aware(datetime.combine(query_date, datetime.max.time()))

        # --- Validar project_id ---
        project_id_str = request.query_params.get('project_id')
        project_id = None
        if project_id_str:
            try:
                project_id = int(project_id_str)
            except (ValueError, TypeError):
                return Response({'error': 'project_id debe ser un entero.'}, status=400)

        # --- order_by ---
        order_by_param = request.query_params.get('order_by', '')
        order_config = VALID_ORDER_FIELDS.get(order_by_param)  # None si inválido/vacío

        # --- Puntos accesibles ---
        user = request.user
        if user.is_staff or user.is_superuser:
            base_qs = CatchmentPoint.objects.select_related('project__client').order_by('title')
        else:
            owned = set(user.owned_catchment_points.values_list('id', flat=True))
            viewed = set(user.viewed_catchment_points.values_list('id', flat=True))
            base_qs = CatchmentPoint.objects.filter(
                id__in=owned | viewed
            ).select_related('project__client').order_by('title')

        if project_id:
            base_qs = base_qs.filter(project_id=project_id)

        # Cargar todos los puntos filtrados (son pocos cientos como máximo)
        all_points = list(base_qs)
        point_ids = [p.id for p in all_points]

        # --- Agregaciones del día en una sola query ---
        agg_map = {}
        if point_ids:
            agg_rows = InteractionDetail.objects.filter(
                catchment_point_id__in=point_ids,
                date_time_medition__gte=query_start,
                date_time_medition__lte=query_end,
            ).values('catchment_point_id').annotate(
                consumption=Sum('total_diff'),
                avg_flow=Avg('flow'),
                avg_level=Avg('nivel'),
                avg_water_table=Avg('water_table'),
                measurements_count=Count('id'),
            )
            agg_map = {row['catchment_point_id']: row for row in agg_rows}

        # --- Warnings del día por punto ---
        warnings_map = {}
        if point_ids:
            warnings_rows = SystemEvent.objects.filter(
                point_catchment_id__in=point_ids,
                created__date=query_date,
            ).values('point_catchment_id').annotate(
                warnings_count=Count('id'),
            )
            warnings_map = {row['point_catchment_id']: row['warnings_count'] for row in warnings_rows}

        # --- Ordenamiento en Python ---
        if order_config:
            field, descending = order_config

            def _sort_key(p):
                if field == 'warnings_count':
                    return warnings_map.get(p.id, 0)
                val = agg_map.get(p.id, {}).get(field)
                # None/nulls al final
                return (val is None, val or 0)

            all_points.sort(key=_sort_key, reverse=descending)

        # --- Paginación ---
        page_size_param = request.query_params.get('page_size', 10)
        try:
            page_size = max(1, min(int(page_size_param), 50))
        except (ValueError, TypeError):
            page_size = 10
        page_number_param = request.query_params.get('page', 1)
        try:
            page_number = max(1, int(page_number_param))
        except (ValueError, TypeError):
            page_number = 1

        django_paginator = Paginator(all_points, page_size)
        page_obj = django_paginator.get_page(page_number)
        page_points = list(page_obj.object_list)
        page_point_ids = [p.id for p in page_points]

        # --- Prefetch de relaciones SOLO para la página ---
        page_qs = CatchmentPoint.objects.filter(
            id__in=page_point_ids
        ).select_related('project__client').prefetch_related(
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
                'system_events',
                queryset=SystemEvent.objects.filter(created__date=query_date),
                to_attr='_day_events',
            ),
            Prefetch(
                'data_config_profiles',
                queryset=ProfileDataConfigCatchment.objects.only(
                    'point_catchment_id', 'is_telemetry'
                ),
                to_attr='_page_data_configs',
            ),
            Prefetch(
                'ikolu_profiles',
                queryset=ProfileIkoluCatchment.objects.only(
                    'point_catchment_id', 'entry_by_form'
                ),
                to_attr='_page_ikolu_configs',
            ),
        )
        page_points_by_id = {p.id: p for p in page_qs}
        page_points = [page_points_by_id[p.id] for p in page_points]

        # --- Construir resultados ---
        results = []
        for point in page_points:
            project = point.project
            is_admin = user.is_staff or user.is_superuser

            if project:
                if is_admin:
                    project_name = (
                        f"{project.name} - {project.client.name}"
                        if project.client else project.name
                    )
                else:
                    project_name = project.name
                proj_id = project.id
            else:
                project_name = None
                proj_id = None

            # Variables de los schemes precargados
            vars_set = set()
            for scheme in point._page_schemes:
                for v in scheme._vars:
                    if v.type_variable:
                        vars_set.add(v.type_variable.upper())
            variables = sorted(vars_set)

            metrics = agg_map.get(point.id, {})
            measurements_count = metrics.get('measurements_count', 0) or 0
            has_data = measurements_count > 0

            consumption_raw = metrics.get('consumption')
            consumption = float(consumption_raw) if consumption_raw is not None else 0.0

            avg_flow = None
            avg_level = None
            water_table = None

            if has_data:
                if any('CAUDAL' in v for v in variables):
                    raw = metrics.get('avg_flow')
                    avg_flow = round(max(0.0, float(raw)), 2) if raw is not None else None

                if any(v in ('NIVEL', 'NIVEL_FREATICO') for v in variables):
                    raw = metrics.get('avg_level')
                    avg_level = round(max(0.0, float(raw)), 2) if raw is not None else None

                raw_wt = metrics.get('avg_water_table')
                water_table = round(max(0.0, float(raw_wt)), 2) if raw_wt is not None else None

            is_telemetry = any(p.is_telemetry for p in point._page_data_configs)
            is_form = any(p.entry_by_form for p in point._page_ikolu_configs)

            results.append({
                'point_id': point.id,
                'point_name': point.title,
                'project_id': proj_id,
                'project_name': project_name,
                'is_telemetry': is_telemetry,
                'is_form': is_form,
                'status': 'connected' if has_data else 'disconnected',
                'measurements_count': measurements_count,
                'consumption': round(consumption, 2),
                'avg_flow': avg_flow,
                'avg_level': avg_level,
                'water_table': water_table,
                'variables': variables,
                'warnings_count': len(point._day_events),
            })

        # Construir respuesta paginada manualmente
        base_url = request.build_absolute_uri('?')

        def _page_url(page_num):
            if page_num is None or page_num < 1 or page_num > django_paginator.num_pages:
                return None
            from urllib.parse import urlencode, parse_qs, urlsplit, urlunsplit
            scheme, netloc, path, query, fragment = urlsplit(base_url)
            params = parse_qs(query, keep_blank_values=True)
            params['page'] = [str(page_num)]
            new_query = urlencode(params, doseq=True)
            return urlunsplit((scheme, netloc, path, new_query, fragment))

        return Response({
            'count': django_paginator.count,
            'next': _page_url(page_obj.next_page_number()) if page_obj.has_next() else None,
            'previous': _page_url(page_obj.previous_page_number()) if page_obj.has_previous() else None,
            'results': results,
        })


def _filter_system_events(qs, request):
    """Aplica filtros comunes de event_type, severity, start, end y search."""
    from datetime import datetime

    event_type_param = request.query_params.get('event_type')
    if event_type_param:
        valid_types = [c[0] for c in SystemEvent.EVENT_TYPE_CHOICES]
        types = [t.strip() for t in event_type_param.split(',') if t.strip()]
        invalid = [t for t in types if t not in valid_types]
        if invalid:
            return None, Response(
                {'error': f'event_type inválido: {", ".join(invalid)}'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        qs = qs.filter(event_type__in=types)

    severity_param = request.query_params.get('severity')
    if severity_param:
        valid_severities = [c[0] for c in SystemEvent.SEVERITY_CHOICES]
        severities = [s.strip() for s in severity_param.split(',') if s.strip()]
        invalid = [s for s in severities if s not in valid_severities]
        if invalid:
            return None, Response(
                {'error': f'severity inválido: {", ".join(invalid)}'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        qs = qs.filter(severity__in=severities)

    start_param = request.query_params.get('start')
    if start_param:
        try:
            start_dt = timezone.make_aware(datetime.fromisoformat(start_param))
            qs = qs.filter(created__gte=start_dt)
        except ValueError:
            return None, Response(
                {'error': 'start debe ser un datetime ISO válido.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

    end_param = request.query_params.get('end')
    if end_param:
        try:
            end_dt = timezone.make_aware(datetime.fromisoformat(end_param))
            qs = qs.filter(created__lte=end_dt)
        except ValueError:
            return None, Response(
                {'error': 'end debe ser un datetime ISO válido.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

    search = request.query_params.get('search', '').strip()
    if search:
        qs = qs.filter(
            Q(title__icontains=search) | Q(message__icontains=search)
        )

    return qs, None


def _point_display_name(point):
    """Devuelve 'Punto / Proyecto (Cliente)' evitando repetir proyecto/cliente."""
    if not point:
        return None
    project = point.project
    client_name = project.client.name if project and project.client else None
    project_name = project.name if project else None
    if project_name and client_name and project_name != client_name:
        return f"{point.title} / {project_name} ({client_name})"
    if project_name:
        return f"{point.title} / {project_name}"
    return point.title


def _paginate_system_events(qs, request):
    """Pagina queryset de SystemEvent y retorna diccionario de respuesta."""
    page_size_param = request.query_params.get('page_size', 20)
    try:
        page_size = max(1, min(int(page_size_param), 100))
    except (ValueError, TypeError):
        page_size = 20

    page_number_param = request.query_params.get('page', 1)
    try:
        page_number = max(1, int(page_number_param))
    except (ValueError, TypeError):
        page_number = 1

    paginator = Paginator(qs, page_size)
    page_obj = paginator.get_page(page_number)

    results = []
    for ev in page_obj.object_list:
        point = ev.point_catchment
        point_data = None
        if point:
            point_data = {
                'id': point.id,
                'title': point.title,
                'display_name': _point_display_name(point),
            }
        results.append({
            'id': ev.id,
            'event_type': ev.event_type,
            'severity': ev.severity,
            'title': ev.title,
            'message': ev.message,
            'created': ev.created.isoformat() if ev.created else None,
            'point': point_data,
            'extra_data': ev.extra_data,
        })

    base_url = request.build_absolute_uri('?')

    def _page_url(page_num):
        if page_num is None or page_num < 1 or page_num > paginator.num_pages:
            return None
        from urllib.parse import urlencode, parse_qs, urlsplit, urlunsplit
        scheme, netloc, path, query, fragment = urlsplit(base_url)
        params = parse_qs(query, keep_blank_values=True)
        params['page'] = [str(page_num)]
        new_query = urlencode(params, doseq=True)
        return urlunsplit((scheme, netloc, path, new_query, fragment))

    return {
        'count': paginator.count,
        'next': _page_url(page_obj.next_page_number()) if page_obj.has_next() else None,
        'previous': _page_url(page_obj.previous_page_number()) if page_obj.has_previous() else None,
        'results': results,
    }


class ControlCenterSystemEventsListView(APIView):
    """
    GET /api/ik/control_center/system_events/

    Listado paginado de eventos del sistema (SystemEvent) para los puntos
    a los que el usuario tiene acceso. Staff ve todos.

    Query params:
    - point_id: filtrar por un punto específico (se valida acceso)
    - event_type: filtrar por tipo(s), separados por coma
    - severity: filtrar por severidad(es), separadas por coma
    - start/end: rango de fechas ISO (2026-06-01T00:00:00)
    - search: búsqueda en título o mensaje (icontains)
    - page / page_size: paginación (default 20, max 100)
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [DashboardRateThrottle]

    def get(self, request):
        user = request.user

        if user.is_staff or user.is_superuser:
            accessible_qs = CatchmentPoint.objects.order_by('title')
        else:
            owned = set(user.owned_catchment_points.values_list('id', flat=True))
            viewed = set(user.viewed_catchment_points.values_list('id', flat=True))
            accessible_qs = CatchmentPoint.objects.filter(
                id__in=owned | viewed
            ).order_by('title')

        point_id_param = request.query_params.get('point_id')
        if point_id_param:
            try:
                point_id = int(point_id_param)
            except (ValueError, TypeError):
                return Response(
                    {'error': 'point_id debe ser un entero.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if not accessible_qs.filter(id=point_id).exists():
                return Response(
                    {'error': 'Punto no encontrado o sin acceso'},
                    status=status.HTTP_404_NOT_FOUND,
                )

        qs = SystemEvent.objects.select_related(
            'point_catchment__project__client'
        ).order_by('-created')

        if point_id_param:
            qs = qs.filter(point_catchment_id=point_id)
        else:
            accessible_ids = list(accessible_qs.values_list('id', flat=True))
            qs = qs.filter(point_catchment_id__in=accessible_ids)

        qs, error_response = _filter_system_events(qs, request)
        if error_response:
            return error_response

        return Response(_paginate_system_events(qs, request))


class ControlCenterSystemEventsPointDetailView(APIView):
    """
    GET /api/ik/control_center/system_events/<point_id>/

    Vista detallada de eventos del sistema para un punto específico.
    Mismo formato y filtros que el listado general, pero fijando el punto
    en la URL. Útil para el modal/vista detallada de un punto en el Centro
    de Control.

    Query params:
    - event_type: filtrar por tipo(s), separados por coma
    - severity: filtrar por severidad(es), separadas por coma
    - start/end: rango de fechas ISO (2026-06-01T00:00:00)
    - search: búsqueda en título o mensaje (icontains)
    - page / page_size: paginación (default 20, max 100)
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [DashboardRateThrottle]

    def get(self, request, point_id):
        user = request.user

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
                {'error': 'Punto no encontrado o sin acceso'},
                status=status.HTTP_404_NOT_FOUND,
            )

        qs = SystemEvent.objects.select_related(
            'point_catchment__project__client'
        ).filter(
            point_catchment=point
        ).order_by('-created')

        qs, error_response = _filter_system_events(qs, request)
        if error_response:
            return error_response

        return Response(_paginate_system_events(qs, request))
