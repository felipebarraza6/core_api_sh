"""Notification and alert models for void."""
from django.db import models

from void.models.base import VoidModel


class Notification(VoidModel):
    """Notificación genérica para clientes, usuarios o dispositivos."""

    CHANNEL_CHOICES = [
        ("email", "Email"),
        ("sms", "SMS"),
        ("whatsapp", "WhatsApp"),
        ("push", "Push"),
        ("in_app", "In-app"),
    ]

    STATUS_CHOICES = [
        ("pending", "Pendiente"),
        ("sent", "Enviada"),
        ("failed", "Fallida"),
        ("read", "Leída"),
    ]

    CATEGORY_CHOICES = [
        ("subscription_reminder", "Recordatorio de suscripción"),
        ("invoice_reminder", "Recordatorio de factura"),
        ("invoice_overdue", "Factura vencida"),
        ("sla_alert", "Alerta SLA"),
        ("device_offline", "Dispositivo offline"),
        ("system", "Sistema"),
    ]

    recipient_email = models.EmailField(
        verbose_name="Email destinatario",
    )
    recipient_name = models.CharField(
        max_length=300,
        blank=True,
        default="",
        verbose_name="Nombre destinatario",
    )
    category = models.CharField(
        max_length=40,
        choices=CATEGORY_CHOICES,
        verbose_name="Categoría",
        db_index=True,
    )
    channel = models.CharField(
        max_length=20,
        choices=CHANNEL_CHOICES,
        default="email",
        verbose_name="Canal",
    )
    subject = models.CharField(
        max_length=500,
        verbose_name="Asunto",
    )
    body = models.TextField(
        verbose_name="Cuerpo",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
        verbose_name="Estado",
        db_index=True,
    )
    sent_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name="Enviada el",
    )
    error_message = models.CharField(
        max_length=500,
        blank=True,
        default="",
        verbose_name="Error de envío",
    )

    # Referencias opcionales
    contract = models.ForeignKey(
        "Contract",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="notifications",
        verbose_name="Contrato",
    )
    client = models.ForeignKey(
        "Client",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="notifications",
        verbose_name="Cliente",
    )
    reference_id = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="ID de referencia",
        help_text="Clave única para evitar duplicados de la misma notificación.",
        db_index=True,
    )

    class Meta:
        verbose_name = "Notificación"
        verbose_name_plural = "Notificaciones"
        ordering = ["-created"]
        indexes = [
            models.Index(fields=["status", "category"]),
            models.Index(fields=["recipient_email", "status"]),
        ]

    def __str__(self):
        return f"{self.category} → {self.recipient_email} ({self.status})"
