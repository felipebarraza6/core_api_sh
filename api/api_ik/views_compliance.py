"""
Endpoint de Compliance DGA/SMA
==============================

GET /api/ik/compliance/

Retorna el listado completo de cumplimiento DGA/SMA para los puntos del usuario,
incluyendo historial de caudales excedidos, warnings de consumo, y stats agregadas.

Auth: Token
Filtros por usuario (owner/viewer), staff ve todo.
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from django.db.models import Q, Sum
from api.core.models import CatchmentPoint, DgaDataConfigCatchment, InteractionDetail


class ComplianceListView(APIView):
    """
    GET /api/ik/compliance/

    Retorna:
    {
        "stats": {"total": N, "by_standard": {}, "by_type": {}},
        "points": [
            {
                "point_id": 1,
                "point_name": "S3",
                "code": "12345-DGA",
                "compliance_type": ["DGA"],
                "standard": "MAYOR",
                "type_dga": "SUPERFICIAL",
                "send_dga": true,
                "send_sma": false,
                "authorized_flow": 150.0,
                "authorized_total": 50000.0,
                "annual_consumption": 12500.5,
                "pct_consumed": 25.01,
                "flow_history": {"count": 5, "threshold": 2.0, "measurements": [...]},
                "compliance_warning": {
                    "level": "safe",
                    "status": "Dentro de límites",
                    "pct_consumed": 25.01,
                    "threshold_pct": 80.0,
                    "messages": ["Consumo dentro de límites (25.01% del total autorizado)."]
                },
                "last_sent_at": "2026-05-28T14:00:00",
                "voucher": "...",
                "flow": 223.0,
                "water_table": 0.25,
                "total": 45271.0,
            }
        ]
    }
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from django.utils import timezone
        from datetime import date
        from collections import Counter

        user = request.user
        today = date.today()
        current_year = today.year

        # Filtrar puntos según permisos
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

        if not point_ids:
            return Response({
                "stats": {"total": 0, "by_standard": {}, "by_type": {}},
                "points": [],
            })

        # Puntos con compliance configurado
        compliance_points = DgaDataConfigCatchment.objects.filter(
            Q(point_catchment_id__in=point_ids),
            Q(send_dga=True) | Q(send_sma=True)
        ).filter(
            Q(send_dga=True, code_dga__isnull=False, code_dga__gt='') |
            Q(send_sma=True, sma_device_id__isnull=False, sma_device_id__gt='')
        ).select_related('point_catchment')

        # Consumo anual por punto (una sola query)
        annual_consumptions = {
            item['catchment_point']: item['sum_diff'] or 0.0
            for item in InteractionDetail.objects.filter(
                catchment_point_id__in=point_ids,
                date_time_medition__year=current_year
            ).values('catchment_point').annotate(sum_diff=Sum('total_diff'))
        }

        # Precalcular caudales excedidos y cercanos al límite por punto (año actual, máx 20 por punto)
        flow_exceedances = {}
        near_limit_records = {}
        for cfg in compliance_points:
            cp = cfg.point_catchment
            auth_flow = cfg.flow_granted_dga
            if auth_flow is not None and float(auth_flow) > 0:
                auth_flow_f = float(auth_flow)
                exceeded = list(
                    InteractionDetail.objects.filter(
                        catchment_point_id=cp.id,
                        date_time_medition__year=current_year,
                        flow__gt=auth_flow_f,
                    ).order_by('-date_time_medition').values('date_time_medition', 'flow')[:20]
                )
                flow_exceedances[cp.id] = exceeded
                near = list(
                    InteractionDetail.objects.filter(
                        catchment_point_id=cp.id,
                        date_time_medition__year=current_year,
                        flow__gte=auth_flow_f * 0.9,
                        flow__lte=auth_flow_f,
                    ).order_by('-date_time_medition').values('date_time_medition', 'flow')[:20]
                )
                near_limit_records[cp.id] = near
            else:
                flow_exceedances[cp.id] = []
                near_limit_records[cp.id] = []

        by_standard = Counter()
        by_type = Counter()
        points = []

        for cfg in compliance_points:
            cp = cfg.point_catchment

            # Último registro con envío DGA exitoso
            if cfg.send_dga:
                last_sent = InteractionDetail.objects.filter(
                    catchment_point=cp,
                    n_voucher__isnull=False
                ).order_by('-date_time_medition').first()
            else:
                last_sent = None

            if not last_sent:
                last_sent = InteractionDetail.objects.filter(
                    catchment_point=cp
                ).order_by('-date_time_medition').first()

            standard = cfg.standard or 'SIN_ESTANDAR'
            type_dga = cfg.type_dga or 'NO_DEFINIDO'
            by_standard[standard] += 1
            by_type[type_dga] += 1

            annual_consumption = annual_consumptions.get(cp.id, 0.0)
            authorized_total = float(cfg.total_granted_dga) if cfg.total_granted_dga is not None else None
            pct_consumed = None
            if authorized_total and authorized_total > 0 and annual_consumption > 0:
                pct_consumed = round((annual_consumption / authorized_total) * 100, 2)

            compliance_type = []
            if cfg.send_dga and cfg.code_dga:
                compliance_type.append('DGA')
            if cfg.send_sma and cfg.sma_device_id:
                compliance_type.append('SMA')

            exceeded_list = flow_exceedances.get(cp.id, [])
            flow_history = {
                'count': len(exceeded_list),
                'has_more': len(exceeded_list) == 20,
                'threshold': float(cfg.flow_granted_dga) if cfg.flow_granted_dga is not None else None,
                'measurements': [
                    {
                        'date': e['date_time_medition'].isoformat() if e['date_time_medition'] else None,
                        'flow': round(float(e['flow']), 2),
                    }
                    for e in exceeded_list
                ],
            }

            near_list = near_limit_records.get(cp.id, [])
            near_limit_history = {
                'count': len(near_list),
                'has_more': len(near_list) == 20,
                'threshold': float(cfg.flow_granted_dga) if cfg.flow_granted_dga is not None else None,
                'measurements': [
                    {
                        'date': e['date_time_medition'].isoformat() if e['date_time_medition'] else None,
                        'flow': round(float(e['flow']), 2),
                    }
                    for e in near_list
                ],
            }

            current_flow = round(float(last_sent.flow or 0), 2) if last_sent else 0.0
            compliance_warning = self._build_warning(
                auth_flow=float(cfg.flow_granted_dga) if cfg.flow_granted_dga is not None else None,
                current_flow=current_flow,
            )

            item = {
                'point_id': cp.id,
                'point_name': cp.title,
                'code': cfg.code_dga or cfg.sma_device_id,
                'compliance_type': compliance_type,
                'standard': standard,
                'type_dga': type_dga,
                'send_dga': cfg.send_dga,
                'send_sma': cfg.send_sma,
                'authorized_flow': float(cfg.flow_granted_dga) if cfg.flow_granted_dga is not None else None,
                'authorized_total': cfg.total_granted_dga,
                'annual_consumption': round(annual_consumption, 2),
                'pct_consumed': pct_consumed,
                'flow_history': flow_history,
                'near_limit_history': near_limit_history,
                'compliance_warning': compliance_warning,
            }

            if last_sent:
                item.update({
                    'last_sent_at': last_sent.date_time_medition.isoformat() if last_sent.date_time_medition else None,
                    'voucher': last_sent.n_voucher,
                    'flow': round(float(last_sent.flow or 0), 2),
                    'water_table': round(float(last_sent.water_table or 0), 2),
                    'total': round(float(last_sent.total or 0), 2),
                })
            else:
                item.update({
                    'last_sent_at': None,
                    'voucher': None,
                    'flow': 0.0,
                    'water_table': 0.0,
                    'total': 0.0,
                })
            points.append(item)

        stats = {
            'total': len(points),
            'with_warnings': sum(1 for p in points if p['compliance_warning']['level'] == 'warning'),
            'with_critical': sum(1 for p in points if p['compliance_warning']['level'] == 'critical'),
            'by_standard': dict(by_standard),
            'by_type': dict(by_type),
        }

        return Response({
            'stats': stats,
            'points': points,
        })

    def _build_warning(self, auth_flow, current_flow):
        """
        Construye el objeto compliance_warning PREVENTIVO.
        Solo evalúa caudal instantáneo vs límite autorizado.
        No usa total acumulado (es histórico, se suma solo).
        """
        has_flow_data = auth_flow is not None and auth_flow > 0

        if not has_flow_data:
            return {
                'level': 'unknown',
                'status': 'Sin límite de caudal configurado',
                'flow_pct': None,
                'messages': ['No se ha configurado caudal autorizado para este punto.'],
            }

        flow_pct = round((current_flow / auth_flow) * 100, 2) if current_flow is not None and current_flow > 0 else 0.0

        if current_flow is not None and current_flow > 0:
            if current_flow > auth_flow:
                return {
                    'level': 'critical',
                    'status': 'Caudal excedido',
                    'flow_pct': flow_pct,
                    'messages': [
                        f'Caudal actual ({current_flow} L/s) supera el límite autorizado ({auth_flow} L/s).'
                    ],
                }
            elif flow_pct >= 90.0:
                return {
                    'level': 'warning',
                    'status': 'Cerca de superar límite',
                    'flow_pct': flow_pct,
                    'messages': [
                        f'Caudal actual ({current_flow} L/s) está al {flow_pct}% del límite autorizado ({auth_flow} L/s).'
                    ],
                }

        return {
            'level': 'safe',
            'status': 'Dentro de límites',
            'flow_pct': flow_pct,
            'messages': [
                f'Caudal dentro de límites ({flow_pct}% del autorizado).'
            ],
        }
