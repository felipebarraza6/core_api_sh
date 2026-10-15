"""
Observatorio georreferenciado público
=====================================

GET /api/ik/observatory/public/   — AllowAny: solo códigos DGA (OB*) con coordenadas
GET /api/ik/observatory/points/   — IsAuthenticated: DGA + no-DGA del usuario (o todos si staff)

Respuesta: `stats` (indicadores agregados) + `mode`, `count`, `dga_count`,
`other_count`, `legend` y `points` (id, lat, lon, code, code_kind, type_dga,
measurements, dga).
Las coordenadas UTM (lat= northing, lon= easting, zona 19S) se convierten a
lat/lon decimal en la lectura; no se modifica la base de datos. Los puntos sin
coordenada válida no se muestran.
`measurements` es un diccionario {categoría: valor} de la última medición
enviada; la categoría (nivel freático / caudal / totalizado) se normaliza desde
las variables del punto (`Variable.type_variable`) o se infiere por `type_dga`.
`dga` (solo puntos DGA) trae `standard`, `shac`, último envío (`last_send`), el
`voucher` (comprobante) y el próximo envío programado (`next_send`).
Sin cliente, título, telemetría ni credenciales.
"""

import math
from datetime import datetime, timedelta

import pytz

from django.db.models import Q, Prefetch
from django.utils import timezone
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes

from api.core.models import CatchmentPoint, DgaDataConfigCatchment, InteractionDetail
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


def _utm_to_latlon(easting, northing, zone=19, southern=True):
    """Convierte UTM (WGS84) a lat/lon decimal. Por defecto zona 19S (Chile central).

    Fórmula de la serie estándar (USGS); sin dependencias externas.
    """
    a = 6378137.0
    f = 1 / 298.257223563
    e2 = f * (2 - f)
    k0 = 0.9996
    e1 = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))
    x = easting - 500000.0
    y = northing - (10000000.0 if southern else 0.0)
    lon0 = math.radians(zone * 6 - 183)
    m = y / k0
    mu = m / (a * (1 - e2 / 4 - 3 * e2 ** 2 / 64 - 5 * e2 ** 3 / 256))
    phi1 = (
        mu
        + (3 * e1 / 2 - 27 * e1 ** 3 / 32) * math.sin(2 * mu)
        + (21 * e1 ** 2 / 16 - 55 * e1 ** 4 / 32) * math.sin(4 * mu)
        + (151 * e1 ** 3 / 96) * math.sin(6 * mu)
    )
    n1 = a / math.sqrt(1 - e2 * math.sin(phi1) ** 2)
    t1 = math.tan(phi1) ** 2
    c1 = e2 / (1 - e2) * math.cos(phi1) ** 2
    r1 = a * (1 - e2) / (1 - e2 * math.sin(phi1) ** 2) ** 1.5
    d = x / (n1 * k0)
    lat = phi1 - (n1 * math.tan(phi1) / r1) * (
        d ** 2 / 2
        - (5 + 3 * t1 + 10 * c1 - 4 * c1 ** 2 - 9 * (e2 / (1 - e2))) * d ** 4 / 24
        + (61 + 90 * t1 + 298 * c1 + 45 * t1 ** 2 - 252 * (e2 / (1 - e2)) - 3 * c1 ** 2) * d ** 6 / 720
    )
    lon = lon0 + (
        d
        - (1 + 2 * t1 + c1) * d ** 3 / 6
        + (5 - 2 * c1 + 28 * t1 - 3 * c1 ** 2 + 8 * (e2 / (1 - e2)) + 24 * t1 ** 2) * d ** 5 / 120
    ) / math.cos(phi1)
    return math.degrees(lat), math.degrees(lon)


def _resolve_coords(lat_raw, lon_raw):
    """Devuelve (lat, lon) decimales o (None, None).

    Acepta lat/lon geográficas directas; si no lo son pero el par parece UTM
    (`lat`=northing, `lon`=easting) se convierte desde zona 19S. Solo lectura.
    """
    lat = _parse_coord(lat_raw)
    lon = _parse_coord(lon_raw)
    if lat is None or lon is None:
        return None, None
    if -90 <= lat <= 90 and -180 <= lon <= 180:
        return lat, lon
    northing, easting = lat, lon
    if 0 <= northing <= 10000000 and 100000 <= easting <= 900000:
        clat, clon = _utm_to_latlon(easting, northing, zone=19, southern=True)
        if -90 <= clat <= 90 and -180 <= clon <= 180:
            return clat, clon
    return None, None


def _code_kind(code):
    code = (code or '').strip()
    if not code:
        return None
    if code.upper().startswith('OB'):
        return 'DGA'
    return 'OTHER'


