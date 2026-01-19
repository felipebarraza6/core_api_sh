"""Modelos para la Gestión de Tickets de Soporte."""

import uuid
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

# Importaciones de otras apps
from api.core.models.users import User
from api.core.models.utils import ModelApi
from api.telemetry.models.catchment_points import CatchmentPoint
from api.infrastructure.models import Device


class SupportTicket(ModelApi):
    """Sistema completo de tickets de soporte."""

    ticket_number = models.CharField(
        max_length=20, unique=True, help_text="Número único del ticket (auto-generado)"
    )
    title = models.CharField(max_length=200, help_text="Título descriptivo del ticket")
    description = models.TextField(help_text="Descripción detallada del problema")

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

    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="created_tickets",
        null=True,
        blank=True,
    )

    assigned_to = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_tickets",
    )

    affected_devices = models.ManyToManyField(
        Device,
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

    opened_at = models.DateTimeField(auto_now_add=True)
    due_date = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    resolution_time_hours = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
    )

    customer_satisfaction = models.PositiveIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )

    tags = models.JSONField(default=list, blank=True)
    attachments = models.JSONField(default=dict)
    custom_fields = models.JSONField(default=dict)

    class Meta:
        db_table = "core_supportticket"
        verbose_name = "Ticket de Soporte"
        verbose_name_plural = "Tickets de Soporte"
        ordering = ["-opened_at"]

    def __str__(self):
        return f"#{self.ticket_number} - {self.title}"

    def save(self, *args, **kwargs):
        if not self.ticket_number:
            self.ticket_number = self._generate_ticket_number()

        if self.status == "RESOLVED" and not self.resolved_at:
            self.resolved_at = timezone.now()
            if self.opened_at:
                delta = self.resolved_at - self.opened_at
                self.resolution_time_hours = delta.total_seconds() / 3600

        if self.status == "CLOSED" and not self.closed_at:
            self.closed_at = timezone.now()

        super().save(*args, **kwargs)

    def _generate_ticket_number(self) -> str:
        import random
        import string
        year = timezone.now().year
        random_part = "".join(random.choices(string.digits, k=5))
        return f"SUP-{year}-{random_part}"


class TicketComment(ModelApi):
    """Comentarios y actualizaciones en tickets de soporte."""

    ticket = models.ForeignKey(
        SupportTicket,
        on_delete=models.CASCADE,
        related_name="comments",
    )
    author = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="ticket_comments",
    )
    comment = models.TextField()
    is_internal = models.BooleanField(default=False)
    attachments = models.JSONField(default=dict)
    mentioned_users = models.ManyToManyField(
        User,
        related_name="mentioned_in_comments",
        blank=True,
    )

    class Meta:
        db_table = "core_ticketcomment"
        verbose_name = "Comentario de Ticket"
        verbose_name_plural = "Comentarios de Tickets"
        ordering = ["created"]

    def __str__(self):
        return f"Comment by {self.author.username} on #{self.ticket.ticket_number}"


class TicketSLA(ModelApi):
    """Definición de SLA (Service Level Agreement) para tickets."""

    name = models.CharField(max_length=100)
    category = models.CharField(
        max_length=15,
        choices=SupportTicket.TICKET_CATEGORIES,
    )
    priority = models.CharField(
        max_length=10,
        choices=SupportTicket.PRIORITY_LEVELS,
    )
    response_time_hours = models.PositiveIntegerField()
    resolution_time_hours = models.PositiveIntegerField()
    penalty_per_hour = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
    business_hours_only = models.BooleanField(default=True)

    class Meta:
        db_table = "core_ticketsla"
        verbose_name = "SLA de Tickets"
        verbose_name_plural = "SLAs de Tickets"
        unique_together = ["category", "priority"]

    def __str__(self):
        return f"{self.name} ({self.category} - {self.priority})"