"""
Endpoint de Compliance DGA/SMA
==============================

GET /api/ik/compliance/

Retorna el listado de cumplimiento DGA/SMA para los puntos del usuario,
ordenado por % de consumo respecto al total autorizado (mayor primero).
Filtros: ?search=<nombre>&project_id=<id>

Auth: Token
Filtros por usuario (owner/viewer), staff ve todo.
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from rest_framework.pagination import PageNumberPagination

from django.db.models import Q, Sum, Exists, OuterRef
from django.core.paginator import Paginator
from django.utils import timezone
from api.core.models import CatchmentPoint, DgaDataConfigCatchment, InteractionDetail
from .throttles import DashboardRateThrottle


_COMPLIANCE_TYPE_ORDER = ['DGA', 'SMA']


def compliance_type_for_config(cfg):
    """
    Retorna la lista de tipos de compliance configurados, sin depender de si
    están activos.

    Regla:
    - code_dga que empiece con 'OB' (case-insensitive) → DGA.
    - code_dga que NO empiece con 'OB' → SMA.
    - sma_device_id presente → SMA.
    """
    if not cfg:
        return []
    types = set()
    code = (cfg.code_dga or '').strip()
    if code:
        if code.upper().startswith('OB'):
            types.add('DGA')
        else:
            types.add('SMA')
    if cfg.sma_device_id:
        types.add('SMA')
    return [t for t in _COMPLIANCE_TYPE_ORDER if t in types]


def _is_compliance_active_for_config(cfg):
    """Retorna True si la config tiene compliance DGA o SMA activo."""
    if not cfg:
        return False
    types = compliance_type_for_config(cfg)
    active_dga = 'DGA' in types and cfg.send_dga
    active_sma = 'SMA' in types and cfg.send_sma
    return active_dga or active_sma


class CompliancePagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100

    def get_paginated_response(self, data):
        return Response({
            'count': self.page.paginator.count,
            'next': self.get_next_link(),
            'previous': self.get_previous_link(),
            'points': data['points'],
        })


class ComplianceListView(APIView):
    """
    GET /api/ik/compliance/

    Paginación: ?page=1&page_size=10 (default 10, max 100)
    Filtros: ?search=<nombre>&project_id=<id>&standard=<estandar>&active_only=true
    Orden: ?order_by=default (activos primero, luego % consumido desc) |
            pct_consumed_desc | pct_consumed_asc |
            point_name_asc | point_name_desc |
            exceedances_desc | near_limit_desc
    Retorna:
    {
        "count": N,
        "next": "...",
        "previous": null,
        "points": [...]
    }
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [DashboardRateThrottle]

    def get(self, request):
        from datetime import date, datetime, timedelta
        from django.core.paginator import Paginator

        user = request.user
        today = date.today()
        current_year = today.year
        year_start = timezone.make_aware(datetime(current_year, 1, 1, 0, 0, 0))
        year_end = timezone.make_aware(datetime(current_year, 12, 31, 23, 59, 59))

        # Por defecto se listan los puntos accesibles que tienen compliance
        # configurado (código DGA o SMA), activo o inactivo.
        # ?active_only=true filtra solo los activos.
        active_only = request.query_params.get('active_only', 'false').lower() == 'true'

        # Puntos accesibles
        if user.is_staff or user.is_superuser:
            points_qs = CatchmentPoint.objects.order_by('title')
        else:
            owned_ids = set(
                user.owned_catchment_points.values_list('id', flat=True)
            )
            viewed_ids = set(
                user.viewed_catchment_points.values_list('id', flat=True)
            )
            points_qs = CatchmentPoint.objects.filter(
                id__in=owned_ids | viewed_ids
            ).order_by('title')

        # Filtrar solo puntos con compliance configurado
        has_compliance_q = Exists(
            DgaDataConfigCatchment.objects.filter(
                point_catchment_id=OuterRef('id'),
            ).filter(
                Q(code_dga__isnull=False, code_dga__gt='')
                | Q(sma_device_id__isnull=False, sma_device_id__gt='')
            )
        )
        has_active_compliance_q = Exists(
            DgaDataConfigCatchment.objects.filter(
                point_catchment_id=OuterRef('id'),
            ).filter(
                (Q(send_dga=True) & Q(code_dga__isnull=False, code_dga__gt=''))
                | (Q(send_sma=True) & Q(sma_device_id__isnull=False, sma_device_id__gt=''))
            )
        )
        points_qs = points_qs.filter(
            has_active_compliance_q if active_only else has_compliance_q
        )

        project_id = request.query_params.get('project_id')
        if project_id:
            try:
                points_qs = points_qs.filter(project_id=int(project_id))
            except (ValueError, TypeError):
                return Response(
                    {'error': 'project_id debe ser un entero.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        search = request.query_params.get('search', '').strip()
        if search:
            points_qs = points_qs.filter(
                Q(title__icontains=search)
                | Exists(
                    DgaDataConfigCatchment.objects.filter(
                        point_catchment_id=OuterRef('id'),
                    ).filter(
                        Q(code_dga__icontains=search)
                        | Q(sma_device_id__icontains=search)
                    )
                )
            )

        points_qs = points_qs.select_related('project__client')
        point_ids = list(points_qs.values_list('id', flat=True))

        if not point_ids:
            return Response({
                "count": 0,
                "next": None,
                "previous": None,
                "points": [],
            })

        # Consumo anual por punto (todos los puntos, no solo activos)
        annual_consumption_map = {
            item['catchment_point_id']: float(item['total_sum'] or 0.0)
            for item in InteractionDetail.objects.filter(
                catchment_point_id__in=point_ids,
                date_time_medition__gte=year_start,
                date_time_medition__lte=year_end,
            ).values('catchment_point_id').annotate(
                total_sum=Sum('total_diff')
            )
        }

        # Configs de compliance por punto. Si hay varias, preferir la activa
        # (send_dga + code_dga o send_sma + sma_device_id); si ambas lo son,
        # quedarse con la más reciente (-id) para evitar configs residuales.
        configs_map = {}
        for cfg in DgaDataConfigCatchment.objects.filter(
            point_catchment_id__in=point_ids
        ).order_by('-id'):
            existing = configs_map.get(cfg.point_catchment_id)
            if existing is None:
                configs_map[cfg.point_catchment_id] = cfg
            elif _is_compliance_active_for_config(cfg) and not _is_compliance_active_for_config(existing):
                configs_map[cfg.point_catchment_id] = cfg

        # Filtro por estándar (aplicado sobre la config seleccionada)
        standard_param = request.query_params.get('standard', '').strip()
        standard_filters = []
        if standard_param:
            valid_standards = {
                'SIN_ESTANDAR', 'MAYOR', 'MEDIO', 'MENOR', 'CAUDALES_MUY_PEQUENOS'
            }
            standard_filters = [s.strip().upper() for s in standard_param.split(',') if s.strip()]
            invalid = [s for s in standard_filters if s not in valid_standards]
            if invalid:
                return Response(
                    {'error': f'standard inválido: {", ".join(invalid)}. Opciones: {", ".join(valid_standards)}'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Filtro por tipo DGA (superficial/subterraneo)
        type_dga_param = request.query_params.get('type_dga', '').strip()
        type_dga_filters = []
        if type_dga_param:
            valid_types = {'SUPERFICIAL', 'SUBTERRANEO'}
            type_dga_filters = [t.strip().upper() for t in type_dga_param.split(',') if t.strip()]
            invalid = [t for t in type_dga_filters if t not in valid_types]
            if invalid:
                return Response(
                    {'error': f'type_dga inválido: {", ".join(invalid)}. Opciones: {", ".join(valid_types)}'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Ordenamiento
        order_by = request.query_params.get('order_by', 'default')
        valid_order_keys = {
            'default',
            'pct_consumed_desc',
            'pct_consumed_asc',
            'point_name_asc',
            'point_name_desc',
            'exceedances_desc',
            'near_limit_desc',
        }
        if order_by not in valid_order_keys:
            return Response(
                {'error': f'order_by inválido. Opciones: {", ".join(valid_order_keys)}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        points_all = list(points_qs)
        for p in points_all:
            cfg = configs_map.get(p.id)
            p._cfg = cfg
            p._pct_consumed = self._pct_for_point(p, annual_consumption_map)
            p._is_active = _is_compliance_active_for_config(cfg)

        if active_only:
            points_all = [p for p in points_all if p._is_active]

        if standard_filters:
            standard_set = set(standard_filters)
            points_all = [
                p for p in points_all
                if p._cfg and p._cfg.standard and p._cfg.standard.upper() in standard_set
            ]

        if type_dga_filters:
            type_dga_set = set(type_dga_filters)
            points_all = [
                p for p in points_all
                if p._cfg and p._cfg.type_dga and p._cfg.type_dga.upper() in type_dga_set
            ]

        # Conteos de excedencias y cercanos al límite (todos los puntos,
        # porque pueden usarse para ordenar)
        flow_exceedances_count = {p.id: 0 for p in points_all}
        near_limit_records_count = {p.id: 0 for p in points_all}

        threshold_map = {}
        for p in points_all:
            cfg = p._cfg
            if cfg and cfg.flow_granted_dga is not None and float(cfg.flow_granted_dga) > 0:
                threshold_map[p.id] = float(cfg.flow_granted_dga)

        if threshold_map:
            lookback_date = timezone.make_aware(
                datetime.combine(today - timedelta(days=90), datetime.min.time())
            )
            for cp_id, auth_flow in threshold_map.items():
                base_qs = InteractionDetail.objects.filter(
                    catchment_point_id=cp_id,
                    date_time_medition__gte=lookback_date,
                )
                flow_exceedances_count[cp_id] = base_qs.filter(
                    flow__gt=auth_flow
                ).count()
                near_limit_records_count[cp_id] = base_qs.filter(
                    flow__gte=auth_flow * 0.9,
                    flow__lte=auth_flow,
                ).count()

        # Orden: activos primero; luego según criterio elegido.
        if order_by == 'default':
            points_all.sort(
                key=lambda p: (
                    not p._is_active,
                    p._pct_consumed is None,
                    -(p._pct_consumed or 0),
                ),
            )
        elif order_by == 'pct_consumed_desc':
            points_all.sort(
                key=lambda p: (
                    not p._is_active,
                    p._pct_consumed is None,
                    -(p._pct_consumed or 0),
                ),
            )
        elif order_by == 'pct_consumed_asc':
            points_all.sort(
                key=lambda p: (
                    not p._is_active,
                    p._pct_consumed is None,
                    p._pct_consumed or 0,
                ),
            )
        elif order_by == 'point_name_asc':
            points_all.sort(
                key=lambda p: (not p._is_active, p.title or '')
            )
        elif order_by == 'point_name_desc':
            points_all.sort(
                key=lambda p: (p._is_active, p.title or ''), reverse=True
            )
        elif order_by == 'exceedances_desc':
            points_all.sort(
                key=lambda p: (
                    not p._is_active,
                    -flow_exceedances_count.get(p.id, 0),
                )
            )
        elif order_by == 'near_limit_desc':
            points_all.sort(
                key=lambda p: (
                    not p._is_active,
                    -near_limit_records_count.get(p.id, 0),
                )
            )

        # Paginar
        page_size_param = request.query_params.get('page_size', 10)
        try:
            page_size = max(1, min(int(page_size_param), 100))
        except (ValueError, TypeError):
            page_size = 10

        page_number_param = request.query_params.get('page', 1)
        try:
            page_number = max(1, int(page_number_param))
        except (ValueError, TypeError):
            page_number = 1

        django_paginator = Paginator(points_all, page_size)
        page_obj = django_paginator.get_page(page_number)
        page_points = list(page_obj.object_list)
        page_point_ids = [p.id for p in page_points]

        # Último registro con voucher o general por punto
        last_map = {}
        voucher_ids = set()
        for cp_id in page_point_ids:
            last_voucher = InteractionDetail.objects.filter(
                catchment_point_id=cp_id,
                n_voucher__isnull=False
            ).order_by('-date_time_medition').first()
            if last_voucher:
                last_map[cp_id] = last_voucher
                voucher_ids.add(cp_id)

        for cp_id in page_point_ids:
            if cp_id in voucher_ids:
                continue
            last_any = InteractionDetail.objects.filter(
                catchment_point_id=cp_id
            ).order_by('-date_time_medition').first()
            if last_any:
                last_map[cp_id] = last_any

        points = [
            self._build_compliance_item(
                p,
                annual_consumption_map,
                flow_exceedances_count,
                near_limit_records_count,
                last_map,
            )
            for p in page_points
        ]

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
            'points': points,
        })

    def _pct_for_point(self, point, annual_consumption_map):
        cfg = getattr(point, '_cfg', None)
        if not cfg or cfg.total_granted_dga is None:
            return None
        total = float(cfg.total_granted_dga)
        if total <= 0:
            return None
        consumed = annual_consumption_map.get(point.id, 0.0)
        return (consumed * 100.0) / total

    def _build_compliance_item(self, point, annual_consumption_map,
                               flow_exceedances_count, near_limit_records_count,
                               last_map):
        cfg = getattr(point, '_cfg', None)
        cp_id = point.id
        annual_consumption = annual_consumption_map.get(cp_id, 0.0)

        if cfg:
            standard = cfg.standard or 'SIN_ESTANDAR'
            type_dga = cfg.type_dga or 'NO_DEFINIDO'
            authorized_total = (
                float(cfg.total_granted_dga)
                if cfg.total_granted_dga is not None else None
            )
            pct_consumed = getattr(point, '_pct_consumed', None)
            auth_flow = (
                float(cfg.flow_granted_dga)
                if cfg.flow_granted_dga is not None else None
            )
            code = cfg.code_dga or cfg.sma_device_id
            compliance_type = compliance_type_for_config(cfg)
            compliance_active = _is_compliance_active_for_config(cfg)
        else:
            standard = None
            type_dga = None
            authorized_total = None
            pct_consumed = None
            auth_flow = None
            code = None
            compliance_type = []
            compliance_active = False

        exceeded_count = flow_exceedances_count.get(cp_id, 0)
        flow_history = {
            'count': exceeded_count,
            'has_more': exceeded_count > 20,
            'threshold': auth_flow,
        }

        near_count = near_limit_records_count.get(cp_id, 0)
        near_limit_history = {
            'count': near_count,
            'has_more': near_count > 20,
            'threshold': auth_flow,
        }

        last_sent = last_map.get(cp_id)
        current_flow = round(float(last_sent.flow or 0), 2) if last_sent else 0.0
        compliance_warning = self._build_warning(
            auth_flow=auth_flow, current_flow=current_flow
        )

        return {
            'point_id': cp_id,
            'project_id': point.project_id,
            'point_name': point.title,
            'client_name': (
                point.project.client.name
                if point.project and point.project.client else None
            ),
            'code': code,
            'compliance_type': compliance_type,
            'standard': standard,
            'type_dga': type_dga,
            'compliance_active': compliance_active,
            'authorized_flow': auth_flow,
            'authorized_total': authorized_total,
            'annual_consumption': round(annual_consumption, 2),
            'pct_consumed': pct_consumed,
            'flow': current_flow,
            'water_table': round(float(last_sent.water_table or 0), 2) if last_sent else 0.0,
            'flow_history': flow_history,
            'near_limit_history': near_limit_history,
            'compliance_warning': compliance_warning,
            'voucher': last_sent.n_voucher if last_sent else None,
        }

    def _build_warning(self, auth_flow, current_flow):
        has_flow_data = auth_flow is not None and auth_flow > 0

        if not has_flow_data:
            return {'level': 'unknown'}

        if current_flow is not None and current_flow > 0:
            if current_flow > auth_flow:
                return {'level': 'critical'}

        flow_pct = round((current_flow / auth_flow) * 100, 2) if current_flow is not None and current_flow > 0 else 0.0
        if flow_pct >= 90.0:
            return {'level': 'warning'}

        return {'level': 'safe'}


class ToggleComplianceView(APIView):
    """
    POST /api/ik/management/toggle_compliance/

    Activa/desactiva compliance DGA de un punto (toggle send_dga).

    Body: {"point_id": 183}
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        point_id = request.data.get('point_id')
        if not point_id:
            return Response(
                {'error': 'point_id es requerido'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Verificar acceso al punto
        user = request.user
        if user.is_staff or user.is_superuser:
            point = CatchmentPoint.objects.filter(id=point_id).first()
        else:
            point = CatchmentPoint.objects.filter(
                Q(id=point_id),
                Q(owner_user=user) | Q(users_viewers=user),
            ).first()

        if not point:
            return Response(
                {'error': 'Punto no encontrado o sin acceso'},
                status=status.HTTP_404_NOT_FOUND,
            )

        config, created = DgaDataConfigCatchment.objects.get_or_create(
            point_catchment=point,
            defaults={
                'send_dga': True,
                'standard': 'SIN_ESTANDAR',
                'type_dga': 'SUBTERRANEO',
            },
        )

        if not created:
            config.send_dga = not config.send_dga
            config.save(update_fields=['send_dga'])

        return Response({
            'success': True,
            'point_id': point.id,
            'send_dga': config.send_dga,
            'send_sma': config.send_sma,
            'compliance_active': config.send_dga or config.send_sma,
        })


class _ComplianceHistoryBaseView(APIView):
    """Base para endpoints de detalle de caudal (excedencias / cercanos al límite)."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [DashboardRateThrottle]

    MAX_DAYS = 365
    DEFAULT_DAYS = 90

    def _get_point_and_threshold(self, request, point_id):
        user = request.user
        if user.is_staff or user.is_superuser:
            point = CatchmentPoint.objects.filter(id=point_id).first()
        else:
            point = CatchmentPoint.objects.filter(
                Q(id=point_id),
                Q(owner_user=user) | Q(users_viewers=user),
            ).first()

        if not point:
            return None, Response(
                {'error': 'Punto no encontrado o sin acceso'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # El detalle se puede consultar si el punto tiene compliance configurado,
        # activo o inactivo. Preferimos la config activa si hay varias.
        configs = DgaDataConfigCatchment.objects.filter(
            point_catchment=point,
        ).filter(
            Q(code_dga__isnull=False, code_dga__gt='')
            | Q(sma_device_id__isnull=False, sma_device_id__gt='')
        ).order_by('-id')

        cfg = None
        for c in configs:
            if _is_compliance_active_for_config(c):
                cfg = c
                break
        if not cfg and configs.exists():
            cfg = configs.first()

        if not cfg:
            return None, Response(
                {'error': 'El punto no tiene configuración de compliance'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        auth_flow = cfg.flow_granted_dga
        if auth_flow is None or float(auth_flow) <= 0:
            return None, Response(
                {'error': 'El punto no tiene caudal autorizado configurado'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return {'point': point, 'config': cfg, 'threshold': float(auth_flow)}, None

    def _parse_days(self, request):
        try:
            days = int(request.query_params.get('days', self.DEFAULT_DAYS))
        except (ValueError, TypeError):
            days = self.DEFAULT_DAYS
        return max(1, min(days, self.MAX_DAYS))

    def _paginate(self, request, queryset, threshold, point_id):
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

        paginator = Paginator(queryset, page_size)
        page_obj = paginator.get_page(page_number)

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

        results = [
            {
                'date_time': r['date_time_medition'].isoformat() if r['date_time_medition'] else None,
                'flow': float(r['flow']) if r['flow'] is not None else 0.0,
            }
            for r in page_obj.object_list
        ]

        return Response({
            'count': paginator.count,
            'next': _page_url(page_obj.next_page_number()) if page_obj.has_next() else None,
            'previous': _page_url(page_obj.previous_page_number()) if page_obj.has_previous() else None,
            'threshold': threshold,
            'point_id': point_id,
            'results': results,
        })


class ComplianceFlowHistoryView(_ComplianceHistoryBaseView):
    """
    GET /api/ik/compliance/<point_id>/flow_history/
        ?days=90        (default 90, max 365)
        &page=1
        &page_size=20   (max 100)

    Retorna los registros cuyo caudal superó el caudal autorizado.
    """

    def get(self, request, point_id):
        data, error = self._get_point_and_threshold(request, point_id)
        if error:
            return error

        days = self._parse_days(request)
        lookback_date = timezone.make_aware(
            timezone.datetime.combine(
                timezone.now().date() - timezone.timedelta(days=days),
                timezone.datetime.min.time(),
            )
        )

        qs = InteractionDetail.objects.filter(
            catchment_point_id=point_id,
            date_time_medition__gte=lookback_date,
            flow__gt=data['threshold'],
        ).order_by('-date_time_medition').values('date_time_medition', 'flow')

        return self._paginate(request, qs, data['threshold'], point_id)


class ComplianceNearLimitView(_ComplianceHistoryBaseView):
    """
    GET /api/ik/compliance/<point_id>/near_limit/
        ?days=90        (default 90, max 365)
        &page=1
        &page_size=20   (max 100)

    Retorna los registros entre el 90% y el 100% del caudal autorizado.
    """

    def get(self, request, point_id):
        data, error = self._get_point_and_threshold(request, point_id)
        if error:
            return error

        days = self._parse_days(request)
        lookback_date = timezone.make_aware(
            timezone.datetime.combine(
                timezone.now().date() - timezone.timedelta(days=days),
                timezone.datetime.min.time(),
            )
        )

        threshold = data['threshold']
        qs = InteractionDetail.objects.filter(
            catchment_point_id=point_id,
            date_time_medition__gte=lookback_date,
            flow__gte=threshold * 0.9,
            flow__lte=threshold,
        ).order_by('-date_time_medition').values('date_time_medition', 'flow')

        return self._paginate(request, qs, threshold, point_id)
