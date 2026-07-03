"""
Serializers para el subsistema de Tickets de Soporte + SLA.
"""

from rest_framework import serializers

from api.core.models import (
    CatchmentPoint,
    SupportTicket,
    TicketCategory,
    TicketComment,
    TicketAttachment,
    TicketActivityLog,
    SLAConfig,
    User,
)


class TicketCategorySerializer(serializers.ModelSerializer):
    """Serializer para categorías de tickets (con tipo y subcategorías)."""

    category_type_display = serializers.CharField(
        source="get_category_type_display", read_only=True
    )
    subcategories = serializers.PrimaryKeyRelatedField(many=True, read_only=True)
    operators = serializers.PrimaryKeyRelatedField(
        many=True, read_only=True,
    )

    class Meta:
        model = TicketCategory
        fields = [
            "id", "category_type", "category_type_display", "name",
            "parent", "subcategories", "operators", "notify_operators_on_create",
            "is_active", "created", "modified",
        ]


class TicketCategoryWriteSerializer(serializers.ModelSerializer):
    """Serializer para crear/editar categorías de tickets."""

    operators = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=User.objects.filter(is_active=True),
        required=False,
    )

    class Meta:
        model = TicketCategory
        fields = [
            "id", "category_type", "name", "parent",
            "operators", "notify_operators_on_create", "is_active",
        ]

    def validate(self, attrs):
        parent = attrs.get("parent")
        category_type = attrs.get("category_type")
        if parent and category_type and parent.category_type != category_type:
            raise serializers.ValidationError(
                {"parent": "La subcategoría debe ser del mismo tipo que su padre."}
            )
        if parent and attrs.get("id") and parent.id == attrs["id"]:
            raise serializers.ValidationError(
                {"parent": "Una categoría no puede ser su propio padre."}
            )
        return attrs


class SLAConfigSerializer(serializers.ModelSerializer):
    category_detail = TicketCategorySerializer(source="category", read_only=True)

    class Meta:
        model = SLAConfig
        fields = [
            "id", "client", "project", "category", "category_detail", "priority",
            "response_time_hours", "resolution_time_hours",
            "business_hours_only", "escalation_user", "is_active",
            "created", "modified",
        ]


class SLAConfigWriteSerializer(serializers.ModelSerializer):
    """Serializer para crear/editar configuraciones SLA."""

    class Meta:
        model = SLAConfig
        fields = [
            "id", "client", "project", "category", "priority",
            "response_time_hours", "resolution_time_hours",
            "business_hours_only", "escalation_user", "is_active",
        ]

    def validate(self, attrs):
        response = attrs.get("response_time_hours")
        resolution = attrs.get("resolution_time_hours")
        if response is not None and response < 0:
            raise serializers.ValidationError(
                {"response_time_hours": "Debe ser un número positivo."}
            )
        if resolution is not None and resolution < 0:
            raise serializers.ValidationError(
                {"resolution_time_hours": "Debe ser un número positivo."}
            )

        # Evitar duplicados exactos
        instance = self.instance
        filters = {
            "client": attrs.get("client"),
            "project": attrs.get("project"),
            "category": attrs.get("category"),
            "priority": attrs.get("priority"),
        }
        qs = SLAConfig.objects.filter(**filters)
        if instance:
            qs = qs.exclude(pk=instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                "Ya existe una configuración SLA con esa combinación de cliente, proyecto, categoría y prioridad."
            )
        return attrs


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


class TicketPointSerializer(serializers.ModelSerializer):
    """Serializer mínimo para puntos vinculados a un ticket."""

    class Meta:
        model = CatchmentPoint
        fields = ["id", "title"]


class SupportTicketListSerializer(serializers.ModelSerializer):
    """Serializer ligero para listados."""

    points = TicketPointSerializer(many=True, read_only=True)
    client_name = serializers.SerializerMethodField(read_only=True)
    created_by_name = serializers.CharField(source="created_by.get_full_name", read_only=True)
    assigned_to_name = serializers.CharField(source="assigned_to.get_full_name", read_only=True)
    comments_count = serializers.IntegerField(source="comments.count", read_only=True)
    category_detail = TicketCategorySerializer(source="category", read_only=True)

    class Meta:
        model = SupportTicket
        fields = [
            "id", "points", "client_name",
            "title", "status", "priority", "category", "category_detail",
            "source", "origin",
            "created_by", "created_by_name", "assigned_to", "assigned_to_name",
            "scheduled_date", "comments_count", "created", "modified",
        ]

    def get_client_name(self, obj):
        first = obj.points.first()
        if first and first.project and first.project.client:
            return first.project.client.name
        return None


class SupportTicketDetailSerializer(serializers.ModelSerializer):
    """Serializer completo para retrieve. Incluye comentarios, adjuntos y logs."""

    points = TicketPointSerializer(many=True, read_only=True)
    client_name = serializers.SerializerMethodField(read_only=True)
    created_by_name = serializers.CharField(source="created_by.get_full_name", read_only=True)
    assigned_to_name = serializers.CharField(source="assigned_to.get_full_name", read_only=True)
    comments = TicketCommentSerializer(many=True, read_only=True)
    activity_logs = TicketActivityLogSerializer(many=True, read_only=True)
    attachments = TicketAttachmentSerializer(many=True, read_only=True)
    category_detail = TicketCategorySerializer(source="category", read_only=True)

    class Meta:
        model = SupportTicket
        fields = [
            "id", "points", "client_name",
            "title", "description",
            "created_by", "created_by_name", "assigned_to", "assigned_to_name",
            "status", "priority", "category", "category_detail",
            "source", "origin",
            "alert_trigger", "system_event",
            "sla_config", "sla_deadline_response", "sla_deadline_resolution",
            "sla_responded_at", "sla_resolved_at",
            "resolved_at", "closed_at",
            "scheduled_date", "visit_report",
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

    def get_client_name(self, obj):
        first = obj.points.first()
        if first and first.project and first.project.client:
            return first.project.client.name
        return None


class SupportTicketWriteSerializer(serializers.ModelSerializer):
    """Serializer para create/update."""

    points = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=CatchmentPoint.objects.all(),
        write_only=True,
    )

    class Meta:
        model = SupportTicket
        fields = [
            "id", "points", "title", "description",
            "assigned_to", "status", "priority", "category", "source", "origin",
            "alert_trigger", "system_event",
            "scheduled_date", "visit_report",
            "is_active",
        ]

    def validate_points(self, value):
        if not value:
            raise serializers.ValidationError("Debe seleccionar al menos un punto.")
        return value

    def validate(self, attrs):
        points = attrs.get("points")
        if self.instance and "points" not in attrs:
            points = list(self.instance.points.all())
        if not points:
            raise serializers.ValidationError(
                {"points": "Debe seleccionar al menos un punto."}
            )

        # Ejecutar validación del modelo (M2M no se puede pasar al __init__)
        model_attrs = {k: v for k, v in attrs.items() if k != "points"}
        instance = SupportTicket(**model_attrs)
        if self.instance:
            instance.pk = self.instance.pk
            for field in [
                "title", "description", "assigned_to",
                "status", "priority", "category", "source", "origin",
                "alert_trigger", "system_event", "is_active",
            ]:
                if field not in model_attrs:
                    setattr(instance, field, getattr(self.instance, field))
        instance.clean()
        return attrs
