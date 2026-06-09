"""
ViewSets para el subsistema de alertas.
"""

from django_filters import rest_framework as filters
from rest_framework import mixins, viewsets
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema, extend_schema_view

from api.core.models.alerts import AlertRule, AlertChannel, AlertTrigger, SystemEvent
from api.core.serializers.alerts import (
    AlertRuleListSerializer,
    AlertRuleDetailSerializer,
    AlertRuleWriteSerializer,
    AlertChannelSerializer,
    AlertTriggerSerializer,
    SystemEventSerializer,
)


class AlertRuleFilter(filters.FilterSet):
    class Meta:
        model = AlertRule
        fields = {
            "point_catchment": ["exact"],
            "target_type": ["exact"],
            "variable_type": ["exact"],
            "is_active": ["exact"],
            "check_frequency_minutes": ["exact", "lte", "gte"],
        }


@extend_schema_view(
    list=extend_schema(summary="Listar reglas de alerta", description="Devuelve todas las AlertRule configuradas. Filtros: punto, tipo, activa, frecuencia."),
    retrieve=extend_schema(summary="Detalle de regla de alerta", description="Obtiene una AlertRule específica con sus canales de notificación anidados."),
    create=extend_schema(summary="Crear regla de alerta", description="Crea una nueva regla para monitorear umbral, desconexión, reconexión o errores de procesamiento."),
    update=extend_schema(summary="Actualizar regla de alerta"),
    partial_update=extend_schema(summary="Actualizar parcialmente regla de alerta"),
    destroy=extend_schema(summary="Eliminar regla de alerta"),
)
class AlertRuleViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """
    CRUD completo para AlertRule.

    Listado usa serializer ligero; retrieve usa serializer con canales anidados.
    """
    permission_classes = [IsAuthenticated]
    filter_backends = (filters.DjangoFilterBackend, SearchFilter, OrderingFilter)
    filterset_class = AlertRuleFilter
    queryset = AlertRule.objects.select_related("point_catchment").prefetch_related("channels").order_by("-created")
    lookup_field = "id"
    search_fields = ['name', 'point_catchment__title']
    ordering_fields = ['created', 'name', 'check_frequency_minutes']

    def get_serializer_class(self):
        if self.action in ["list"]:
            return AlertRuleListSerializer
        elif self.action in ["retrieve"]:
            return AlertRuleDetailSerializer
        return AlertRuleWriteSerializer


class AlertChannelFilter(filters.FilterSet):
    class Meta:
        model = AlertChannel
        fields = {
            "alert_rule": ["exact"],
            "channel_type": ["exact"],
            "is_active": ["exact"],
        }


@extend_schema_view(
    list=extend_schema(summary="Listar canales de notificación", description="Canales EMAIL, GOOGLE_CHAT, WEBHOOK y SMS asociados a reglas de alerta."),
    retrieve=extend_schema(summary="Detalle de canal de notificación"),
    create=extend_schema(summary="Crear canal de notificación"),
    update=extend_schema(summary="Actualizar canal de notificación"),
    partial_update=extend_schema(summary="Actualizar parcialmente canal de notificación"),
    destroy=extend_schema(summary="Eliminar canal de notificación"),
)
class AlertChannelViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """CRUD completo para AlertChannel."""
    permission_classes = [IsAuthenticated]
    filter_backends = (filters.DjangoFilterBackend, SearchFilter, OrderingFilter)
    filterset_class = AlertChannelFilter
    queryset = AlertChannel.objects.select_related("alert_rule")
    serializer_class = AlertChannelSerializer
    lookup_field = "id"
    search_fields = ['destination', 'alert_rule__name']
    ordering_fields = ['created', 'channel_type']


class AlertTriggerFilter(filters.FilterSet):
    class Meta:
        model = AlertTrigger
        fields = {
            "alert_rule": ["exact"],
            "notification_sent": ["exact"],
            "is_acknowledged": ["exact"],
            "triggered_at": ["exact", "date", "date__gte", "date__lte"],
        }


@extend_schema_view(
    list=extend_schema(summary="Listar disparos de alerta", description="Historial de AlertTrigger. Filtros: regla, enviado, acknowledgado, fecha."),
    retrieve=extend_schema(summary="Detalle de disparo de alerta"),
    create=extend_schema(summary="Crear disparo de alerta (manual)"),
    update=extend_schema(summary="Actualizar disparo"),
    partial_update=extend_schema(summary="Actualizar parcialmente disparo"),
    destroy=extend_schema(summary="Eliminar disparo"),
)
class AlertTriggerViewSet(
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """
    Solo lectura y update parcial (acknowledge) para AlertTrigger.

    No se permite crear ni eliminar triggers desde la API;
    solo el motor (`alert_engine.py`) los crea.
    """
    permission_classes = [IsAuthenticated]
    filter_backends = (filters.DjangoFilterBackend, SearchFilter, OrderingFilter)
    filterset_class = AlertTriggerFilter
    queryset = (
        AlertTrigger.objects.select_related("alert_rule", "alert_rule__point_catchment")
        .prefetch_related("alert_rule__channels")
        .order_by("-triggered_at")
    )
    serializer_class = AlertTriggerSerializer
    lookup_field = "id"
    search_fields = ['alert_rule__name', 'point_catchment__title']
    ordering_fields = ['triggered_at', 'value_at_trigger']


class SystemEventFilter(filters.FilterSet):
    class Meta:
        model = SystemEvent
        fields = {
            "event_type": ["exact"],
            "severity": ["exact"],
            "point_catchment": ["exact"],
            "created": ["date", "date__gte", "date__lte"],
        }


@extend_schema_view(
    list=extend_schema(summary="Listar eventos del sistema", description="Eventos de auditoría: resets de contador, errores de medición, cambios de configuración."),
    retrieve=extend_schema(summary="Detalle de evento del sistema"),
)
class SystemEventViewSet(
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """Solo lectura para SystemEvent."""
    permission_classes = [IsAuthenticated]
    filter_backends = (filters.DjangoFilterBackend, SearchFilter, OrderingFilter)
    filterset_class = SystemEventFilter
    queryset = SystemEvent.objects.select_related("point_catchment").order_by("-created")
    serializer_class = SystemEventSerializer
    lookup_field = "id"
    search_fields = ['title', 'message', 'point_catchment__title']
    ordering_fields = ['created', 'severity', 'event_type']
