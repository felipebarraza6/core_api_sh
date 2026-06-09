"""
Serializers para el subsistema de Tickets de Soporte + SLA.
"""

from rest_framework import serializers

from api.core.models import (
    SupportTicket,
    TicketComment,
    TicketAttachment,
    TicketActivityLog,
    SLAConfig,
)


class SLAConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = SLAConfig
        fields = [
            "id", "client", "project", "category", "priority",
            "response_time_hours", "resolution_time_hours",
            "business_hours_only", "escalation_user", "is_active",
            "created", "modified",
        ]


class TicketAttachmentSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = TicketAttachment
        fields = [
            "id", "ticket", "comment", "file", "file_url",
            "original_name", "uploaded_by", "created",
        ]
        read_only_fields = ["uploaded_by", "created"]

    def get_file_url(self, obj):
        request = self.context.get("request")
        if obj.file and request:
            return request.build_absolute_uri(obj.file.url)
        return obj.file.url if obj.file else None


class TicketCommentSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source="author.get_full_name", read_only=True)
    attachments = TicketAttachmentSerializer(many=True, read_only=True)

    class Meta:
        model = TicketComment
        fields = [
            "id", "ticket", "author", "author_name",
            "content", "is_internal", "status_change",
            "attachments", "created", "modified",
        ]
        read_only_fields = ["author", "created", "modified"]


class TicketActivityLogSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.get_full_name", read_only=True)

    class Meta:
        model = TicketActivityLog
        fields = [
            "id", "ticket", "user", "user_name",
            "field_name", "old_value", "new_value", "created",
        ]
        read_only_fields = fields


class SupportTicketListSerializer(serializers.ModelSerializer):
    """Serializer ligero para listados."""

    point_title = serializers.CharField(source="point_catchment.title", read_only=True)
    client_name = serializers.CharField(source="point_catchment.project.client.name", read_only=True)
    created_by_name = serializers.CharField(source="created_by.get_full_name", read_only=True)
    assigned_to_name = serializers.CharField(source="assigned_to.get_full_name", read_only=True)
    comments_count = serializers.IntegerField(source="comments.count", read_only=True)

    class Meta:
        model = SupportTicket
        fields = [
            "id", "point_catchment", "point_title", "client_name",
            "title", "status", "priority", "category", "source", "origin",
            "created_by", "created_by_name", "assigned_to", "assigned_to_name",
            "comments_count", "created", "modified",
        ]


class SupportTicketDetailSerializer(serializers.ModelSerializer):
    """Serializer completo para retrieve. Incluye comentarios, adjuntos y logs."""

    point_title = serializers.CharField(source="point_catchment.title", read_only=True)
    client_name = serializers.CharField(source="point_catchment.project.client.name", read_only=True)
    created_by_name = serializers.CharField(source="created_by.get_full_name", read_only=True)
    assigned_to_name = serializers.CharField(source="assigned_to.get_full_name", read_only=True)
    comments = TicketCommentSerializer(many=True, read_only=True)
    activity_logs = TicketActivityLogSerializer(many=True, read_only=True)
    attachments = TicketAttachmentSerializer(many=True, read_only=True)

    class Meta:
        model = SupportTicket
        fields = [
            "id", "point_catchment", "point_title", "client_name",
            "title", "description",
            "created_by", "created_by_name", "assigned_to", "assigned_to_name",
            "status", "priority", "category", "source", "origin",
            "alert_trigger", "system_event",
            "sla_config", "sla_deadline_response", "sla_deadline_resolution",
            "sla_responded_at", "sla_resolved_at",
            "resolved_at", "closed_at",
            "is_active",
            "comments", "activity_logs", "attachments",
            "created", "modified",
        ]
        read_only_fields = [
            "sla_deadline_response", "sla_deadline_resolution",
            "sla_responded_at", "sla_resolved_at",
            "resolved_at", "closed_at",
            "created", "modified",
        ]


class SupportTicketWriteSerializer(serializers.ModelSerializer):
    """Serializer para create/update."""

    class Meta:
        model = SupportTicket
        fields = [
            "id", "point_catchment", "title", "description",
            "assigned_to", "status", "priority", "category", "source", "origin",
            "alert_trigger", "system_event",
            "is_active",
        ]

    def validate(self, attrs):
        # Ejecutar validación del modelo
        instance = SupportTicket(**attrs)
        if self.instance:
            instance.pk = self.instance.pk
            for field in ["point_catchment", "title", "description", "assigned_to",
                          "status", "priority", "category", "source", "origin",
                          "alert_trigger", "system_event", "is_active"]:
                if field not in attrs:
                    setattr(instance, field, getattr(self.instance, field))
        instance.clean()
        return attrs
