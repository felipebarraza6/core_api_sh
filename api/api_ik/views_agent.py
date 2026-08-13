"""Vistas para agentes automatizados (IA) que necesitan credenciales de equipos.

Único propósito: entregar el token_service (token del equipo) de cada punto junto
con metadatos mínimos, para que un agente pueda usarlo al consultar al proveedor.

⚠️ SEGURIDAD: este endpoint expone credenciales de dispositivos.
Solo staff/superuser.
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from django.db.models import Prefetch
from django.utils import timezone

from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes

from api.core.models import (
    CatchmentPoint,
    DgaDataConfigCatchment,
    ProfileDataConfigCatchment,
)

from .throttles import SummaryRateThrottle
from .views import PointsSummaryView


class AgentPointsTokensView(APIView):
    """
    GET /api/ik/agent/points/

    Lista todos los puntos con su token de equipo (token_service), pensado
    exclusivamente para agentes automatizados. Requiere staff/superuser.

    Filtros opcionales:
    - provider: twin | nettra | novus | none (o tdata/thethings/tago como alias)
    - project_id: filtrar por proyecto

    Response:
    {
        "total": 200,
        "generated_at": "2026-08-04T...",
        "points": [
            {
                "id": 3,
                "nombre": "San Vicente de Tagua Tagua",
                "proyecto": "Oceano",
                "cliente": "Essbio",
                "es_dga": true,
                "codigo_obra": "123-45",
                "token": "4t0oCOg35GVh4wo3iKubYsQ5O6esThgYHjcTnTLVCGE"
            }
        ]
    }
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [SummaryRateThrottle]

    @extend_schema(
        summary="Puntos con token de equipo para agentes",
        description=(
            "Lista todos los puntos con su token_service (token del equipo), exclusivo para "
            "agentes automatizados. Solo staff/superuser. Retorna id, nombre, proyecto, "
            "cliente, es_dga, codigo_obra y token.\n\n"
            "Filtros opcionales:\n\n"
            "- `provider`: `twin`, `nettra`, `novus` o `none` (alias: `tdata`, `thethings`, `tago`)\n"
            "- `project_id`: filtrar por proyecto"
        ),
        parameters=[
            OpenApiParameter(
                name="provider",
                type=OpenApiTypes.STR,
                required=False,
                description=(
                    "Filtra por proveedor de telemetría. Valores: twin, nettra, novus, none "
                    "(o tdata/thethings/tago como alias)."
                ),
            ),
            OpenApiParameter(
                name="project_id",
                type=OpenApiTypes.INT,
                required=False,
                description="ID del proyecto para filtrar los puntos.",
            ),
        ],
    )
    def get(self, request):
        user = request.user
        if not (user.is_staff or user.is_superuser):
            return Response(
                {"error": "Requiere permisos de staff/superuser."},
                status=status.HTTP_403_FORBIDDEN,
            )

        points_qs = CatchmentPoint.objects.select_related(
            'project', 'project__client', 'telemetry_provider'
        ).order_by('title')

        # ── Filtro por proveedor (misma lógica que points_summary) ──
        provider_param = request.query_params.get('provider', '').strip().lower()
        if provider_param:
            provider_filter = PointsSummaryView.PROVIDER_FILTERS.get(provider_param)
            if provider_filter is None:
                return Response(
                    {
                        'error': (
                            f"provider inválido: '{provider_param}'. "
                            "Valores válidos: twin, nettra, novus, none "
                            "(o tdata/thethings/tago como alias)."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            points_qs = points_qs.filter(provider_filter)

        # ── Filtro por proyecto ──
        project_id_param = request.query_params.get('project_id', '').strip()
        if project_id_param:
            try:
                points_qs = points_qs.filter(project_id=int(project_id_param))
            except (ValueError, TypeError):
                return Response(
                    {'error': 'project_id debe ser un entero.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # ── Prefetch de token y DGA (2 queries, sin N+1) ──
        points_qs = points_qs.prefetch_related(
            Prefetch(
                'data_config_profiles',
                queryset=ProfileDataConfigCatchment.objects.only(
                    'point_catchment_id', 'token_service'
                ).order_by('id'),
                to_attr='_agent_configs',
            ),
            Prefetch(
                'dga_data_config_profiles',
                queryset=DgaDataConfigCatchment.objects.only(
                    'point_catchment_id', 'send_dga', 'code_dga'
                ).order_by('id'),
                to_attr='_agent_dgas',
            ),
        )

        data = []
        for p in points_qs:
            config = p._agent_configs[0] if p._agent_configs else None
            dga = p._agent_dgas[0] if p._agent_dgas else None
            data.append({
                'id': p.id,
                'nombre': p.title,
                'proyecto': p.project.name if p.project else None,
                'cliente': p.project.client.name if p.project and p.project.client else None,
                'es_dga': bool(dga.send_dga) if dga else False,
                'codigo_obra': dga.code_dga if dga else None,
                'token': config.token_service if config else None,
            })

        return Response({
            'total': len(data),
            'generated_at': timezone.now().isoformat(),
            'points': data,
        })
