"""
ViewSet unificado para CatchmentPoint.

Consolida endpoints de V1, V2, V3 y Unified en un solo ViewSet coherente.
"""

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from api.telemetry.models.catchment_points import CatchmentPoint
from api.telemetry.models import TelemetryRecord
from api.unified.views.base import BaseViewSet
from api.unified.serializers.catchment_points import (
    CatchmentPointListSerializer,
    CatchmentPointDetailSerializer,
    CatchmentPointCreateSerializer,
    CatchmentPointConfigSerializer,
)
from api.unified.serializers.base import TelemetryRecordSerializer, VariableSerializer
from api.unified.services.status_service import StatusService


class CatchmentPointViewSet(BaseViewSet):
    """
    ViewSet unificado para puntos de captación.

    Endpoints:
        GET    /points/                 - Lista de puntos
        POST   /points/                 - Crear punto
        GET    /points/{id}/            - Detalle de punto
        PUT    /points/{id}/            - Actualizar punto
        DELETE /points/{id}/            - Eliminar punto

    Actions:
        GET    /points/{id}/records/    - Registros de telemetría
        GET    /points/{id}/latest/     - Última lectura
        GET    /points/{id}/status/     - Estado online/offline
        GET    /points/{id}/config/     - Configuración dinámica
        PUT    /points/{id}/config/     - Actualizar configuración
        GET    /points/{id}/variables/  - Variables del punto
    """

    queryset = CatchmentPoint.objects.filter(
        is_active=True
    ).select_related(
        'project',
        'project__client',
        'device',
        'configuration_scheme',
        'frequency',
    ).prefetch_related(
        'variables',
    )

    serializer_class = CatchmentPointDetailSerializer
    serializer_class_list = CatchmentPointListSerializer
    serializer_class_detail = CatchmentPointDetailSerializer
    serializer_class_create = CatchmentPointCreateSerializer

    @action(detail=True, methods=['get'])
    def records(self, request, pk=None):
        """
        Obtiene registros de telemetría del punto.

        Query params:
            - limit: Número máximo de registros (default: 100, max: 1000)
            - hours: Horas hacia atrás (default: 24)
            - offset: Offset para paginación
        """
        point = self.get_object()

        limit = min(int(request.query_params.get('limit', 100)), 1000)
        hours = request.query_params.get('hours')
        offset = int(request.query_params.get('offset', 0))

        queryset = TelemetryRecord.objects.filter(point=point)

        if hours:
            from datetime import timedelta
            from django.utils import timezone
            since = timezone.now() - timedelta(hours=int(hours))
            queryset = queryset.filter(timestamp__gte=since)

        records = queryset.order_by('-timestamp')[offset:offset + limit]
        serializer = TelemetryRecordSerializer(records, many=True)

        return Response({
            "point_id": point.id,
            "point_title": point.title,
            "count": len(serializer.data),
            "records": serializer.data,
        })

    @action(detail=True, methods=['get'])
    def latest(self, request, pk=None):
        """
        Obtiene la última lectura del punto.
        """
        point = self.get_object()

        record = TelemetryRecord.objects.filter(
            point=point
        ).order_by('-timestamp').first()

        if not record:
            return Response({
                "point_id": point.id,
                "point_title": point.title,
                "latest": None,
                "message": "No hay registros disponibles",
            })

        serializer = TelemetryRecordSerializer(record)

        return Response({
            "point_id": point.id,
            "point_title": point.title,
            "latest": serializer.data,
        })

    @action(detail=True, methods=['get'])
    def status(self, request, pk=None):
        """
        Obtiene el estado online/offline del punto.
        """
        point = self.get_object()

        threshold = request.query_params.get('threshold_minutes')
        if threshold:
            threshold = int(threshold)

        point_status = StatusService.get_point_status(point.id, threshold)

        return Response({
            "point_id": point.id,
            "point_title": point.title,
            **point_status,
        })

    @action(detail=True, methods=['get', 'put'])
    def config(self, request, pk=None):
        """
        Obtiene o actualiza la configuración dinámica del punto.
        """
        point = self.get_object()

        if request.method == 'GET':
            return Response({
                "point_id": point.id,
                "point_title": point.title,
                "config": point.get_config_dict(),
                "scheme": {
                    "id": point.configuration_scheme.id,
                    "name": point.configuration_scheme.name,
                    "code": point.configuration_scheme.code,
                } if point.configuration_scheme else None,
            })

        # PUT - Actualizar configuración
        serializer = CatchmentPointConfigSerializer(data=request.data)
        if serializer.is_valid():
            new_config = serializer.update_config(point, serializer.validated_data)
            return Response({
                "point_id": point.id,
                "point_title": point.title,
                "config": new_config,
                "message": "Configuración actualizada correctamente",
            })

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['get'])
    def variables(self, request, pk=None):
        """
        Obtiene las variables del punto.
        """
        point = self.get_object()

        variables = point.variables.filter(is_active=True)
        serializer = VariableSerializer(variables, many=True)

        return Response({
            "point_id": point.id,
            "point_title": point.title,
            "count": len(serializer.data),
            "variables": serializer.data,
        })

    @action(detail=False, methods=['get'])
    def batch_status(self, request):
        """
        Obtiene el estado de múltiples puntos en una sola llamada.

        Query params:
            - ids: Lista de IDs separados por coma
        """
        ids_param = request.query_params.get('ids', '')

        if not ids_param:
            return Response({
                "error": "Debe proporcionar parámetro 'ids'",
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            point_ids = [int(id.strip()) for id in ids_param.split(',')]
        except ValueError:
            return Response({
                "error": "IDs inválidos",
            }, status=status.HTTP_400_BAD_REQUEST)

        batch_status = StatusService.get_batch_status(point_ids)

        return Response({
            "count": len(batch_status),
            "statuses": batch_status,
        })
