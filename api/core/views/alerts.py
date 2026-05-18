"""
ViewSets para el subsistema de alertas.
"""

from django_filters import rest_framework as filters
from rest_framework import mixins, viewsets
from rest_framework.permissions import IsAuthenticated

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
    filter_backends = (filters.DjangoFilterBackend,)
    filterset_class = AlertRuleFilter
    queryset = AlertRule.objects.select_related("point_catchment").prefetch_related("channels").order_by("-created")
    lookup_field = "id"

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
    filter_backends = (filters.DjangoFilterBackend,)
    filterset_class = AlertChannelFilter
    queryset = AlertChannel.objects.select_related("alert_rule")
    serializer_class = AlertChannelSerializer
    lookup_field = "id"


class AlertTriggerFilter(filters.FilterSet):
    class Meta:
        model = AlertTrigger
        fields = {
            "alert_rule": ["exact"],
            "notification_sent": ["exact"],
            "is_acknowledged": ["exact"],
            "triggered_at": ["exact", "date", "date__gte", "date__lte"],
        }


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
    filter_backends = (filters.DjangoFilterBackend,)
    filterset_class = AlertTriggerFilter
    queryset = (
        AlertTrigger.objects.select_related("alert_rule", "alert_rule__point_catchment")
        .prefetch_related("alert_rule__channels")
        .order_by("-triggered_at")
    )
    serializer_class = AlertTriggerSerializer
    lookup_field = "id"


class SystemEventFilter(filters.FilterSet):
    class Meta:
        model = SystemEvent
        fields = {
            "event_type": ["exact"],
            "severity": ["exact"],
            "point_catchment": ["exact"],
            "created": ["date", "date__gte", "date__lte"],
        }


class SystemEventViewSet(
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """Solo lectura para SystemEvent."""
    permission_classes = [IsAuthenticated]
    filter_backends = (filters.DjangoFilterBackend,)
    filterset_class = SystemEventFilter
    queryset = SystemEvent.objects.select_related("point_catchment").order_by("-created")
    serializer_class = SystemEventSerializer
    lookup_field = "id"
