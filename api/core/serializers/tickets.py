"""
Serializers para el subsistema de Tickets de Soporte + SLA.
"""

from django.utils import timezone
from rest_framework import serializers

from api.core.models import (
    CatchmentPoint,
    SupportTicket,
    SupportTicketTask,
    TicketCategory,
    TicketComment,
    TicketAttachment,
    TicketActivityLog,
    TicketNotification,
    SLAConfig,
    User,
)


class TicketCategoryOperatorSerializer(serializers.ModelSerializer):
    """Serializer minimo para operadores de categoria."""

    name = serializers.CharField(source="get_full_name", read_only=True)

    class Meta:
        model = User
        fields = ["id", "name"]


class TicketCategorySerializer(serializers.ModelSerializer):
    """Serializer para categorías de tickets (con tipo y subcategorías)."""

    category_type_display = serializers.CharField(
        source="get_category_type_display", read_only=True
    )
    subcategories = serializers.PrimaryKeyRelatedField(many=True, read_only=True)
    operators = serializers.PrimaryKeyRelatedField(
        many=True, read_only=True,
    )
    operators_detail = TicketCategoryOperatorSerializer(
        source="operators", many=True, read_only=True
    )

    class Meta:
        model = TicketCategory
        fields = [
            "id", "category_type", "category_type_display", "name",
            "parent", "subcategories", "operators", "operators_detail",
            "notify_operators_on_create", "is_active", "created", "modified",
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
        if parent is None and self.instance:
            parent = self.instance.parent
        category_type = attrs.get("category_type")
        if category_type is None and self.instance:
            category_type = self.instance.category_type

        if parent and category_type and parent.category_type != category_type:
            raise serializers.ValidationError(
                {"parent": "La subcategoría debe ser del mismo tipo que su padre."}
            )

        # Evitar auto-referencia y ciclos simples (padre = sí misma)
        if parent and self.instance and parent.id == self.instance.pk:
            raise serializers.ValidationError(
                {"parent": "Una categoría no puede ser su propio padre."}
            )
        return attrs


class SLAConfigSerializer(serializers.ModelSerializer):
    category_detail = TicketCategorySerializer(source="category", read_only=True)
    escalation_user_name = serializers.CharField(
        source="escalation_user.get_full_name", read_only=True
    )

    class Meta:
        model = SLAConfig
        fields = [
            "id", "client", "project", "category", "category_detail", "priority",
            "response_time_hours", "resolution_time_hours",
            "business_hours_only", "escalation_user", "escalation_user_name", "is_active",
            "webhook_url", "created", "modified",
        ]


class SLAConfigWriteSerializer(serializers.ModelSerializer):
    """Serializer para crear/editar configuraciones SLA."""

    class Meta:
        model = SLAConfig
        fields = [
            "id", "client", "project", "category", "priority",
            "response_time_hours", "resolution_time_hours",
            "business_hours_only", "escalation_user", "is_active",
            "webhook_url",
        ]

    def validate(self, attrs):
        response = attrs.get("response_time_hours")
        resolution = attrs.get("resolution_time_hours")
        if response is not None and response <= 0:
            raise serializers.ValidationError(
                {"response_time_hours": "Debe ser un número positivo."}
            )
        if resolution is not None and resolution <= 0:
            raise serializers.ValidationError(
                {"resolution_time_hours": "Debe ser un número positivo."}
            )

        # Evitar duplicados exactos. En updates parciales se usan los valores
        # actuales de la instancia para los campos no enviados.
        instance = self.instance

        def _get_value(field):
            if field in attrs:
                return attrs[field]
            if instance:
                return getattr(instance, field)
            return None

        filters = {
            "client": _get_value("client"),
            "project": _get_value("project"),
            "category": _get_value("category"),
            "priority": _get_value("priority"),
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
    uploaded_by_name = serializers.CharField(
        source="uploaded_by.get_full_name", read_only=True, default=None
    )

    class Meta:
        model = TicketAttachment
        fields = [
            "id", "ticket", "comment", "task", "file", "file_url",
            "original_name", "uploaded_by", "uploaded_by_name", "created",
        ]
        read_only_fields = ["uploaded_by", "uploaded_by_name", "created"]

    def get_file_url(self, obj):
        request = self.context.get("request")
        if obj.file and request:
            return request.build_absolute_uri(obj.file.url)
        return obj.file.url if obj.file else None


class TicketCommentSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source="author.get_full_name", read_only=True)
    attachments = TicketAttachmentSerializer(many=True, read_only=True)
    parent_id = serializers.IntegerField(
        source="parent.id", read_only=True, default=None
    )
    reply_count = serializers.IntegerField(source="replies.count", read_only=True)
    like_count = serializers.SerializerMethodField()
    liked_by_me = serializers.SerializerMethodField()

    class Meta:
        model = TicketComment
        fields = [
            "id", "ticket", "parent_id", "author", "author_name",
            "content", "is_internal", "status_change",
            "attachments", "reply_count",
            "like_count", "liked_by_me",
            "created", "modified",
        ]
        read_only_fields = ["author", "created", "modified"]

    def get_like_count(self, obj):
        annotated = getattr(obj, "like_count", None)
        if annotated is not None:
            return annotated
        return obj.likes.count()

    def get_liked_by_me(self, obj):
        annotated = getattr(obj, "liked_by_me", None)
        if annotated is not None:
            return bool(annotated)
        request = self.context.get("request") if self.context else None
        if not request or not request.user or request.user.is_anonymous:
            return False
        return obj.likes.filter(user_id=request.user.id).exists()


class SupportTicketTaskSerializer(serializers.ModelSerializer):
    """Tarea de ticket. Incluye adjuntos y nombre de asignado/creador."""

    attachments = TicketAttachmentSerializer(many=True, read_only=True)
    assigned_to_name = serializers.CharField(
        source="assigned_to.get_full_name", read_only=True, default=None
    )
    created_by_name = serializers.CharField(
        source="created_by.get_full_name", read_only=True, default=None
    )

    class Meta:
        model = SupportTicketTask
        fields = [
            "id", "ticket", "title", "description", "status", "priority",
            "assigned_to", "assigned_to_name",
            "due_date", "created_stage", "created_by", "created_by_name",
            "attachments", "created", "modified",
        ]
        read_only_fields = ["created_stage", "created_by", "created", "modified"]


class SupportTicketTaskWriteSerializer(serializers.ModelSerializer):
    """Creación/edición de tarea. created_stage se fija con el estado del ticket."""

    class Meta:
        model = SupportTicketTask
        fields = [
            "id", "ticket", "title", "description", "status", "priority",
            "assigned_to", "due_date",
        ]

    def validate(self, attrs):
        ticket = attrs.get("ticket") or getattr(self.instance, "ticket", None)
        if ticket is None:
            raise serializers.ValidationError("La tarea debe pertenecer a un ticket.")
        attrs["created_stage"] = ticket.status
        return attrs


class TicketAttachmentWriteSerializer(serializers.ModelSerializer):
    """Subida de archivo ligada a un comentario o a una tarea."""

    class Meta:
        model = TicketAttachment
        fields = ["id", "ticket", "comment", "task", "file", "original_name"]

    def validate(self, attrs):
        comment = attrs.get("comment")
        task = attrs.get("task")
        if comment and task:
            raise serializers.ValidationError(
                "Un adjunto no puede pertenecer a un comentario y a una tarea a la vez."
            )
        return attrs


class FileDriveSerializer(serializers.ModelSerializer):
    """Vista "drive": cada archivo con su contexto (ticket, comentario o tarea)."""

    file_url = serializers.SerializerMethodField()
    uploaded_by_name = serializers.CharField(
        source="uploaded_by.get_full_name", read_only=True, default=None
    )
    ticket_id = serializers.IntegerField(source="ticket.id", read_only=True)
    ticket_title = serializers.CharField(source="ticket.title", read_only=True)
    comment_id = serializers.IntegerField(source="comment.id", read_only=True, default=None)
    comment_snippet = serializers.SerializerMethodField()
    task_id = serializers.IntegerField(source="task.id", read_only=True, default=None)
    task_title = serializers.CharField(source="task.title", read_only=True, default=None)
    project_id = serializers.SerializerMethodField()
    project_name = serializers.SerializerMethodField()
    client_id = serializers.SerializerMethodField()
    client_name = serializers.SerializerMethodField()

    class Meta:
        model = TicketAttachment
        fields = [
            "id", "ticket_id", "ticket_title",
            "comment_id", "comment_snippet",
            "task_id", "task_title",
            "project_id", "project_name", "client_id", "client_name",
            "file_url", "original_name", "uploaded_by", "uploaded_by_name",
            "created",
        ]
        read_only_fields = fields

    def get_file_url(self, obj):
        request = self.context.get("request")
        if obj.file and request:
            return request.build_absolute_uri(obj.file.url)
        return obj.file.url if obj.file else None

    def get_comment_snippet(self, obj):
        if obj.comment:
            return obj.comment.content[:120]
        return None

    def get_project_id(self, obj):
        first = obj.ticket.points.first() if obj.ticket else None
        return first.project_id if first and first.project else None

    def get_project_name(self, obj):
        first = obj.ticket.points.first() if obj.ticket else None
        return first.project.name if first and first.project else None

    def get_client_id(self, obj):
        first = obj.ticket.points.first() if obj.ticket else None
        return first.project.client_id if first and first.project and first.project.client else None

    def get_client_name(self, obj):
        first = obj.ticket.points.first() if obj.ticket else None
        return (
            first.project.client.name
            if first and first.project and first.project.client else None
        )


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
    scheduled_date_confirmed_by_name = serializers.SerializerMethodField(read_only=True)
    scheduled_date_cancelled_by_name = serializers.SerializerMethodField(read_only=True)
    comments_count = serializers.IntegerField(source="comments.count", read_only=True)
    category_detail = TicketCategorySerializer(source="category", read_only=True)
    work_order_category_detail = TicketCategorySerializer(source="work_order_category", read_only=True)

    class Meta:
        model = SupportTicket
        fields = [
            "id", "points", "client_name",
            "title", "status", "priority", "category", "category_detail",
            "work_order_category", "work_order_category_detail",
            "source", "origin",
            "created_by", "created_by_name", "assigned_to", "assigned_to_name",
            "scheduled_date", "scheduled_date_confirmed",
            "scheduled_date_confirmed_by", "scheduled_date_confirmed_by_name",
            "scheduled_date_confirmed_at",
            "scheduled_date_cancelled", "scheduled_date_cancelled_by",
            "scheduled_date_cancelled_by_name", "scheduled_date_cancelled_at",
            "scheduled_date_cancelled_reason", "comments_count",
            "sla_deadline_response", "sla_deadline_resolution",
            "sla_responded_at", "sla_resolved_at",
            "created", "modified",
        ]
        read_only_fields = [
            "sla_deadline_response", "sla_deadline_resolution",
            "sla_responded_at", "sla_resolved_at",
            "scheduled_date_confirmed", "scheduled_date_confirmed_by",
            "scheduled_date_confirmed_at",
            "scheduled_date_cancelled", "scheduled_date_cancelled_by",
            "scheduled_date_cancelled_at", "scheduled_date_cancelled_reason",
        ]

    def get_client_name(self, obj):
        first = obj.points.first()
        if first and first.project and first.project.client:
            return first.project.client.name
        return None

    def get_scheduled_date_confirmed_by_name(self, obj):
        if obj.scheduled_date_confirmed_by:
            return (
                obj.scheduled_date_confirmed_by.get_full_name()
                or obj.scheduled_date_confirmed_by.email
            )
        return None

    def get_scheduled_date_cancelled_by_name(self, obj):
        if obj.scheduled_date_cancelled_by:
            return (
                obj.scheduled_date_cancelled_by.get_full_name()
                or obj.scheduled_date_cancelled_by.email
            )
        return None


class SupportTicketDetailSerializer(serializers.ModelSerializer):
    """Serializer completo para retrieve. Incluye comentarios, adjuntos y logs."""

    points = TicketPointSerializer(many=True, read_only=True)
    client_name = serializers.SerializerMethodField(read_only=True)
    created_by_name = serializers.CharField(source="created_by.get_full_name", read_only=True)
    assigned_to_name = serializers.CharField(source="assigned_to.get_full_name", read_only=True)
    scheduled_date_confirmed_by_name = serializers.SerializerMethodField(read_only=True)
    scheduled_date_cancelled_by_name = serializers.SerializerMethodField(read_only=True)
    comments = TicketCommentSerializer(many=True, read_only=True)
    activity_logs = TicketActivityLogSerializer(many=True, read_only=True)
    attachments = TicketAttachmentSerializer(many=True, read_only=True)
    tasks = SupportTicketTaskSerializer(many=True, read_only=True)
    category_detail = TicketCategorySerializer(source="category", read_only=True)
    work_order_category_detail = TicketCategorySerializer(source="work_order_category", read_only=True)

    class Meta:
        model = SupportTicket
        fields = [
            "id", "points", "client_name",
            "title", "description",
            "created_by", "created_by_name", "assigned_to", "assigned_to_name",
            "status", "priority", "category", "category_detail",
            "work_order_category", "work_order_category_detail",
            "source", "origin",
            "alert_trigger", "system_event",
            "sla_config", "sla_deadline_response", "sla_deadline_resolution",
            "sla_responded_at", "sla_resolved_at", "sla_paused_at",
            "resolved_at", "closed_at",
            "scheduled_date", "scheduled_date_confirmed",
            "scheduled_date_confirmed_by", "scheduled_date_confirmed_by_name",
            "scheduled_date_confirmed_at",
            "scheduled_date_cancelled", "scheduled_date_cancelled_by",
            "scheduled_date_cancelled_by_name", "scheduled_date_cancelled_at",
            "scheduled_date_cancelled_reason", "visit_report",
            "is_active",
            "comments", "activity_logs", "attachments", "tasks",
            "created", "modified",
        ]
        read_only_fields = [
            "sla_deadline_response", "sla_deadline_resolution",
            "sla_responded_at", "sla_resolved_at", "sla_paused_at",
            "resolved_at", "closed_at",
            "scheduled_date_confirmed", "scheduled_date_confirmed_by",
            "scheduled_date_confirmed_at",
            "scheduled_date_cancelled", "scheduled_date_cancelled_by",
            "scheduled_date_cancelled_at", "scheduled_date_cancelled_reason",
            "created", "modified",
        ]

    def get_client_name(self, obj):
        first = obj.points.first()
        if first and first.project and first.project.client:
            return first.project.client.name
        return None

    def get_scheduled_date_confirmed_by_name(self, obj):
        if obj.scheduled_date_confirmed_by:
            return (
                obj.scheduled_date_confirmed_by.get_full_name()
                or obj.scheduled_date_confirmed_by.email
            )
        return None

    def get_scheduled_date_cancelled_by_name(self, obj):
        if obj.scheduled_date_cancelled_by:
            return (
                obj.scheduled_date_cancelled_by.get_full_name()
                or obj.scheduled_date_cancelled_by.email
            )
        return None


class SupportTicketWriteSerializer(serializers.ModelSerializer):
    """Serializer para create/update."""

    points = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=CatchmentPoint.objects.all(),
        write_only=True,
        required=False,
    )
    category = serializers.PrimaryKeyRelatedField(
        queryset=TicketCategory.objects.filter(
            category_type__in=["SOFTWARE", "HARDWARE", "COMPLIANCE"]
        ),
        required=False,
        allow_null=True,
    )
    work_order_category = serializers.PrimaryKeyRelatedField(
        queryset=TicketCategory.objects.filter(
            category_type="WORK_ORDER", parent__isnull=False, is_active=True
        ),
        required=False,
        allow_null=True,
    )

    class Meta:
        model = SupportTicket
        fields = [
            "id", "points", "title", "description",
            "assigned_to", "status", "priority", "category", "source", "origin",
            "work_order_category",
            "alert_trigger", "system_event",
            "scheduled_date", "visit_report",
            "is_active",
        ]

    def validate(self, attrs):
        points = attrs.get("points")
        if self.instance and "points" not in attrs:
            points = list(self.instance.points.all())

        origin = attrs.get("origin")
        if self.instance and "origin" not in attrs:
            origin = self.instance.origin

        # Ejecutar validación del modelo (M2M no se puede pasar al __init__)
        model_attrs = {k: v for k, v in attrs.items() if k != "points"}
        instance = SupportTicket(**model_attrs)
        if self.instance:
            instance.pk = self.instance.pk
            for field in [
                "title", "description", "assigned_to",
                "status", "priority", "category", "source", "origin",
                "work_order_category",
                "alert_trigger", "system_event", "is_active",
            ]:
                if field not in model_attrs:
                    setattr(instance, field, getattr(self.instance, field))
        instance.clean()

        # La categoría de OT solo persiste en estado EN_ORDEN_TRABAJO.
        if instance.status != "EN_ORDEN_TRABAJO":
            attrs["work_order_category"] = None
        return attrs

    def update(self, instance, validated_data):
        # Si cambia la fecha planificada, la confirmación previa deja de valer
        # y también se cancela cualquier cancelación anterior (re-agendar).
        if (
            "scheduled_date" in validated_data
            and instance.scheduled_date != validated_data["scheduled_date"]
        ):
            instance.scheduled_date_confirmed = False
            instance.scheduled_date_confirmed_by = None
            instance.scheduled_date_confirmed_at = None
            instance.scheduled_date_cancelled = False
            instance.scheduled_date_cancelled_by = None
            instance.scheduled_date_cancelled_at = None
            instance.scheduled_date_cancelled_reason = None

        points = validated_data.pop("points", None)
        instance = super().update(instance, validated_data)
        if points is not None:
            instance.points.set(points)
        return instance
