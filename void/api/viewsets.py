"""DRF viewsets for void API."""
from django.utils.dateparse import parse_datetime
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from void.models import (
    AlertRule,
    AlertTrigger,
    ComplianceAuthority,
    ComplianceStandard,
    Device,
    Point,
    PointComplianceProfile,
    ProcessedReading,
    Project,
    Provider,
    VoidUserProfile,
)
from void.services import PointService, ShadowService
from void.services.notifications import AlertDispatcher

from .permissions import PointObjectPermission, VoidRolePermission
from .serializers import (
    AlertRuleSerializer,
    AlertTriggerSerializer,
    ComplianceAuthoritySerializer,
    ComplianceStandardSerializer,
    DeviceSerializer,
    PointComplianceProfileSerializer,
    PointSerializer,
    PointSummarySerializer,
    ProcessedReadingSerializer,
    ProjectSerializer,
    ProviderSerializer,
    VoidUserProfileSerializer,
)


class VoidUserProfileViewSet(viewsets.ModelViewSet):
    """CRUD de perfiles de usuario void."""

    queryset = VoidUserProfile.objects.select_related("user").all()
    serializer_class = VoidUserProfileSerializer
    permission_classes = [IsAuthenticated, VoidRolePermission]
    filter_backends = [filters.SearchFilter]
    search_fields = ["user__email", "user__username", "phone"]

    def get_queryset(self):
        user = self.request.user
        profile = getattr(user, "void_profile", None)
        if profile is None:
            return VoidUserProfile.objects.none()
        if profile.role in {"admin", "operator"}:
            return self.queryset
        return self.queryset.filter(pk=profile.pk)


class ProjectViewSet(viewsets.ModelViewSet):
    """CRUD de proyectos."""

    queryset = Project.objects.select_related("client").all()
    serializer_class = ProjectSerializer
    permission_classes = [IsAuthenticated, VoidRolePermission]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "client__name", "code_internal"]
    ordering_fields = ["name", "created"]


