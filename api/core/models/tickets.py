"""
Subsistema de Tickets de Soporte + SLA.

Módulo completamente nuevo; no toca legacy (NotificationsCatchment).
Se expone vía API bajo /api/ik/tickets/.
"""

from django.core.exceptions import ValidationError
from django.db import models

from .catchment_points import CatchmentPoint, Client, ProjectCatchments
from .utils import ModelApi


class TicketCategory(ModelApi):
    """
    Categorías dinámicas para tickets de soporte.
    Cada categoría pertenece a un tipo fijo (SOFTWARE, HARDWARE, COMPLIANCE,
    WORK_ORDER) y puede tener subcategorías del mismo tipo.
    """

    TYPE_CHOICES = [
        ("SOFTWARE", "Software"),
        ("HARDWARE", "Hardware"),
        ("COMPLIANCE", "Cumplimiento"),
        ("WORK_ORDER", "Orden de Trabajo"),
    ]

    category_type = models.CharField(
        max_length=20,
        choices=TYPE_CHOICES,
        verbose_name="Tipo",
    )
    name = models.CharField(max_length=100, verbose_name="Nombre")
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="subcategories",
        verbose_name="Categoría padre",
    )
    operators = models.ManyToManyField(
        "core.User",
        blank=True,
        related_name="operated_ticket_categories",
        verbose_name="Operadores",
        help_text="Usuarios que recibirán notificación cuando se cree un ticket en esta categoría.",
    )
    notify_operators_on_create = models.BooleanField(
        default=True,
        verbose_name="Notificar operadores al crear ticket",
        help_text="Si está activo, se enviará un correo a los operadores cuando se cree un ticket de esta categoría.",
    )
    is_active = models.BooleanField(default=True, verbose_name="Activa")

    class Meta:
        verbose_name = "Categoría de ticket"
        verbose_name_plural = "Categorías de tickets"
        ordering = ["category_type", "name"]
        unique_together = [["category_type", "name", "parent"]]

    def __str__(self):
        if self.parent:
            return f"{self.get_category_type_display()} / {self.parent.name} / {self.name}"
        return f"{self.get_category_type_display()} / {self.name}"

    def clean(self):
        errors = {}
        if self.parent:
            if self.parent.category_type != self.category_type:
                errors["parent"] = "La subcategoría debe ser del mismo tipo que su padre."
            if self.parent_id == self.pk:
                errors["parent"] = "Una categoría no puede ser su propio padre."
        if errors:
            raise ValidationError(errors)


class SLAConfig(ModelApi):
    """
    Configuración de tiempos de respuesta/resolución por cliente/proyecto/categoría/prioridad.
    Si un campo es null, significa 'aplica a todos'.
    """

    PRIORITY_CHOICES = [
        ("BAJA", "Baja"),
        ("MEDIA", "Media"),
        ("ALTA", "Alta"),
        ("CRITICA", "Crítica"),
    ]

    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name="Cliente",
        help_text="Si se deja vacío, aplica a todos los clientes.",
    )
    project = models.ForeignKey(
        ProjectCatchments,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name="Proyecto",
        help_text="Si se deja vacío, aplica a todos los proyectos del cliente.",
    )
    category = models.ForeignKey(
        "core.TicketCategory",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sla_configs",
        verbose_name="Categoría",
        help_text="Si se deja vacío, aplica a todas las categorías.",
    )
    priority = models.CharField(
        max_length=20,
        choices=PRIORITY_CHOICES,
        null=True,
        blank=True,
        verbose_name="Prioridad",
        help_text="Si se deja vacío, aplica a todas las prioridades.",
    )
    response_time_hours = models.IntegerField(
        default=4,
        verbose_name="Tiempo de respuesta (horas)",
        help_text="Horas máximas para dar primera respuesta al ticket.",
    )
    resolution_time_hours = models.IntegerField(
        default=24,
        verbose_name="Tiempo de resolución (horas)",
        help_text="Horas máximas para resolver el ticket.",
    )
    business_hours_only = models.BooleanField(
        default=False,
        verbose_name="Solo horario hábil",
        help_text="Si es True, el SLA solo corre en días hábiles (L-V 9:00-18:00).",
    )
    escalation_user = models.ForeignKey(
        "core.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Usuario de escalamiento",
        help_text="A quién notificar si se vence el SLA.",
    )
    webhook_url = models.URLField(
        blank=True,
        null=True,
        verbose_name="Webhook SLA",
        help_text="URL que recibe un POST JSON cuando el SLA de un ticket con esta configuración vence. Si está vacío, se usa settings.SLA_OVERDUE_WEBHOOK_URL si existe.",
    )
    is_active = models.BooleanField(default=True, verbose_name="Activo")

    class Meta:
        verbose_name = "Configuración SLA"
        verbose_name_plural = "Configuraciones SLA"
        # Evitar duplicados exactos
        unique_together = [
            ["client", "project", "category", "priority"],
        ]

    def __str__(self):
        parts = []
        if self.client:
            parts.append(f"Cliente:{self.client.name}")
        if self.project:
            parts.append(f"Proy:{self.project.name}")
        if self.category:
            parts.append(f"Cat:{self.category}")
        if self.priority:
            parts.append(f"Pri:{self.priority}")
        scope = " | ".join(parts) if parts else "Global"
        return f"[{scope}] Resp:{self.response_time_hours}h / Resol:{self.resolution_time_hours}h"


