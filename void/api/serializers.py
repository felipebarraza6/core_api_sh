"""Serializers for void API."""
from rest_framework import serializers

from void.models import (
    AlertRule,
    AlertTrigger,
    Client,
    ComplianceAuthority,
    ComplianceStandard,
    Device,
    DeviceHardware,
    DeviceVariableConfig,
    MqttTopicConfig,
    Point,
    PointComplianceProfile,
    PointGroup,
    PointPermission,
    ProcessedReading,
    Project,
    Provider,
    ProviderEndpoint,
    VoidUserProfile,
)


class NestedUserSerializer(serializers.ModelSerializer):
    """Datos mínimos del usuario Django."""

    class Meta:
        model = VoidUserProfile.user.field.related_model
        fields = ["id", "username", "email", "first_name", "last_name"]


class VoidUserProfileSerializer(serializers.ModelSerializer):
    user = NestedUserSerializer(read_only=True)

    class Meta:
        model = VoidUserProfile
        fields = [
            "id",
            "user",
            "role",
            "phone",
            "timezone",
            "notification_preferences",
            "is_active",
            "created",
        ]
        read_only_fields = ["created"]


class ClientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Client
        fields = [
            "id",
            "name",
            "tax_id",
            "status",
            "contact_name",
            "contact_email",
            "contact_phone",
            "billing_email",
            "billing_phone",
            "billing_address",
            "notes",
            "metadata",
            "created",
        ]


class ProjectSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source="client.name", read_only=True)

    class Meta:
        model = Project
        fields = [
            "id",
            "name",
            "description",
            "client",
            "client_name",
            "code_internal",
            "is_active",
            "created",
        ]


class PointGroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = PointGroup
        fields = ["id", "name", "description", "points", "created"]


class PointPermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PointPermission
        fields = ["id", "user", "group", "permission", "created"]


class ProviderEndpointSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProviderEndpoint
        fields = [
            "id",
            "endpoint_type",
            "name",
            "http_method",
            "path_template",
            "headers",
            "query_params",
            "body_template",
            "response_parser",
            "is_active",
            "order",
        ]


class MqttTopicConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = MqttTopicConfig
        fields = [
            "id",
            "name",
            "topic_template",
            "qos",
            "payload_parser",
            "is_active",
        ]


class ProviderSerializer(serializers.ModelSerializer):
    endpoints = ProviderEndpointSerializer(many=True, read_only=True)
    mqtt_topics = MqttTopicConfigSerializer(many=True, read_only=True)

    class Meta:
        model = Provider
        fields = [
            "id",
            "name",
            "description",
            "protocol",
            "base_url",
            "auth_type",
            "auth_config",
            "is_active",
            "metadata",
            "endpoints",
            "mqtt_topics",
            "created",
        ]


class DeviceVariableConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeviceVariableConfig
        fields = [
            "id",
            "source_variable",
            "internal_variable",
            "processing_type",
            "pulses_factor",
            "offset",
            "scale",
            "max_diff_m3_per_hour",
            "reconnection_threshold_hours",
            "compute_flow",
            "unit",
            "is_active",
            "display_name",
            "output_field",
            "formula",
            "custom_schema",
            "extra_data",
        ]


class DeviceHardwareSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeviceHardware
        fields = [
            "id",
            "component_type",
            "serial",
            "model",
            "manufacturer",
            "installation_date",
            "warranty_until",
            "status",
            "notes",
        ]


class DeviceSerializer(serializers.ModelSerializer):
    variable_configs = DeviceVariableConfigSerializer(many=True, read_only=True)
    hardware = DeviceHardwareSerializer(many=True, read_only=True)
    provider_name = serializers.CharField(source="provider.name", read_only=True)

    class Meta:
        model = Device
        fields = [
            "id",
            "point",
            "provider",
            "provider_name",
            "external_id",
            "serial_number",
            "model",
            "firmware_version",
            "configuration",
            "is_active",
            "activated_at",
            "variable_configs",
            "hardware",
            "created",
        ]


class PointComplianceProfileInlineSerializer(serializers.ModelSerializer):
    authority_code = serializers.CharField(source="authority.code", read_only=True)
    standard_code = serializers.CharField(source="standard.code", read_only=True)

    class Meta:
        model = PointComplianceProfile
        fields = [
            "id",
            "authority",
            "authority_code",
            "standard",
            "standard_code",
            "type_key",
            "external_code",
            "is_active",
        ]