class PointViewSet(viewsets.ModelViewSet):
    """CRUD de puntos de captación + acciones de resumen y lecturas."""

    serializer_class = PointSerializer
    permission_classes = [IsAuthenticated, PointObjectPermission]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "code_internal"]
    ordering_fields = ["name", "created", "frequency_minutes"]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.point_service = PointService()

    def get_queryset(self):
        return self.point_service.get_points_for_user(self.request.user)

    def perform_update(self, serializer):
        if not self.point_service.can_edit_point(self.request.user, self.get_object()):
            raise PermissionDenied("No tienes permiso para editar este punto.")
        serializer.save()

    @action(detail=True, methods=["get"])
    def summary(self, request, pk=None):
        data = self.point_service.get_point_summary(int(pk))
        if data is None:
            return Response({"error": "Punto no encontrado"}, status=status.HTTP_404_NOT_FOUND)
        return Response(data)

    @action(detail=True, methods=["get"])
    def config(self, request, pk=None):
        data = self.point_service.get_point_config(int(pk))
        if data is None:
            return Response({"error": "Punto no encontrado"}, status=status.HTTP_404_NOT_FOUND)
        return Response(data)

    @action(detail=True, methods=["get"])
    def records(self, request, pk=None):
        point = self.get_object()
        variable = request.query_params.get("variable")
        since_str = request.query_params.get("since")
        until_str = request.query_params.get("until")
        since = parse_datetime(since_str) if since_str else None
        until = parse_datetime(until_str) if until_str else None

        qs = ProcessedReading.objects.filter(device__point=point)
        if variable:
            qs = qs.filter(variable=variable)
        if since:
            qs = qs.filter(timestamp__gte=since)
        if until:
            qs = qs.filter(timestamp__lte=until)

        page = self.paginate_queryset(qs.order_by("-timestamp"))
        serializer = ProcessedReadingSerializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    @action(detail=True, methods=["post"])
    def shadow(self, request, pk=None):
        """Ejecuta shadow mode para el total del punto."""
        point = self.get_object()
        try:
            device = point.device
        except Device.DoesNotExist:
            return Response(
                {"error": "El punto no tiene dispositivo"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        output_field = request.data.get("output_field", "total")
        window_minutes = int(request.data.get("window_minutes", 70))
        ingest = bool(request.data.get("ingest", True))
        process = bool(request.data.get("process", True))

        service = ShadowService()
        run = service.run_for_output_field(
            device=device,
            output_field=output_field,
            window_minutes=window_minutes,
            ingest=ingest,
            process=process,
        )

        return Response({
            "run_id": run.id,
            "status": run.status,
            "variable": run.variable,
            "output_field": run.output_field,
            "window_start": run.window_start,
            "window_end": run.window_end,
            "legacy_count": run.legacy_count,
            "void_count": run.void_count,
            "matched_count": run.matched_count,
            "mismatched_count": run.mismatched_count,
            "legacy_only_count": run.legacy_only_count,
            "void_only_count": run.void_only_count,
            "error_message": run.error_message,
        })


class DeviceViewSet(viewsets.ModelViewSet):
    """CRUD de dispositivos."""

    queryset = Device.objects.select_related("point", "provider").prefetch_related(
        "variable_configs", "hardware"
    )
    serializer_class = DeviceSerializer
    permission_classes = [IsAuthenticated, PointObjectPermission]
    filter_backends = [filters.SearchFilter]
    search_fields = ["serial_number", "external_id", "model"]

    def get_queryset(self):
        profile = getattr(self.request.user, "void_profile", None)
        if profile is None:
            return Device.objects.none()
        if profile.role in {"admin", "operator"}:
            return self.queryset
        allowed_points = PointService().get_points_for_user(self.request.user)
        return self.queryset.filter(point__in=allowed_points)


class ProviderViewSet(viewsets.ModelViewSet):
    """CRUD de proveedores de telemetría."""

    queryset = Provider.objects.prefetch_related("endpoints", "mqtt_topics").all()
    serializer_class = ProviderSerializer
    permission_classes = [IsAuthenticated, VoidRolePermission]
    filter_backends = [filters.SearchFilter]
    search_fields = ["name", "base_url"]


class AlertRuleViewSet(viewsets.ModelViewSet):
    """CRUD de reglas de alerta."""

    queryset = AlertRule.objects.all()
    serializer_class = AlertRuleSerializer
    permission_classes = [IsAuthenticated, VoidRolePermission]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name"]
    ordering_fields = ["name", "created", "is_active"]
    ordering = ["name"]


class AlertTriggerViewSet(viewsets.ReadOnlyModelViewSet):
    """Listado y detalle de disparos de alerta. Solo lectura."""

    queryset = AlertTrigger.objects.select_related("rule", "event").all()
    serializer_class = AlertTriggerSerializer
    permission_classes = [IsAuthenticated, VoidRolePermission]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["rule__name", "message"]
    ordering_fields = ["created", "status"]
    ordering = ["-created"]

    @action(detail=True, methods=["post"])
    def dispatch_now(self, request, pk=None):
        """Fuerza el envío de un trigger pendiente."""
        trigger = self.get_object()
        if trigger.status != "pending":
            return Response(
                {"error": "Solo se pueden reenviar triggers pendientes."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        result = AlertDispatcher().dispatch(trigger)
        return Response({"status": trigger.status, "result": result})


class ComplianceAuthorityViewSet(viewsets.ModelViewSet):
    """CRUD de entidades regulatorias (DGA, SMA, etc.)."""

    queryset = ComplianceAuthority.objects.all()
    serializer_class = ComplianceAuthoritySerializer
    permission_classes = [IsAuthenticated, VoidRolePermission]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["code", "name", "base_url"]
    ordering_fields = ["name", "code", "created"]


class ComplianceStandardViewSet(viewsets.ModelViewSet):
    """CRUD de estándares de envío de cumplimiento."""

    queryset = ComplianceStandard.objects.all()
    serializer_class = ComplianceStandardSerializer
    permission_classes = [IsAuthenticated, VoidRolePermission]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["code", "name"]
    ordering_fields = ["code", "created"]


class PointComplianceProfileViewSet(viewsets.ModelViewSet):
    """CRUD de perfiles de cumplimiento por punto."""

    serializer_class = PointComplianceProfileSerializer
    permission_classes = [IsAuthenticated, PointObjectPermission]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["point__name", "authority__name", "external_code"]
    ordering_fields = ["created", "point__name"]
    ordering = ["-created"]

    def get_queryset(self):
        profile = getattr(self.request.user, "void_profile", None)
        qs = PointComplianceProfile.objects.select_related(
            "point", "authority", "standard"
        )
        if profile is None:
            return qs.none()
        if profile.role in {"admin", "operator"}:
            return qs
        allowed_points = PointService().get_points_for_user(self.request.user)
        return qs.filter(point__in=allowed_points)

    def perform_update(self, serializer):
        if not self.point_service.can_edit_point(
            self.request.user, self.get_object().point
        ):
            raise PermissionDenied("No tienes permiso para editar este punto.")
        serializer.save()

    def perform_create(self, serializer):
        profile = getattr(self.request.user, "void_profile", None)
        if profile is None or profile.role not in {"admin", "operator", "client_admin"}:
            raise PermissionDenied("No tienes permiso para crear perfiles de cumplimiento.")
        serializer.save()
