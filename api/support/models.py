"""
Modelos para la Gestión de Tickets de Soporte
"""

import uuid
from datetime import timedelta

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import JSONField
from django.utils import timezone

# Importaciones de otras apps
from api.core.models.users import User
from api.core.models.utils import ModelApi
from api.telemetry.models.catchment_points import CatchmentPoint
from api.telemetry.models.management_super import IoTDevice


class SupportTicket(ModelApi):
    """
    Sistema completo de tickets de soporte
    """

    ticket_number = models.CharField(
        max_length=20, unique=True, help_text="Número único del ticket (auto-generado)"
    )

    title = models.CharField(max_length=200, help_text="Título descriptivo del ticket")

    description = models.TextField(help_text="Descripción detallada del problema")

    # Estado del ticket
    TICKET_STATUS = [
        ("OPEN", "Abierto"),
        ("IN_PROGRESS", "En Progreso"),
        ("WAITING_CUSTOMER", "Esperando Cliente"),
        ("WAITING_SUPPLIER", "Esperando Proveedor"),
        ("RESOLVED", "Resuelto"),
        ("CLOSED", "Cerrado"),
    ]

    status = models.CharField(
        max_length=20,
        choices=TICKET_STATUS,
        default="OPEN",
        help_text="Estado actual del ticket",
    )

    # Prioridad
    PRIORITY_LEVELS = [
        ("LOW", "Baja"),
        ("NORMAL", "Normal"),
        ("HIGH", "Alta"),
        ("CRITICAL", "Crítica"),
        ("EMERGENCY", "Emergencia"),
    ]

    priority = models.CharField(
        max_length=10,
        choices=PRIORITY_LEVELS,
        default="NORMAL",
        help_text="Prioridad del ticket",
    )

    # Categorización
    TICKET_CATEGORIES = [
        ("TECHNICAL", "Técnico"),
        ("FUNCTIONAL", "Funcional"),
        ("PERFORMANCE", "Performance"),
        ("SECURITY", "Seguridad"),
        ("DATA_QUALITY", "Calidad de Datos"),
        ("HARDWARE", "Hardware"),
        ("SOFTWARE", "Software"),
        ("NETWORK", "Red"),
        ("MAINTENANCE", "Mantenimiento"),
        ("OTHER", "Otro"),
    ]

    category = models.CharField(
        max_length=15,
        choices=TICKET_CATEGORIES,
        default="TECHNICAL",
        help_text="Categoría del ticket",
    )

    # Usuarios involucrados
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="created_tickets",
        help_text="Usuario que creó el ticket",
        null=True,
        blank=True,
    )

    assigned_to = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_tickets",
        help_text="Usuario asignado al ticket",
    )

    # Recursos afectados
    affected_devices = models.ManyToManyField(
        IoTDevice,
        related_name="support_tickets",
        blank=True,
        help_text="Dispositivos afectados",
    )

    affected_points = models.ManyToManyField(
        CatchmentPoint,
        related_name="support_tickets",
        blank=True,
        help_text="Puntos de captación afectados",
    )

    # Fechas importantes
    opened_at = models.DateTimeField(
        auto_now_add=True, help_text="Fecha de apertura del ticket"
    )

    due_date = models.DateTimeField(
        null=True, blank=True, help_text="Fecha límite para resolución"
    )

    resolved_at = models.DateTimeField(
        null=True, blank=True, help_text="Fecha de resolución"
    )

    closed_at = models.DateTimeField(null=True, blank=True, help_text="Fecha de cierre")

    # Métricas de resolución
    resolution_time_hours = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Tiempo de resolución en horas",
    )

    customer_satisfaction = models.PositiveIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text="Satisfacción del cliente (1-5)",
    )

    # Información adicional
    tags = models.JSONField(
        default=list,
        blank=True,
        help_text="Tags para categorización adicional",
    )

    attachments = JSONField(
        default=dict, help_text="Archivos adjuntos (URLs, paths, etc.)"
    )

    custom_fields = JSONField(
        default=dict, help_text="Campos personalizados según categoría"
    )

    class Meta:
        verbose_name = "Ticket de Soporte"
        verbose_name_plural = "Tickets de Soporte"
        indexes = [
            models.Index(fields=["ticket_number"]),
            models.Index(fields=["status", "priority"]),
            models.Index(fields=["category", "status"]),
            models.Index(fields=["created_by", "status"]),
            models.Index(fields=["assigned_to", "status"]),
            models.Index(fields=["opened_at"]),
            models.Index(fields=["due_date"]),
        ]
        ordering = ["-opened_at"]

    def __str__(self):
        return f"#{self.ticket_number} - {self.title}"

    def save(self, *args, **kwargs):
        # Auto-generate ticket number
        if not self.ticket_number:
            self.ticket_number = self._generate_ticket_number()

        # Calculate resolution time when resolved
        if self.status == "RESOLVED" and not self.resolved_at:
            self.resolved_at = timezone.now()
            if self.opened_at:
                delta = self.resolved_at - self.opened_at
                self.resolution_time_hours = delta.total_seconds() / 3600

        # Set closed timestamp
        if self.status == "CLOSED" and not self.closed_at:
            self.closed_at = timezone.now()

        super().save(*args, **kwargs)

    def _generate_ticket_number(self) -> str:
        """Genera número único de ticket"""
        import random
        import string

        # Formato: SUP-YYYY-NNNNN (ej: SUP-2024-00001)
        year = timezone.now().year
        random_part = "".join(random.choices(string.digits, k=5))
        return f"SUP-{year}-{random_part}"

    @property
    def is_overdue(self) -> bool:
        """Verifica si el ticket está vencido"""
        if not self.due_date:
            return False
        return timezone.now() > self.due_date

    @property
    def days_open(self) -> int:
        """Días que el ticket lleva abierto"""
        if self.status == "CLOSED" and self.closed_at:
            delta = self.closed_at - self.opened_at
        else:
            delta = timezone.now() - self.opened_at
        return delta.days

    def add_comment(self, user: User, comment: str, is_internal: bool = False):
        """Agrega un comentario al ticket"""
        return TicketComment.objects.create(
            ticket=self, author=user, comment=comment, is_internal=is_internal
        )

    def assign_to(self, user: User):
        """Asigna el ticket a un usuario"""
        self.assigned_to = user
        self.status = "IN_PROGRESS"
        self.save()

        # Crear comentario automático
        self.add_comment(
            user, f"Ticket asignado a {user.get_full_name()}", is_internal=True
        )

    def resolve(self, user: User, resolution_notes: str = ""):
        """Resuelve el ticket"""
        self.status = "RESOLVED"
        self.resolved_at = timezone.now()
        self.save()

        # Crear comentario automático si hay notas
        if resolution_notes:
            self.add_comment(user, f"Ticket resuelto: {resolution_notes}", is_internal=True)