class SupportTicket(ModelApi):
    """
    Ticket de soporte técnico. Vinculado a uno o varios puntos de captación.
    """

    STATUS_CHOICES = [
        ("ABIERTO", "Abierto"),
        ("EN_ANALISIS", "En análisis"),
        ("EN_ORDEN_TRABAJO", "En orden de trabajo"),
        ("ESPERA_CLIENTE", "Espera cliente"),
        ("ESPERA_PROVEEDOR", "Espera proveedor"),
        ("RESUELTO", "Resuelto"),
        ("CERRADO", "Cerrado"),
        ("CANCELADO", "Cancelado"),
    ]

    PRIORITY_CHOICES = [
        ("BAJA", "Baja"),
        ("MEDIA", "Media"),
        ("ALTA", "Alta"),
        ("CRITICA", "Crítica"),
    ]

    SOURCE_CHOICES = [
        ("APP_CLIENTE", "App Cliente"),
        ("APP_ADMIN", "App Admin"),
        ("ALERTA_AUTO", "Alerta automática"),
        ("SISTEMA", "Sistema"),
        ("CORREO", "Correo"),
        ("TELEFONO", "Teléfono"),
    ]

    ORIGIN_CHOICES = [
        ("CLIENTE", "Cliente"),
        ("INTERNO", "Interno"),
        ("OPERACIONES", "Operaciones"),
    ]

    points = models.ManyToManyField(
        CatchmentPoint,
        related_name="support_tickets",
        verbose_name="Puntos de captación",
    )

    title = models.CharField(max_length=300, verbose_name="Título")
    description = models.TextField(verbose_name="Descripción")

    created_by = models.ForeignKey(
        "core.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_tickets",
        verbose_name="Creado por",
    )
    assigned_to = models.ForeignKey(
        "core.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_tickets",
        verbose_name="Asignado a",
    )

    status = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        default="ABIERTO",
        verbose_name="Estado",
        db_index=True,
    )
    priority = models.CharField(
        max_length=20,
        choices=PRIORITY_CHOICES,
        default="MEDIA",
        verbose_name="Prioridad",
        db_index=True,
    )
    category = models.ForeignKey(
        "core.TicketCategory",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tickets",
        verbose_name="Categoría",
    )
    work_order_category = models.ForeignKey(
        "core.TicketCategory",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="work_order_tickets",
        verbose_name="Categoría de orden de trabajo",
        help_text=(
            "Subcategoría de tipo WORK_ORDER que describe la orden de trabajo. "
            "Solo aplica mientras el ticket está en estado EN_ORDEN_TRABAJO; la "
            "categoría original del ticket se mantiene intacta."
        ),
    )
    source = models.CharField(
        max_length=30,
        choices=SOURCE_CHOICES,
        default="APP_CLIENTE",
        verbose_name="Origen/Canal",
    )
    origin = models.CharField(
        max_length=20,
        choices=ORIGIN_CHOICES,
        default="CLIENTE",
        verbose_name="Origen (cliente/interno)",
        db_index=True,
    )

    # Vinculación con subsistemas existentes
    alert_trigger = models.ForeignKey(
        "core.AlertTrigger",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="support_tickets",
        verbose_name="Alerta relacionada",
    )
    system_event = models.ForeignKey(
        "core.SystemEvent",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="support_tickets",
        verbose_name="Evento de sistema relacionado",
    )

    # SLA
    sla_config = models.ForeignKey(
        SLAConfig,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Configuración SLA aplicada",
    )
    sla_deadline_response = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Límite primera respuesta",
    )
    sla_deadline_resolution = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Límite resolución",
    )
    sla_responded_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Primera respuesta dada",
    )
    sla_resolved_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Resuelto según SLA",
    )
    sla_last_overdue_notification = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Última notificación de SLA vencido",
        help_text="Se usa para evitar enviar spam de recordatorios.",
    )

    sla_paused_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="SLA pausado en",
        help_text=(
            "Marca cuándo se pausó el SLA (estados de espera). Mientras está "
            "seteado el reloj del SLA no corre; al salir del estado de espera "
            "los plazos se desplazan por el tiempo pausado y este campo se limpia."
        ),
    )

    resolved_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Fecha de resolución",
    )
    closed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Fecha de cierre",
    )

    scheduled_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Fecha planificada",
        help_text="Fecha de visita o ejecución planificada por operaciones.",
    )
    scheduled_date_confirmed = models.BooleanField(
        default=False,
        verbose_name="Fecha planificada confirmada",
        help_text="Indica si la fecha planificada fue confirmada por el involucrado.",
    )
    scheduled_date_confirmed_by = models.ForeignKey(
        "core.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="confirmed_ticket_schedules",
        verbose_name="Fecha confirmada por",
        help_text="Usuario que confirmó la fecha planificada.",
    )
    scheduled_date_confirmed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Fecha confirmada en",
        help_text="Cuándo se confirmó la fecha planificada.",
    )
    scheduled_date_cancelled = models.BooleanField(
        default=False,
        verbose_name="Fecha planificada cancelada",
        help_text="Indica si la fecha planificada fue cancelada y queda a la espera de re-agendar.",
    )
    scheduled_date_cancelled_by = models.ForeignKey(
        "core.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cancelled_ticket_schedules",
        verbose_name="Fecha cancelada por",
        help_text="Usuario que canceló la fecha planificada.",
    )
    scheduled_date_cancelled_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Fecha cancelada en",
        help_text="Cuándo se canceló la fecha planificada.",
    )
    scheduled_date_cancelled_reason = models.TextField(
        null=True,
        blank=True,
        verbose_name="Motivo de cancelación",
        help_text="Motivo por el que se canceló la fecha planificada.",
    )
    visit_report = models.TextField(
        null=True,
        blank=True,
        verbose_name="Informe de visita",
        help_text="Reporte técnico posterior a la visita/ejecución.",
    )

    is_active = models.BooleanField(default=True, verbose_name="Activo", db_index=True)

    class Meta:
        verbose_name = "Ticket de soporte"
        verbose_name_plural = "Tickets de soporte"
        ordering = ["-created"]
        indexes = [
            models.Index(fields=["assigned_to", "status", "is_active"]),
            models.Index(fields=["origin", "status", "is_active"]),
            models.Index(fields=["category", "status", "is_active"]),
        ]

    def __str__(self):
        return f"#{self.id} {self.title} ({self.get_status_display()})"

    def clean(self):
        # Mantener consistencia entre estado y timestamps.
        # Si el estado ya no justifica el timestamp, se limpia para evitar
        # errores de validación que no se pueden mostrar en formularios que
        # no incluyen esos campos (ej. Django admin con campos read-only).
        if self.status not in ("RESUELTO", "CERRADO", "CANCELADO"):
            self.resolved_at = None
        if self.status != "CERRADO":
            self.closed_at = None

        # La categoría de OT solo aplica mientras el ticket está en orden de
        # trabajo; en cualquier otro estado se limpia.
        if self.status != "EN_ORDEN_TRABAJO":
            self.work_order_category = None
        elif not self.work_order_category:
            raise ValidationError(
                {"work_order_category": "Debe seleccionar una categoría de orden de trabajo."}
            )
        elif self.work_order_category.category_type != "WORK_ORDER":
            raise ValidationError(
                {"work_order_category": "La categoría de OT debe ser de tipo WORK_ORDER."}
            )
        elif self.work_order_category.parent is None:
            raise ValidationError(
                {"work_order_category": "Debe ser una subcategoría de orden de trabajo."}
            )


