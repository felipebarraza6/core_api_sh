"""
Serializers para el subsistema de alertas.
"""

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from api.core.models.alerts import AlertRule, AlertChannel, AlertTrigger, SystemEvent


def _run_model_clean(serializer, attrs, model_class):
    """
    Helper para ejecutar model.clean() dentro de un serializer de DRF.
    Soporta tanto create como update (PATCH/PUT).
    """
    if serializer.instance:
        # Update: copiar campos existentes y sobreescribir con attrs
        instance = serializer.instance
        for key, value in attrs.items():
            setattr(instance, key, value)
    else:
        # Create: instancia temporal
        instance = model_class(**attrs)

    try:
        instance.clean()
    except DjangoValidationError as exc:
        raise serializers.ValidationError(exc.message_dict)

    return attrs


class AlertChannelSerializer(serializers.ModelSerializer):
    class Meta:
        model = AlertChannel
        fields = [
            "id", "alert_rule", "channel_type", "destination",
            "is_active", "template_override", "created", "modified",
        ]

    def validate(self, attrs):
        return _run_model_clean(self, attrs, AlertChannel)


class AlertChannelNestedSerializer(serializers.ModelSerializer):
    """Versión reducida para anidar dentro de AlertRule."""
    class Meta:
        model = AlertChannel
        fields = ["id", "channel_type", "destination", "is_active"]


class AlertTriggerSerializer(serializers.ModelSerializer):
    alert_rule_name = serializers.CharField(source="alert_rule.name", read_only=True)

    class Meta:
        model = AlertTrigger
        fields = [
            "id", "alert_rule", "alert_rule_name", "triggered_at",
            "value_at_trigger", "threshold_breached", "interaction_detail",
            "point_catchment",
            "notification_sent", "notification_error", "notification_sent_at",
            "ai_diagnosis",
            "is_acknowledged", "acknowledged_by", "acknowledged_at",
            "created", "modified",
        ]
        read_only_fields = fields


class AlertRuleListSerializer(serializers.ModelSerializer):
    """Serializer para listado: incluye conteo de canales y triggers recientes."""
    channels_count = serializers.IntegerField(source="channels.count", read_only=True)
    last_trigger_at = serializers.SerializerMethodField()
    point_catchment_title = serializers.CharField(source="point_catchment.title", read_only=True)

    class Meta:
        model = AlertRule
        fields = [
            "id", "name", "severity", "description", "point_catchment", "point_catchment_title",
            "points", "target_type", "variable_type", "is_active",
            "check_frequency_minutes", "cooldown_minutes",
            "channels_count", "last_trigger_at",
            "created", "modified",
        ]

    def get_last_trigger_at(self, obj: AlertRule) -> str:
        last = obj.triggers.order_by("-triggered_at").first()
        return last.triggered_at.isoformat() if last else None


class AlertRuleDetailSerializer(serializers.ModelSerializer):
    """Serializer para retrieve: incluye canales anidados."""
    channels = AlertChannelNestedSerializer(many=True, read_only=True)
    point_catchment_title = serializers.CharField(source="point_catchment.title", read_only=True)

    class Meta:
        model = AlertRule
        fields = [
            "id", "name", "severity", "description", "point_catchment", "point_catchment_title",
            "points", "target_type", "variable_type",
            "threshold_value", "no_data_minutes",
            "rate_change_value", "rate_change_window",
            "check_frequency_minutes", "cooldown_minutes",
            "is_active", "start_date", "end_date",
            "report_schedule", "report_hour",
            "channels",
            "created", "modified",
        ]


class AlertRuleWriteSerializer(serializers.ModelSerializer):
    """Serializer para create/update: sin canales anidados.

    Valida mediante model.clean() para garantizar consistencia
    con las reglas de negocio definidas en el modelo.
    """
    class Meta:
        model = AlertRule
        fields = [
            "id", "name", "severity", "description", "point_catchment", "points",
            "target_type", "variable_type",
            "threshold_value", "no_data_minutes",
            "rate_change_value", "rate_change_window",
            "check_frequency_minutes", "cooldown_minutes",
            "is_active", "start_date", "end_date",
            "report_schedule", "report_hour",
        ]

    def validate(self, attrs):
        return _run_model_clean(self, attrs, AlertRule)


class SystemEventSerializer(serializers.ModelSerializer):
    point_catchment_title = serializers.CharField(source="point_catchment.title", read_only=True)

    class Meta:
        model = SystemEvent
        fields = [
            "id", "event_type", "point_catchment", "point_catchment_title",
            "title", "message", "severity", "extra_data",
            "created", "modified",
        ]
