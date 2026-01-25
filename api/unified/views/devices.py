"""
ViewSet unificado para Device.

Incluye soporte para campos dinámicos (configuration_scheme).
"""

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from api.infrastructure.models import Device
from api.unified.views.base import BaseViewSet
from api.unified.serializers.devices import (
    DeviceListSerializer,
    DeviceDetailSerializer,
    DeviceCreateSerializer,
    DeviceConfigSerializer,
)
from api.unified.services.status_service import StatusService


class DeviceViewSet(BaseViewSet):
    """
    ViewSet unificado para dispositivos IoT.

    Endpoints:
        GET    /devices/                 - Lista de dispositivos
        POST   /devices/                 - Crear dispositivo
        GET    /devices/{id}/            - Detalle de dispositivo
        PUT    /devices/{id}/            - Actualizar dispositivo
        DELETE /devices/{id}/            - Eliminar dispositivo

    Actions:
        GET    /devices/{id}/status/     - Estado del dispositivo
        GET    /devices/{id}/config/     - Configuración dinámica
        PUT    /devices/{id}/config/     - Actualizar configuración
        GET    /devices/{id}/points/     - Puntos asociados
    """

    queryset = Device.objects.select_related(
        'device_model',
        'device_model__manufacturer',
    ).prefetch_related(
        'catchment_points',
    )

    serializer_class = DeviceDetailSerializer
    serializer_class_list = DeviceListSerializer
    serializer_class_detail = DeviceDetailSerializer
    serializer_class_create = DeviceCreateSerializer

    def get_queryset(self):
        """Dispositivos no tienen owner_user, todos los autenticados pueden ver."""
        return super(BaseViewSet, self).get_queryset()

    @action(detail=True, methods=['get'])
    def status(self, request, pk=None):
        """
        Obtiene el estado del dispositivo.
        """
        device = self.get_object()
        device_status = StatusService.get_device_status(device.id)

        return Response({
            "device_id": device.id,
            "device_name": device.name,
            **device_status,
        })

    @action(detail=True, methods=['get', 'put'])
    def config(self, request, pk=None):
        """
        Obtiene o actualiza la configuración dinámica del dispositivo.
        """
        device = self.get_object()

        if request.method == 'GET':
            config = device.get_config_dict() if hasattr(device, 'get_config_dict') else {}
            scheme_info = None

            if hasattr(device, 'configuration_scheme') and device.configuration_scheme:
                scheme_info = {
                    "id": device.configuration_scheme.id,
                    "name": device.configuration_scheme.name,
                    "code": device.configuration_scheme.code,
                }

            return Response({
                "device_id": device.id,
                "device_name": device.name,
                "config": config,
                "scheme": scheme_info,
            })

        # PUT - Actualizar configuración
        serializer = DeviceConfigSerializer(data=request.data)
        if serializer.is_valid():
            new_config = serializer.update_config(device, serializer.validated_data)
            return Response({
                "device_id": device.id,
                "device_name": device.name,
                "config": new_config,
                "message": "Configuración actualizada correctamente",
            })

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['get'])
    def points(self, request, pk=None):
        """
        Obtiene los puntos de captación asociados al dispositivo.
        """
        device = self.get_object()
        points = device.catchment_points.filter(is_active=True).select_related('project')

        points_data = [
            {
                "id": p.id,
                "title": p.title,
                "point_code": p.point_code,
                "project_name": p.project.name if p.project else None,
                "is_active": p.is_active,
            }
            for p in points
        ]

        return Response({
            "device_id": device.id,
            "device_name": device.name,
            "count": len(points_data),
            "points": points_data,
        })

    @action(detail=False, methods=['get'])
    def by_manufacturer(self, request):
        """
        Lista dispositivos agrupados por fabricante.
        """
        from django.db.models import Count

        manufacturers = (
            Device.objects
            .values('device_model__manufacturer__name', 'device_model__manufacturer__id')
            .annotate(device_count=Count('id'))
            .order_by('-device_count')
        )

        return Response({
            "manufacturers": [
                {
                    "id": m['device_model__manufacturer__id'],
                    "name": m['device_model__manufacturer__name'],
                    "device_count": m['device_count'],
                }
                for m in manufacturers
            ]
        })
