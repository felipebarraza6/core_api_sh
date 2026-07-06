"""Motor de alertas para void.

Reglas configurables que evalúan DeviceEvent y generan AlertTrigger.
El dispatch de notificaciones es asíncrono vía Celery.
"""
from django.db import models

from void.models.base import VoidModel


class AlertRule(VoidModel):
    """Regla que decide si un DeviceEvent genera una alerta."""

    CHANNEL_CHOICES = [
        ("email", "Email"),
        ("sms", "SMS"),
        ("webhook", "Webhook"),
        ("push", "Push"),
        ("in_app", "In-app"),
    ]

    SEVERITY_CHOICES = [
        ("info", "Info"),
        ("warning", "Advertencia"),
        ("critical", "Crítico"),
    ]

    name = models.CharField(max_length=200, verbose_name="Nombre")
    is_active = models.BooleanField(default=True, verbose_name="Activo", db_index=True)

    # Filtros de matching.
    event_types = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Tipos de evento",
        help_text="Lista de códigos de DeviceEvent.event_type. Vacío = cualquiera.",
    )
    severities = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Severidades",
        help_text="Lista de severidades. Vacío = cualquiera.",
    )
    device_ids = models.JSONField(
        default=list,
        blank=True,
        verbose_name="IDs de dispositivos",
        help_text="Lista de IDs de device. Vacío = cualquiera.",
    )
    point_ids = models.JSONField(
        default=list,
        blank=True,
        verbose_name="IDs de puntos",
        help_text="Lista de IDs de point. Vacío = cualquiera.",
    )
    variables = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Variables",
        help_text="Lista de nombres de variable. Vacío = cualquiera.",
    )

    # Frecuencia: mínimo minutos entre alertas duplicadas para la misma regla/device/variable.
    cooldown_minutes = models.PositiveIntegerField(
        default=60,
        verbose_name="Cooldown (minutos)",
        help_text="No dispara si ya disparó para el mismo device/variable en este periodo.",
    )

    # Acción.
    channels = models.JSONField(
        default=list,
        verbose_name="Canales",
        help_text="Lista de canales a usar: email, sms, webhook, push, in_app.",
    )
    recipients = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Destinatarios",
        help_text=(
            "{"
            "'emails': ['a@x.com'], "
            "'phones': ['+569...'], "
            "'webhook_url': 'https://...', "
            "'user_ids': [1, 2]"
            "}"
        ),
    )
    message_template = models.TextField(
        blank=True,
        default="",
        verbose_name="Plantilla de mensaje",
        help_text="Soporta {event_type}, {device}, {variable}, {severity}, {message}, {timestamp}, {point}.",
    )

    class Meta:
        verbose_name = "Regla de alerta"
        verbose_name_plural = "Reglas de alerta"
        ordering = ["name"]

    def __str__(self):
        return self.name


class AlertTrigger(VoidModel):
    """Instancia concreta de alerta generada por una regla."""

    STATUS_CHOICES = [
        ("pending", "Pendiente"),
        ("dispatched", "Enviada"),
        ("failed", "Fallida"),
    ]

    rule = models.ForeignKey(
        AlertRule,
        on_delete=models.CASCADE,
        related_name="triggers",
        verbose_name="Regla",
    )
    event = models.ForeignKey(
        "void.DeviceEvent",
        on_delete=models.CASCADE,
        related_name="alert_triggers",
        verbose_name="Evento",
    )

    channels = models.JSONField(default=list, verbose_name="Canales")
    recipients = models.JSONField(default=dict, blank=True, verbose_name="Destinatarios")
    message = models.TextField(blank=True, default="", verbose_name="Mensaje renderizado")

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
        verbose_name="Estado",
        db_index=True,
    )
    dispatched_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name="Enviada el",
    )
    dispatch_result = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Resultado del envío",
    )

    class Meta:
        verbose_name = "Disparo de alerta"
        verbose_name_plural = "Disparos de alerta"
        ordering = ["-created"]
        indexes = [
            models.Index(fields=["rule", "event", "status"]),
            models.Index(fields=["status", "created"]),
        ]

    def __str__(self):
        return f"{self.rule} → {self.event} ({self.status})"
