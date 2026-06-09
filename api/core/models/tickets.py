"""
Subsistema de Tickets de Soporte + SLA.

Módulo completamente nuevo; no toca legacy (NotificationsCatchment).
Se expone vía API bajo /api/ik/tickets/.
"""

from django.core.exceptions import ValidationError
from django.db import models

from .catchment_points import CatchmentPoint, Client, ProjectCatchments
from .utils import ModelApi


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

    CATEGORY_CHOICES = [
        ("SOFTWARE", "Software"),
        ("HARDWARE", "Hardware"),
        ("CONECTIVIDAD", "Conectividad"),
        ("DGA", "DGA"),
        ("TELEMETRIA", "Telemetría"),
        ("OT", "Orden de Trabajo"),
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
    category = models.CharField(
        max_length=50,
        choices=CATEGORY_CHOICES,
        null=True,
        blank=True,
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
    Ticket de soporte técnico. Siempre vinculado a un punto de captación.
    """

    STATUS_CHOICES = [
        ("ABIERTO", "Abierto"),
        ("EN_ANALISIS", "En análisis"),
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

    CATEGORY_CHOICES = [
        ("SOFTWARE", "Software"),
        ("HARDWARE", "Hardware"),
        ("CONECTIVIDAD", "Conectividad"),
        ("DGA", "DGA"),
        ("TELEMETRIA", "Telemetría"),
        ("OT", "Orden de Trabajo"),
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
    ]

    point_catchment = models.ForeignKey(
        CatchmentPoint,
        on_delete=models.CASCADE,
        related_name="support_tickets",
        verbose_name="Punto de captación",
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
    category = models.CharField(
        max_length=30,
        choices=CATEGORY_CHOICES,
        default="TELEMETRIA",
        verbose_name="Categoría",
        db_index=True,
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

    is_active = models.BooleanField(default=True, verbose_name="Activo", db_index=True)

    class Meta:
        verbose_name = "Ticket de soporte"
        verbose_name_plural = "Tickets de soporte"
        ordering = ["-created"]
        indexes = [
            models.Index(fields=["point_catchment", "status", "is_active"]),
            models.Index(fields=["assigned_to", "status", "is_active"]),
            models.Index(fields=["origin", "status", "is_active"]),
            models.Index(fields=["category", "status", "is_active"]),
        ]

    def __str__(self):
        return f"#{self.id} {self.title} ({self.get_status_display()})"

    def clean(self):
        errors = {}
        if self.resolved_at and self.status not in ("RESUELTO", "CERRADO", "CANCELADO"):
            errors["resolved_at"] = "No puede tener fecha de resolución si el estado no es Resuelto/Cerrado/Cancelado."
        if self.closed_at and self.status != "CERRADO":
            errors["closed_at"] = "No puede tener fecha de cierre si el estado no es Cerrado."
        if errors:
            raise ValidationError(errors)


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