class SupportTicketTask(ModelApi):
    """
    Tarea dentro de un ticket de soporte.

    Registra la etapa (created_stage) en que se creó la tarea: es un snapshot
    del estado del ticket en el momento de la creación. Si el ticket cambia de
    estado después, la tarea conserva la etapa original.
    """

    STATUS_CHOICES = [
        ("PENDIENTE", "Pendiente"),
        ("EN_PROGRESO", "En progreso"),
        ("COMPLETADA", "Completada"),
        ("CANCELADA", "Cancelada"),
    ]

    PRIORITY_CHOICES = SupportTicket.PRIORITY_CHOICES

    ticket = models.ForeignKey(
        SupportTicket,
        on_delete=models.CASCADE,
        related_name="tasks",
        verbose_name="Ticket",
    )
    title = models.CharField(max_length=300, verbose_name="Título")
    description = models.TextField(
        null=True,
        blank=True,
        verbose_name="Descripción",
    )
    status = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        default="PENDIENTE",
        verbose_name="Estado",
        db_index=True,
    )
    priority = models.CharField(
        max_length=20,
        choices=PRIORITY_CHOICES,
        default="MEDIA",
        verbose_name="Prioridad",
        db_index=True,
    )
    assigned_to = models.ForeignKey(
        "core.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_ticket_tasks",
        verbose_name="Asignado a",
    )
    due_date = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Fecha límite",
    )
    created_stage = models.CharField(
        max_length=30,
        choices=SupportTicket.STATUS_CHOICES,
        verbose_name="Etapa de creación",
        help_text="Estado del ticket cuando se creó la tarea (snapshot automático).",
    )
    created_by = models.ForeignKey(
        "core.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_ticket_tasks",
        verbose_name="Creado por",
    )

    class Meta:
        verbose_name = "Tarea de ticket"
        verbose_name_plural = "Tareas de tickets"
        ordering = ["-created"]
        indexes = [
            models.Index(fields=["ticket", "status"]),
            models.Index(fields=["assigned_to", "status"]),
        ]

    def __str__(self):
        return f"#{self.id} {self.title} ({self.get_status_display()})"


