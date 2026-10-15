"""
Observatorio georreferenciado público
=====================================

GET /api/ik/observatory/public/   — AllowAny: solo códigos DGA (OB*) con coords
GET /api/ik/observatory/points/   — IsAuthenticated: DGA + no-DGA del usuario (o todos si staff)

Respuesta mínima: id, lat, lon, code, code_kind, type_dga.
Sin cliente, título, telemetría ni credenciales.
"""

from django.db.models import Q, Prefetch
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes

from api.core.models import CatchmentPoint, DgaDataConfigCatchment
from api.core.serializers.catchment_points import PublicMapPointSerializer
from .throttles import PublicReadRateThrottle, SummaryRateThrottle


def _parse_coord(value):
    if value is None:
        return None
    text = str(value).strip().replace(',', '.')
    if not text:
        return None
    try:
        number = float(text)
    except (TypeError, ValueError):
        return None
    if number != number:  # NaN
        return None
    return number


def _code_kind(code):
    code = (code or '').strip()
    if not code:
        return None
    if code.upper().startswith('OB'):
        return 'DGA'
    return 'OTHER'


def _serialize_point(point, cfg):
    lat = _parse_coord(point.lat)
    lon = _parse_coord(point.lon)
    if lat is None or lon is None:
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None

    code = (cfg.code_dga or '').strip() if cfg else ''
    kind = _code_kind(code)
    if not kind:
        return None

    return {
        'id': point.id,
        'lat': lat,
        'lon': lon,
        'code': code,
        'code_kind': kind,
        'type_dga': (cfg.type_dga or None) if cfg else None,
    }


def _base_queryset():
    return CatchmentPoint.objects.exclude(
        Q(lat__isnull=True) | Q(lat='') | Q(lon__isnull=True) | Q(lon='')
    ).prefetch_related(
        Prefetch(
            'dga_data_config_profiles',
            queryset=DgaDataConfigCatchment.objects.only(
                'point_catchment_id', 'code_dga', 'type_dga', 'send_dga', 'sma_device_id'
            ),
        )
    )


def _scoped_queryset(user):
    qs = _base_queryset()
    if user.is_staff or user.is_superuser:
        return qs
    return qs.filter(Q(owner_user=user) | Q(users_viewers=user)).distinct()


def _collect_points(queryset, *, kinds):
    # list() (no iterator): preserva prefetch_related y evita N+1
    points = []
    for point in queryset:
        cfg = point.dga_data_config_profiles.first()
        payload = _serialize_point(point, cfg)
        if not payload:
            continue
        if payload['code_kind'] not in kinds:
            continue
        points.append(payload)
    return points


class ObservatoryPublicPointsView(APIView):
    """
    Capa pública del observatorio: solo códigos DGA (prefijo OB) con coordenadas.
    """
    permission_classes = [AllowAny]
    throttle_classes = [PublicReadRateThrottle]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name='type_dga',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description='SUBTERRANEO | SUPERFICIAL',
                required=False,
            ),
        ],
        responses={200: PublicMapPointSerializer(many=True)},
    )
    def get(self, request):
        qs = _base_queryset()
        type_dga = (request.query_params.get('type_dga') or '').strip().upper()
        if type_dga in ('SUBTERRANEO', 'SUPERFICIAL'):
            qs = qs.filter(dga_data_config_profiles__type_dga=type_dga)

        points = _collect_points(qs, kinds={'DGA'})
        data = PublicMapPointSerializer(points, many=True).data
        return Response({
            'mode': 'public',
            'count': len(data),
            'dga_count': len(data),
            'other_count': 0,
            'points': data,
        })


class ObservatoryAuthPointsView(APIView):
    """
    Capa autenticada: DGA públicos + códigos no-DGA del alcance del usuario.
    Staff/superuser ve todos los puntos con código y coordenadas.
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [SummaryRateThrottle]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name='kind',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description='all | DGA | OTHER',
                required=False,
            ),
            OpenApiParameter(
                name='type_dga',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description='SUBTERRANEO | SUPERFICIAL',
                required=False,
            ),
        ],
        responses={200: PublicMapPointSerializer(many=True)},
    )
    def get(self, request):
        user = request.user
        kind = (request.query_params.get('kind') or 'all').strip().upper()
        if kind in ('DGA', 'OTHER'):
            kinds = {kind}
        else:
            kinds = {'DGA', 'OTHER'}

        # DGA: capa pública completa (códigos regulatorios)
        public_qs = _base_queryset()
        # OTHER: solo alcance del usuario
        private_qs = _scoped_queryset(user)

        type_dga = (request.query_params.get('type_dga') or '').strip().upper()
        if type_dga in ('SUBTERRANEO', 'SUPERFICIAL'):
            public_qs = public_qs.filter(dga_data_config_profiles__type_dga=type_dga)
            private_qs = private_qs.filter(dga_data_config_profiles__type_dga=type_dga)

        by_id = {}
        if 'DGA' in kinds:
            for item in _collect_points(public_qs, kinds={'DGA'}):
                by_id[item['id']] = item
        if 'OTHER' in kinds:
            for item in _collect_points(private_qs, kinds={'OTHER'}):
                by_id[item['id']] = item

        points = sorted(by_id.values(), key=lambda p: p['code'])
        data = PublicMapPointSerializer(points, many=True).data
        dga_count = sum(1 for p in data if p['code_kind'] == 'DGA')
        other_count = len(data) - dga_count

        return Response({
            'mode': 'authenticated',
            'count': len(data),
            'dga_count': dga_count,
            'other_count': other_count,
            'points': data,
        })