class ComplianceAuthoritySerializer(serializers.ModelSerializer):
    class Meta:
        model = ComplianceAuthority
        fields = [
            "id",
            "code",
            "name",
            "protocol",
            "auth_type",
            "base_url",
            "auth_url",
            "auth_username",
            "auth_password",
            "auth_token",
            "auth_header_name",
            "protocol_config",
            "timeout_seconds",
            "retry_attempts",
            "is_active",
            "created",
        ]
        read_only_fields = ["created"]
        extra_kwargs = {
            "auth_password": {"write_only": True},
            "auth_token": {"write_only": True},
        }


class ComplianceStandardSerializer(serializers.ModelSerializer):
    class Meta:
        model = ComplianceStandard
        fields = [
            "id",
            "code",
            "name",
            "description",
            "frequency_minutes",
            "send_minute",
            "minute_interval",
            "send_hour",
            "send_day",
            "send_month",
            "is_active",
            "created",
        ]
        read_only_fields = ["created"]


class PointComplianceProfileSerializer(serializers.ModelSerializer):
    authority = ComplianceAuthoritySerializer(read_only=True)
    standard = ComplianceStandardSerializer(read_only=True)
    authority_id = serializers.PrimaryKeyRelatedField(
        queryset=ComplianceAuthority.objects.all(),
        source="authority",
        write_only=True,
    )
    standard_id = serializers.PrimaryKeyRelatedField(
        queryset=ComplianceStandard.objects.all(),
        source="standard",
        write_only=True,
        required=False,
        allow_null=True,
    )

    class Meta:
        model = PointComplianceProfile
        fields = [
            "id",
            "point",
            "authority",
            "authority_id",
            "standard",
            "standard_id",
            "is_active",
            "external_code",
            "standard_legacy",
            "type_key",
            "region",
            "shac",
            "flow_granted",
            "total_granted",
            "informant_name",
            "informant_rut",
            "date_start_compliance",
            "date_created_code",
            "aggregate_points",
            "variable_mapping",
            "extra_config",
            "created",
        ]
        read_only_fields = ["created"]


class AlertRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = AlertRule
        fields = [
            "id",
            "name",
            "is_active",
            "event_types",
            "severities",
            "device_ids",
            "point_ids",
            "variables",
            "cooldown_minutes",
            "channels",
            "recipients",
            "message_template",
            "created",
        ]
        read_only_fields = ["created"]


class AlertTriggerSerializer(serializers.ModelSerializer):
    rule_name = serializers.CharField(source="rule.name", read_only=True)
    event_type = serializers.CharField(source="event.event_type", read_only=True)
    device_id = serializers.IntegerField(source="event.device_id", read_only=True)

    class Meta:
        model = AlertTrigger
        fields = [
            "id",
            "rule",
            "rule_name",
            "event",
            "event_type",
            "device_id",
            "channels",
            "recipients",
            "message",
            "status",
            "dispatched_at",
            "dispatch_result",
            "created",
        ]
        read_only_fields = [
            "rule", "event", "channels", "recipients", "message",
            "status", "dispatched_at", "dispatch_result", "created",
        ]


class PointSummarySerializer(serializers.ModelSerializer):
    """Liviano, para listados."""

    client_name = serializers.CharField(source="client_fk.name", read_only=True)
    project_name = serializers.CharField(source="project_fk.name", read_only=True)

    class Meta:
        model = Point
        fields = [
            "id",
            "name",
            "code_internal",
            "client_fk",
            "client_name",
            "project_fk",
            "project_name",
            "frequency_minutes",
            "is_active",
            "migration_status",
            "installed_at",
        ]


class PointSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source="client_fk.name", read_only=True)
    project_name = serializers.CharField(source="project_fk.name", read_only=True)
    compliance_profiles = PointComplianceProfileInlineSerializer(many=True, read_only=True)

    class Meta:
        model = Point
        fields = [
            "id",
            "name",
            "code_internal",
            "description",
            "lat",
            "lon",
            "frequency_minutes",
            "is_active",
            "installed_at",
            "decommissioned_at",
            "project_fk",
            "project_name",
            "client_fk",
            "client_name",
            "legacy_point",
            "migration_status",
            "constants",
            "replicate_on_missing",
            "max_replication_hours",
            "extra_data",
            "compliance_profiles",
            "created",
        ]
        read_only_fields = ["created"]


class ProcessedReadingSerializer(serializers.ModelSerializer):
    device_serial = serializers.CharField(source="device.serial_number", read_only=True)
    point_id = serializers.IntegerField(source="device.point_id", read_only=True)

    class Meta:
        model = ProcessedReading
        fields = [
            "id",
            "device",
            "device_serial",
            "point_id",
            "variable",
            "timestamp",
            "pulses",
            "total",
            "flow",
            "nivel",
            "water_table",
            "total_diff",
            "total_today_diff",
            "extra_values",
            "is_reset",
            "is_reconnection",
            "is_interpolated",
            "is_error",
            "error_message",
            "processed_at",
        ]