class TicketComment(ModelApi):
    """
    Comentarios y actualizaciones en tickets de soporte
    """

    ticket = models.ForeignKey(
        SupportTicket,
        on_delete=models.CASCADE,
        related_name="comments",
        help_text="Ticket al que pertenece el comentario",
    )

    author = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="ticket_comments",
        help_text="Autor del comentario",
    )

    comment = models.TextField(help_text="Contenido del comentario")

    is_internal = models.BooleanField(
        default=False, help_text="Comentario interno (solo visible para staff)"
    )

    # Metadata
    attachments = JSONField(default=dict, help_text="Archivos adjuntos al comentario")

    mentioned_users = models.ManyToManyField(
        User,
        related_name="mentioned_in_comments",
        blank=True,
        help_text="Usuarios mencionados en el comentario",
    )

    class Meta:
        verbose_name = "Comentario de Ticket"
        verbose_name_plural = "Comentarios de Tickets"
        indexes = [
            models.Index(fields=["ticket", "created"]),
            models.Index(fields=["author", "created"]),
            models.Index(fields=["is_internal"]),
        ]
        ordering = ["created"]

    def __str__(self):
        return (
            f"Comment by {self.author.get_full_name()} on #{self.ticket.ticket_number}"
        )


class TicketSLA(ModelApi):
    """
    Definición de SLA (Service Level Agreement) para tickets
    """

    name = models.CharField(max_length=100, help_text="Nombre del SLA")

    category = models.CharField(
        max_length=15,
        choices=SupportTicket.TICKET_CATEGORIES,
        help_text="Categoría de tickets a la que aplica",
    )

    priority = models.CharField(
        max_length=10,
        choices=SupportTicket.PRIORITY_LEVELS,
        help_text="Prioridad de tickets a la que aplica",
    )

    # Tiempos de respuesta
    response_time_hours = models.PositiveIntegerField(
        help_text="Tiempo máximo de respuesta inicial en horas"
    )

    resolution_time_hours = models.PositiveIntegerField(
        help_text="Tiempo máximo de resolución en horas"
    )

    # Penalizaciones por incumplimiento
    penalty_per_hour = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=0,
        help_text="Penalización por hora de retraso",
    )

    # Configuración
    is_active = models.BooleanField(default=True, help_text="SLA activo")

    business_hours_only = models.BooleanField(
        default=True, help_text="Solo contar horas hábiles"
    )

    class Meta:
        verbose_name = "SLA de Tickets"
        verbose_name_plural = "SLAs de Tickets"
        indexes = [
            models.Index(fields=["category", "priority", "is_active"]),
        ]
        unique_together = ["category", "priority"]

    def __str__(self):
        return f"{self.name} ({self.category} - {self.priority})"