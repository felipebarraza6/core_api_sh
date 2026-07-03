"""Catchment Points views."""

from django_filters import rest_framework as filters
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, extend_schema_view

from api.core.models.catchment_points import (
    CatchmentPoint,
    Client,
    CounterResetLog,
    DgaDataConfigCatchment,
    FileCatchment,
    NotificationsCatchment,
    ProfileDataConfigCatchment,
    ProfileIkoluCatchment,
    ProjectCatchments,
    RegisterPersons,
    ResponseNotificationsCatchment,
    SchemesCatchment,
    TypeFileCatchment,
    Variable,
)
from api.core.models.telemetry_providers import TelemetryProvider
from api.core.models.compliance_providers import ComplianceProvider
from api.core.serializers import (
    CatchmentPointIkoluSerializer,
    CatchmentPointSerializer,
    ClientSerializer,
    ClientWithProjectsSerializer,
    ComplianceProviderSerializer,
    CounterResetLogSerializer,
    DgaDataConfigCatchmentSerializer,
    FileCatchmentSerializer,
    NotificationsCatchmentSerializer,
    NotificationsCatchmentDetailSerializer,
    ProfileDataConfigCatchmentSerializer,
    ProfileIkoluCatchmentSerializer,
    ProjectCatchmentsSerializer,
    RegisterPersonsSerializer,
    ResponseDepthNotificationsCatchmentSerializer,
    ResponseNotificationsCatchmentSerializer,
    SchemesCatchmentSerializer,
    TelemetryProviderSerializer,
    TypeFileCatchmentSerializer,
    VariableSerializer,
)


@extend_schema_view(
    list=extend_schema(summary="Listar clientes", description="Empresas/clientes propietarios de proyectos. Filtros: search, ordering."),
    retrieve=extend_schema(summary="Detalle de cliente"),
    create=extend_schema(summary="Crear cliente"),
    update=extend_schema(summary="Actualizar cliente"),
    partial_update=extend_schema(summary="Actualizar parcialmente cliente"),
    destroy=extend_schema(summary="Eliminar cliente"),
)
class ClientViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated]
    filter_backends = (filters.DjangoFilterBackend, SearchFilter, OrderingFilter)
    queryset = Client.objects.all()
    serializer_class = ClientSerializer
    lookup_field = "id"
    filterset_fields = ['name', 'rut', 'email', 'critical']
    search_fields = ['name', 'rut', 'email']
    ordering_fields = ['name', 'created', 'critical']

    @action(detail=False, methods=['get'], url_path='all')
    def all(self, request):
        """Devuelve todos los clientes sin paginación, con límite de seguridad."""
        from django.core.cache import cache
        cache_key = 'clients:all'
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached)
        queryset = self.get_queryset()
        try:
            limit = int(request.query_params.get('limit', 500))
        except (ValueError, TypeError):
            limit = 500
        limit = min(max(limit, 1), 1000)
        queryset = queryset[:limit]
        serializer = self.get_serializer(queryset, many=True)
        data = serializer.data
        cache.set(cache_key, data, timeout=300)
        return Response(data)

    @action(detail=False, methods=['get'], url_path='with-projects')
    def with_projects(self, request):
        """Devuelve todos los clientes con sus proyectos anidados, con límite de seguridad."""
        queryset = self.get_queryset().prefetch_related('projectcatchments_set')
        try:
            limit = int(request.query_params.get('limit', 500))
        except (ValueError, TypeError):
            limit = 500
        limit = min(max(limit, 1), 1000)
        queryset = queryset[:limit]
        serializer = ClientWithProjectsSerializer(queryset, many=True)
        return Response(serializer.data)


@extend_schema_view(
    list=extend_schema(summary="Listar proyectos", description="Proyectos de captación asociados a clientes. Filtro: client."),
    retrieve=extend_schema(summary="Detalle de proyecto"),
    create=extend_schema(summary="Crear proyecto"),
    update=extend_schema(summary="Actualizar proyecto"),
    partial_update=extend_schema(summary="Actualizar parcialmente proyecto"),
    destroy=extend_schema(summary="Eliminar proyecto"),
)
class ProjectCatchmentsViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated]
    filter_backends = (filters.DjangoFilterBackend,)
    queryset = ProjectCatchments.objects.all()
    serializer_class = ProjectCatchmentsSerializer
    lookup_field = "id"
    filterset_fields = ['client']

    @action(detail=False, methods=['get'], url_path='all')
    def all(self, request):
        """Devuelve todos los proyectos sin paginación, filtrable por cliente, con límite de seguridad."""
        from django.core.cache import cache
        cache_key = 'projects:all'
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached)
        queryset = self.filter_queryset(self.get_queryset())
        try:
            limit = int(request.query_params.get('limit', 500))
        except (ValueError, TypeError):
            limit = 500
        limit = min(max(limit, 1), 1000)
        queryset = queryset[:limit]
        serializer = self.get_serializer(queryset, many=True)
        data = serializer.data
        cache.set(cache_key, data, timeout=300)
        return Response(data)


