"""Catchment Points views."""

from django_filters import rest_framework as filters
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from api.core.models.catchment_points import (
    CatchmentPoint,
    Client,
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
from api.core.serializers import (
    CatchmentPointIkoluSerializer,
    CatchmentPointSerializer,
    ClientSerializer,
    ClientWithProjectsSerializer,
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
    TypeFileCatchmentSerializer,
    VariableSerializer,
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
    filter_backends = (filters.DjangoFilterBackend,)
    queryset = Client.objects.all()
    serializer_class = ClientSerializer
    lookup_field = "id"

    @action(detail=False, methods=['get'], url_path='all')
    def all(self, request):
        """Devuelve todos los clientes sin paginación."""
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='with-projects')
    def with_projects(self, request):
        """Devuelve todos los clientes con sus proyectos anidados."""
        queryset = self.get_queryset().prefetch_related('projectcatchments_set')
        serializer = ClientWithProjectsSerializer(queryset, many=True)
        return Response(serializer.data)


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
        """Devuelve todos los proyectos sin paginación, filtrable por cliente."""
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


class CatchmentPointViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated]
    filter_backends = (filters.DjangoFilterBackend,)
    # ✅ MEJORADO: Optimización con select_related y prefetch_related para mejorar rendimiento
    # NOTA: data_config_profiles y schemes se agregan en get_queryset() con prefetch optimizado
    queryset = CatchmentPoint.objects.select_related('project', 'owner_user').prefetch_related(
        'ikolu_profiles',
        'dga_data_config_profiles',
    )
    serializer_class = CatchmentPointSerializer
    lookup_field = "id"
    filterset_fields = ['project']

    @action(detail=False, methods=['get'], url_path='all')
    def all(self, request):
        """Devuelve todos los puntos de captación sin paginación, filtrable por proyecto."""
        queryset = self.filter_queryset(self.get_queryset())
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
    queryset = ProfileIkoluCatchment.objects.all()
    serializer_class = ProfileIkoluCatchmentSerializer
    lookup_field = "id"


class NotificationsCatchmentViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated]
    filter_backends = (filters.DjangoFilterBackend,)
    queryset = NotificationsCatchment.objects.all().order_by("-created")
    serializer_class = NotificationsCatchmentSerializer
    lookup_field = "id"

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
    queryset = ResponseNotificationsCatchment.objects.all().order_by("-created")
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


class FileCatchmentViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated]
    filter_backends = (filters.DjangoFilterBackend,)
    queryset = FileCatchment.objects.all()
    serializer_class = FileCatchmentSerializer
    lookup_field = "id"


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
    queryset = ProfileDataConfigCatchment.objects.all()
    serializer_class = ProfileDataConfigCatchmentSerializer
    lookup_field = "id"


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
    queryset = DgaDataConfigCatchment.objects.all()
    serializer_class = DgaDataConfigCatchmentSerializer
    lookup_field = "id"


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
    queryset = SchemesCatchment.objects.all()
    serializer_class = SchemesCatchmentSerializer
    lookup_field = "id"


class VariableViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated]
    filter_backends = (filters.DjangoFilterBackend,)
    queryset = Variable.objects.all()
    serializer_class = VariableSerializer
    lookup_field = "id"


class RegisterPersonsViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated]
    filter_backends = (filters.DjangoFilterBackend,)
    queryset = RegisterPersons.objects.all()
    serializer_class = RegisterPersonsSerializer
    lookup_field = "id"