class TicketComment(ModelApi):
    """
    Comentario dentro de un ticket. Puede ser nota interna (no visible al cliente).
    """

    ticket = models.ForeignKey(
        SupportTicket,
        on_delete=models.CASCADE,
        related_name="comments",
        verbose_name="Ticket",
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="replies",
        verbose_name="Comentario padre",
        help_text="Si es una respuesta a otro comentario, referencia al comentario original (hilos).",
    )
    author = models.ForeignKey(
        "core.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ticket_comments",
        verbose_name="Autor",
    )
    content = models.TextField(verbose_name="Contenido")
    is_internal = models.BooleanField(
        default=False,
        verbose_name="Nota interna",
        help_text="Si es True, el cliente no ve este comentario.",
    )
    status_change = models.CharField(
        max_length=30,
        blank=True,
        null=True,
        verbose_name="Cambio de estado",
        help_text="Si este comentario cambió el estado del ticket, registra el nuevo estado.",
    )

    class Meta:
        verbose_name = "Comentario de ticket"
        verbose_name_plural = "Comentarios de tickets"
        ordering = ["created"]

    def __str__(self):
        prefix = "[INT] " if self.is_internal else ""
        return f"{prefix}Comentario #{self.id} en Ticket {self.ticket_id}"


class TicketCommentLike(ModelApi):
    """
    "Me gusta" de un usuario a un comentario de ticket.
    """

    comment = models.ForeignKey(
        TicketComment,
        on_delete=models.CASCADE,
        related_name="likes",
        verbose_name="Comentario",
    )
    user = models.ForeignKey(
        "core.User",
        on_delete=models.CASCADE,
        related_name="ticket_comment_likes",
        verbose_name="Usuario",
    )

    class Meta:
        verbose_name = "Me gusta de comentario"
        verbose_name_plural = "Me gusta de comentarios"
        constraints = [
            models.UniqueConstraint(
                fields=["comment", "user"],
                name="unique_ticket_comment_like",
            )
        ]

    def __str__(self):
        return f"Like de {self.user_id} al comentario #{self.comment_id}"