class TicketDashboardRowSerializer(serializers.ModelSerializer):
    """Serializer ligero para filas de tablas del dashboard de soporte."""

    category_type = serializers.CharField(
        source="category.category_type", read_only=True, default=None
    )
    assigned_to_name = serializers.CharField(
        source="assigned_to.get_full_name", read_only=True, default=None
    )
    overdue_days = serializers.SerializerMethodField()

    class Meta:
        model = SupportTicket
        fields = [
            "id", "title", "priority", "status",
            "sla_deadline_resolution", "sla_deadline_response",
            "category_type", "assigned_to_name", "overdue_days",
        ]

    def get_overdue_days(self, obj):
        deadline = obj.sla_deadline_resolution or obj.sla_deadline_response
        if deadline:
            delta = timezone.now() - deadline
            return max(0, delta.days)
        return None


class TicketNotificationSerializer(serializers.ModelSerializer):
    """Notificación in-app del subsistema de tickets."""

    ticket_title = serializers.CharField(source="ticket.title", read_only=True)
    comment_id = serializers.IntegerField(
        source="comment.id", read_only=True, default=None
    )
    notification_type_display = serializers.CharField(
        source="get_notification_type_display", read_only=True
    )

    class Meta:
        model = TicketNotification
        fields = [
            "id", "notification_type", "notification_type_display",
            "ticket", "ticket_title", "comment_id",
            "message", "is_read", "created",
        ]