_MEASUREMENT_ORDER = ('nivel_freatico', 'caudal', 'totalizado')

MEASUREMENT_LEGEND = {
    'nivel_freatico': 'Nivel freático',
    'caudal': 'Caudal',
    'totalizado': 'Totalizado',
}


def _norm_measurement(type_variable):
    """Normaliza `Variable.type_variable` a una categoría del observatorio."""
    text = (type_variable or '').strip().upper()
    if text.startswith('NIVEL'):
        return 'nivel_freatico'
    if text.startswith('CAUDAL'):
        return 'caudal'
    if text.startswith('TOTALIZADO'):
        return 'totalizado'
    return None


def _measurements(point, cfg):
    """Categorías que mide el punto; si no tiene variables, se infiere del tipo DGA."""
    found = set()
    for scheme in point.schemes.all():
        for variable in scheme.variables.all():
            category = _norm_measurement(variable.type_variable)
            if category:
                found.add(category)
    if not found:
        type_dga = (getattr(cfg, 'type_dga', '') or '').strip().upper() if cfg else ''
        if type_dga == 'SUBTERRANEO':
            found.add('nivel_freatico')
        elif type_dga == 'SUPERFICIAL':
            found.add('caudal')
    return [category for category in _MEASUREMENT_ORDER if category in found]


CHILE_TZ = pytz.timezone('America/Santiago')


def _next_dga_send(standard):
    """Próximo envío DGA programado según `standard` (America/Santiago)."""
    std = (standard or 'SIN_ESTANDAR').strip().upper()
    local = timezone.localtime(timezone.now(), CHILE_TZ).replace(tzinfo=None)
    if std in ('MAYOR', 'SIN_ESTANDAR'):
        nxt = local.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    elif std == 'MEDIO':
        nxt = (local + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    elif std == 'MENOR':
        nxt = (local.replace(day=1) + timedelta(days=32)).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
    elif std == 'CAUDALES_MUY_PEQUENOS':
        candidates = [
            local.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0),
            local.replace(month=7, day=1, hour=0, minute=0, second=0, microsecond=0),
        ]
        nxt = next((c for c in candidates if c > local), None)
        if nxt is None:
            nxt = local.replace(
                year=local.year + 1, month=1, day=1,
                hour=0, minute=0, second=0, microsecond=0,
            )
    else:
        return None
    return CHILE_TZ.localize(nxt).isoformat()


def _dga_info(cfg, kind):
    """Info de envíos DGA del punto (None para puntos no-DGA)."""
    if kind != 'DGA' or cfg is None:
        return None
    standard = (getattr(cfg, 'standard', '') or 'SIN_ESTANDAR')
    return {
        'standard': standard,
        'shac': (getattr(cfg, 'shac', '') or None),
        'last_send': None,
        'voucher': None,
        'next_send': _next_dga_send(standard),
    }


def _metric(value):
    """Convierte un valor de medición a float (o None si vacío / no numérico)."""
    if value is None:
        return None
    text = str(value).strip().replace(',', '.')
    if not text:
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _record_measurements(record):
    """{categoría: valor} a partir de un registro de telemetría."""
    if record is None:
        return {'nivel_freatico': None, 'caudal': None, 'totalizado': None}
    return {
        'nivel_freatico': _metric(record.water_table),
        'caudal': _metric(record.flow),
        'totalizado': _metric(record.total),
    }


def _fill_last_dga(points):
    """Rellena valores de medición y, para DGA, el último envío (voucher).

    Los DGA toman el valor del último envío (comprobante); los no-DGA, de su
    última medición disponible.
    """
    dga_ids = [p['id'] for p in points if p.get('dga')]
    other_ids = [p['id'] for p in points if not p.get('dga')]

    fields = ('catchment_point_id', 'date_time_medition', 'flow', 'water_table', 'total')
    last = {}
    if dga_ids:
        qs = (
            InteractionDetail.objects
            .filter(catchment_point_id__in=dga_ids, n_voucher__isnull=False)
            .exclude(n_voucher='')
            .only(*(fields + ('n_voucher',)))
            .order_by('catchment_point_id', '-date_time_medition')
            .distinct('catchment_point_id')
        )
        for obj in qs:
            last[obj.catchment_point_id] = obj
    if other_ids:
        qs = (
            InteractionDetail.objects
            .filter(catchment_point_id__in=other_ids)
            .only(*fields)
            .order_by('catchment_point_id', '-date_time_medition')
            .distinct('catchment_point_id')
        )
        for obj in qs:
            last[obj.catchment_point_id] = obj

    for point in points:
        record = last.get(point['id'])
        values = _record_measurements(record)
        measurements = point.get('measurements') or {}
        for category in measurements:
            measurements[category] = values.get(category)
        dga = point.get('dga')
        if dga and record and record.date_time_medition:
            dga['last_send'] = timezone.localtime(
                record.date_time_medition, CHILE_TZ
            ).isoformat()
            dga['voucher'] = record.n_voucher