class TicketAttachment(ModelApi):
    """
    Archivo adjunto a un ticket o a un comentario.
    """

    ticket = models.ForeignKey(
        SupportTicket,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="attachments",
        verbose_name="Ticket",
    )
    comment = models.ForeignKey(
        TicketComment,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="attachments",
        verbose_name="Comentario",
    )
    task = models.ForeignKey(
        SupportTicketTask,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="attachments",
        verbose_name="Tarea",
    )
    file = models.FileField(
        upload_to="tickets/%Y/%m/",
        verbose_name="Archivo",
    )
    original_name = models.CharField(
        max_length=300,
        blank=True,
        verbose_name="Nombre original",
    )
    uploaded_by = models.ForeignKey(
        "core.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Subido por",
    )

    class Meta:
        verbose_name = "Adjunto de ticket"
        verbose_name_plural = "Adjuntos de tickets"

    def clean(self):
        super().clean()
        # Cada archivo debe estar ligado a un comentario o a una tarea
        # (los adjuntos a nivel ticket legacy conviven pero no son el foco).
        if self.comment and self.task:
            raise ValidationError(
                "Un adjunto no puede pertenecer a un comentario y a una tarea a la vez."
            )

    def __str__(self):
        return f"Adjunto {self.original_name or self.file.name}"


class TicketActivityLog(ModelApi):
    """
    Auditoría de cambios en un ticket.
    """

    ticket = models.ForeignKey(
        SupportTicket,
        on_delete=models.CASCADE,
        related_name="activity_logs",
        verbose_name="Ticket",
    )
    user = models.ForeignKey(
        "core.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Usuario",
    )
    field_name = models.CharField(max_length=100, verbose_name="Campo modificado")
    old_value = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        verbose_name="Valor anterior",
    )
    new_value = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        verbose_name="Valor nuevo",
    )

    class Meta:
        verbose_name = "Log de actividad"
        verbose_name_plural = "Logs de actividad"
        ordering = ["-created"]

    def __str__(self):
        return f"[{self.ticket_id}] {self.field_name}: {self.old_value} → {self.new_value}"


class TicketNotification(ModelApi):
    """
    Notificaciones in-app del subsistema de tickets (p. ej. menciones en comentarios).
    Se expone vía API bajo /api/ik/tickets/notifications/.
    """

    MENTION = "MENTION"
    REFERENCE = "REFERENCE"
    TYPE_CHOICES = [
        (MENTION, "Mención en comentario"),
        (REFERENCE, "Referencia a otro ticket"),
    ]

    notification_type = models.CharField(
        max_length=30,
        choices=TYPE_CHOICES,
        default=MENTION,
        verbose_name="Tipo",
    )
    user = models.ForeignKey(
        "core.User",
        on_delete=models.CASCADE,
        related_name="ticket_notifications",
        verbose_name="Usuario",
    )
    ticket = models.ForeignKey(
        SupportTicket,
        on_delete=models.CASCADE,
        related_name="notifications",
        verbose_name="Ticket",
    )
    comment = models.ForeignKey(
        TicketComment,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="notifications",
        verbose_name="Comentario",
    )
    message = models.CharField(max_length=500, verbose_name="Mensaje")
    is_read = models.BooleanField(default=False, verbose_name="Leída")

    class Meta:
        verbose_name = "Notificación de ticket"
        verbose_name_plural = "Notificaciones de tickets"
        ordering = ["-created"]
        indexes = [
            models.Index(fields=["user", "is_read"], name="ik_tktnotif_user_read_idx"),
        ]

    def __str__(self):
        return f"[{self.get_notification_type_display()}] para {self.user_id} en Ticket {self.ticket_id}"