@extend_schema_view(
    list=extend_schema(summary="Listar puntos de captación", description="Puntos de captación con telemetría. Filtros: project, search, ordering."),
    retrieve=extend_schema(summary="Detalle de punto de captación", description="Perfil completo del punto: config, esquemas, variables, última telemetría."),
    create=extend_schema(summary="Crear punto de captación"),
    update=extend_schema(summary="Actualizar punto de captación"),
    partial_update=extend_schema(summary="Actualizar parcialmente punto de captación"),
    destroy=extend_schema(summary="Eliminar punto de captación"),
)
class CatchmentPointViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated]
    filter_backends = (filters.DjangoFilterBackend, SearchFilter, OrderingFilter)
    # ✅ MEJORADO: Optimización con select_related y prefetch_related para mejorar rendimiento
    # NOTA: data_config_profiles y schemes se agregan en get_queryset() con prefetch optimizado
    queryset = CatchmentPoint.objects.select_related('project', 'owner_user').prefetch_related(
        'ikolu_profiles',
        'dga_data_config_profiles',
    )
    serializer_class = CatchmentPointSerializer
    lookup_field = "id"
    filterset_fields = ['project']
    search_fields = ['title', 'project__name', 'project__client__name', 'owner_user__username']
    ordering_fields = ['title', 'frecuency', 'project__name']

    @action(detail=False, methods=['get'], url_path='all')
    def all(self, request):
        """Devuelve todos los puntos de captación sin paginación, filtrable por proyecto."""
        queryset = self.filter_queryset(self.get_queryset())
        # ✅ Seguridad: límite de 500 puntos para prevenir payloads masivos
        try:
            limit = int(request.query_params.get('limit', 500))
        except (ValueError, TypeError):
            limit = 500
        limit = min(max(limit, 1), 1000)
        queryset = queryset[:limit]
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def get_serializer_class(self):
        if self.action in ["retrieve"]:
            return CatchmentPointIkoluSerializer
        elif self.action in ["list"]:
            return CatchmentPointSerializer
        return CatchmentPointSerializer
    
    def get_queryset(self):
        """
        ✅ MEJORADO: Optimización adicional con prefetch_related para evitar N+1 queries.
        """
        queryset = super().get_queryset()
        # ✅ Optimización: Prefetch más agresivo para mejorar rendimiento con grandes volúmenes
        from django.db.models import Prefetch
        from api.core.models import ProfileDataConfigCatchment, SchemesCatchment, Variable
        
        queryset = queryset.prefetch_related(
            Prefetch(
                'data_config_profiles',
                queryset=ProfileDataConfigCatchment.objects.only(
                    'point_catchment_id', 'd1', 'd2', 'd3', 'd4', 'd5', 'd6',
                    'date_start_telemetry', 'date_delivery_act', 'is_telemetry'
                )
            ),
            Prefetch(
                'schemes',
                queryset=SchemesCatchment.objects.prefetch_related(
                    Prefetch(
                        'variables',  # ✅ FIX: Cambiar variable_set por variables (related_name correcto)
                        queryset=Variable.objects.only(
                            'id', 'str_variable', 'label', 'type_variable', 'service',
                            'pulses_factor', 'convert_to_lt', 'calculate_nivel',
                            'token_service', 'scheme_catchment_id'
                        )
                    )
                )
            )
        )
        return queryset


class ProfileIkoluCatchmentViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated]
    filter_backends = (filters.DjangoFilterBackend,)
    queryset = ProfileIkoluCatchment.objects.select_related('point_catchment').all()
    serializer_class = ProfileIkoluCatchmentSerializer
    lookup_field = "id"
    filterset_fields = ['point_catchment']


class NotificationsCatchmentViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated]
    filter_backends = (filters.DjangoFilterBackend, SearchFilter, OrderingFilter)
    queryset = NotificationsCatchment.objects.select_related('point_catchment').all().order_by("-created")
    serializer_class = NotificationsCatchmentSerializer
    lookup_field = "id"
    search_fields = ['title', 'message']
    ordering_fields = ['created', 'title']

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return NotificationsCatchmentDetailSerializer
        return self.serializer_class

    class FilterNotificationsCatchment(filters.FilterSet):
        class Meta:
            model = NotificationsCatchment
            fields = {
                "point_catchment": ["exact"],
                "type_variable": ["exact"],
                "type_notification": ["exact"],
                "type_alert": ["exact"],
                "is_periodic": ["exact"],
                "is_active": ["exact"],
                "is_read": ["exact"],
                "is_response": ["exact"],
                "is_finish": ["exact"],
                "is_wait": ["exact"],
                "status_dga": ["exact"],
                "status_sma": ["exact"],
                "start_date": ["exact"],
                "end_date": ["exact"],
            }

    filterset_class = FilterNotificationsCatchment


class ResponseNotificationsCatchmentViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated]
    filter_backends = (filters.DjangoFilterBackend,)
    queryset = ResponseNotificationsCatchment.objects.select_related('notification', 'user').all().order_by("-created")
    serializer_class = ResponseNotificationsCatchmentSerializer
    lookup_field = "id"

    class FilterNotificationsCatchment(filters.FilterSet):
        class Meta:
            model = ResponseNotificationsCatchment
            fields = {"notification": ["exact"], "user": ["exact"]}

    def get_serializer_class(self):
        if self.action in ["list"]:
            return ResponseDepthNotificationsCatchmentSerializer
        return ResponseNotificationsCatchmentSerializer

    filterset_class = FilterNotificationsCatchment

    def list(self, request, *args, **kwargs):
        """
        Lista de disparos (ResponseNotificationsCatchment).
        Si el filtro 'notification' corresponde a una alerta umbral sincronizada
        con el nuevo subsistema, devuelve los AlertTrigger mapeados.
        """
        notification_id = request.query_params.get("notification")
        if notification_id:
            try:
                notif = NotificationsCatchment.objects.get(id=int(notification_id))
            except (ValueError, NotificationsCatchment.DoesNotExist):
                notif = None

            if notif and notif.type_notification == "ALERT" and notif.type_alert:
                from api.core.views.alert_adapter import get_triggers_as_legacy_responses
                data = get_triggers_as_legacy_responses(legacy_notification_id=int(notification_id))
                return Response(data)

        # Comportamiento legacy normal
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


class TypeFileCatchmentViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated]
    filter_backends = (filters.DjangoFilterBackend,)
    queryset = TypeFileCatchment.objects.all()
    serializer_class = TypeFileCatchmentSerializer
    lookup_field = "id"
    filterset_fields = ['internal']


class FileCatchmentViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated]
    filter_backends = (filters.DjangoFilterBackend, SearchFilter, OrderingFilter)
    queryset = FileCatchment.objects.select_related('point_catchment', 'type_file').all()
    serializer_class = FileCatchmentSerializer
    lookup_field = "id"
    filterset_fields = ['point_catchment', 'type_file']
    search_fields = ['name', 'point_catchment__title']
    ordering_fields = ['name', 'created']


class ProfileDataConfigCatchmentViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated]
    filter_backends = (filters.DjangoFilterBackend,)
    queryset = ProfileDataConfigCatchment.objects.select_related('point_catchment').all()
    serializer_class = ProfileDataConfigCatchmentSerializer
    lookup_field = "id"
    filterset_fields = ['point_catchment']


class DgaDataConfigCatchmentViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated]
    filter_backends = (filters.DjangoFilterBackend,)
    queryset = DgaDataConfigCatchment.objects.select_related('point_catchment').all()
    serializer_class = DgaDataConfigCatchmentSerializer
    lookup_field = "id"
    filterset_fields = ['point_catchment']


class SchemesCatchmentViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated]
    filter_backends = (filters.DjangoFilterBackend,)
    queryset = SchemesCatchment.objects.prefetch_related('points_catchment').all()
    serializer_class = SchemesCatchmentSerializer
    lookup_field = "id"
    filterset_fields = ['points_catchment']


class VariableViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated]
    filter_backends = (filters.DjangoFilterBackend, SearchFilter, OrderingFilter)
    queryset = Variable.objects.select_related('scheme_catchment', 'provider').all()
    serializer_class = VariableSerializer
    lookup_field = "id"
    filterset_fields = ['scheme_catchment', 'provider']
    search_fields = ['str_variable', 'label', 'token_service']
    ordering_fields = ['str_variable', 'type_variable']


class RegisterPersonsViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated]
    filter_backends = (filters.DjangoFilterBackend, SearchFilter, OrderingFilter)
    queryset = RegisterPersons.objects.select_related('profile', 'profile__point_catchment').all()
    serializer_class = RegisterPersonsSerializer
    lookup_field = "id"
    filterset_fields = ['profile', 'profile__point_catchment']
    search_fields = ['name', 'email', 'phone']
    ordering_fields = ['name', 'created']


class CounterResetLogViewSet(
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """Read-only endpoint para historial de resets de contadores."""
    permission_classes = [IsAuthenticated]
    filter_backends = (filters.DjangoFilterBackend, SearchFilter, OrderingFilter)
    queryset = CounterResetLog.objects.select_related('point_catchment').order_by('-date_time_medition')
    serializer_class = CounterResetLogSerializer
    lookup_field = "id"
    filterset_fields = ['point_catchment', 'reset_type', 'detected_by']
    search_fields = ['point_catchment__title', 'detected_by']
    ordering_fields = ['date_time_medition', 'reset_type']


class TelemetryProviderViewSet(
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """Read-only endpoint para proveedores de telemetría."""
    permission_classes = [IsAuthenticated]
    filter_backends = (filters.DjangoFilterBackend,)
    queryset = TelemetryProvider.objects.order_by('name')
    serializer_class = TelemetryProviderSerializer
    lookup_field = "id"
    filterset_fields = ['handler_name', 'protocol', 'auth_type', 'is_active']


class ComplianceProviderViewSet(
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """Read-only endpoint para proveedores de cumplimiento regulatorio."""
    permission_classes = [IsAuthenticated]
    filter_backends = (filters.DjangoFilterBackend,)
    queryset = ComplianceProvider.objects.order_by('name')
    serializer_class = ComplianceProviderSerializer
    lookup_field = "id"
    filterset_fields = ['code', 'protocol', 'auth_type', 'is_active']