def _serialize_point(point, cfg):
    code = (cfg.code_dga or '').strip() if cfg else ''
    kind = _code_kind(code)
    if not kind:
        return None

    lat, lon = _resolve_coords(point.lat, point.lon)
    if lat is None or lon is None:
        # Sin coordenadas válidas el punto no se muestra en el mapa.
        return None

    return {
        'id': point.id,
        'lat': lat,
        'lon': lon,
        'code': code,
        'code_kind': kind,
        'type_dga': (cfg.type_dga or None) if cfg else None,
        'measurements': {category: None for category in _measurements(point, cfg)},
        'dga': _dga_info(cfg, kind),
    }


def _base_queryset():
    return CatchmentPoint.objects.exclude(
        Q(lat__isnull=True) | Q(lat='') | Q(lon__isnull=True) | Q(lon='')
    ).prefetch_related(
        'schemes__variables',
        Prefetch(
            'dga_data_config_profiles',
            queryset=DgaDataConfigCatchment.objects.only(
                'point_catchment_id', 'code_dga', 'type_dga', 'standard',
                'send_dga', 'sma_device_id', 'shac'
            ),
        )
    )


def _scoped_queryset(user):
    qs = _base_queryset()
    if user.is_staff or user.is_superuser:
        return qs
    return qs.filter(Q(owner_user=user) | Q(users_viewers=user)).distinct()


def _build_stats(points):
    """Indicadores agregados de los puntos devueltos (para el observatorio)."""
    by_type = {}
    by_standard = {}
    by_measurement = {}
    by_shac = {}
    sent = 0
    last_sends = []
    next_sends = []
    metrics = {'nivel_freatico': [], 'caudal': [], 'totalizado': []}

    def _parse(iso):
        try:
            return datetime.fromisoformat(iso)
        except (TypeError, ValueError):
            return None

    for point in points:
        type_dga = point.get('type_dga') or 'SIN_TIPO'
        by_type[type_dga] = by_type.get(type_dga, 0) + 1

        dga = point.get('dga') or {}
        standard = dga.get('standard') or 'SIN_ESTANDAR'
        by_standard[standard] = by_standard.get(standard, 0) + 1
        shac = dga.get('shac') or 'Sin SHAC'
        by_shac[shac] = by_shac.get(shac, 0) + 1

        for category, value in (point.get('measurements') or {}).items():
            by_measurement[category] = by_measurement.get(category, 0) + 1
            if value is not None:
                metrics.setdefault(category, []).append(value)

        if dga.get('last_send'):
            sent += 1
            last_sends.append(dga['last_send'])
        if dga.get('next_send'):
            next_sends.append(dga['next_send'])

    def _agg(values):
        if not values:
            return {'count': 0, 'min': None, 'max': None, 'avg': None}
        return {
            'count': len(values),
            'min': round(min(values), 2),
            'max': round(max(values), 2),
            'avg': round(sum(values) / len(values), 2),
        }

    def _extreme(values, pick):
        parsed = [(raw, _parse(raw)) for raw in values]
        parsed = [(raw, dt) for raw, dt in parsed if dt is not None]
        if not parsed:
            return None
        return pick(parsed, key=lambda item: item[1])[0]

    total = len(points)
    return {
        'total': total,
        'by_type_dga': by_type,
        'by_standard': by_standard,
        'by_measurement': by_measurement,
        'by_shac': by_shac,
        'sending': {'sent': sent, 'pending': total - sent},
        'last_send': _extreme(last_sends, max),
        'next_send': _extreme(next_sends, min),
        'metrics': {cat: _agg(vals) for cat, vals in metrics.items()},
    }


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
        _fill_last_dga(points)
        data = PublicMapPointSerializer(points, many=True).data
        return Response({
            'stats': _build_stats(points),
            'mode': 'public',
            'count': len(data),
            'dga_count': len(data),
            'other_count': 0,
            'legend': MEASUREMENT_LEGEND,
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
        _fill_last_dga(points)
        data = PublicMapPointSerializer(points, many=True).data
        dga_count = sum(1 for p in data if p['code_kind'] == 'DGA')
        other_count = len(data) - dga_count

        return Response({
            'stats': _build_stats(points),
            'mode': 'authenticated',
            'count': len(data),
            'dga_count': dga_count,
            'other_count': other_count,
            'legend': MEASUREMENT_LEGEND,
            'points': data,
        })
