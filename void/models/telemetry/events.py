"""Eventos de telemetría para void (resets, saltos, offline, etc.)."""
from django.db import models

from void.models.base import VoidModel


class DeviceEvent(VoidModel):
    """Evento discreto generado durante el procesamiento de telemetría.

    Equivalente a las notificaciones/alertas de legacy pero desacoplado del
    envío: primero se registra el hecho, después un dispatcher decide canales.
    """

    EVENT_TYPE_CHOICES = [
        ("counter_reset", "Reset de contador"),
        ("massive_jump", "Salto masivo de consumo"),
        ("negative_pulses", "Pulsos negativos"),
        ("zero_kept", "Pulsos cero con histórico"),
        ("partial_rejected", "Caída parcial rechazada"),
        ("noise_drop", "Caída de ruido"),
        ("device_offline", "Dispositivo offline"),
        ("device_reconnected", "Dispositivo reconectado"),
    ]

    SEVERITY_CHOICES = [
        ("info", "Info"),
        ("warning", "Advertencia"),
        ("critical", "Crítico"),
    ]

    device = models.ForeignKey(
        "void.Device",
        on_delete=models.CASCADE,
        related_name="events",
        verbose_name="Dispositivo",
    )
    variable = models.CharField(
        max_length=40,
        verbose_name="Variable",
    )
    event_type = models.CharField(
        max_length=30,
        choices=EVENT_TYPE_CHOICES,
        verbose_name="Tipo de evento",
        db_index=True,
    )
    severity = models.CharField(
        max_length=20,
        choices=SEVERITY_CHOICES,
        default="info",
        verbose_name="Severidad",
        db_index=True,
    )
    timestamp = models.DateTimeField(
        verbose_name="Timestamp de la medición",
        db_index=True,
    )
    message = models.TextField(
        blank=True,
        default="",
        verbose_name="Mensaje",
    )
    context = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Contexto",
        help_text="Datos técnicos del evento (pulsos, totales, offsets, etc.).",
    )
    is_dispatched = models.BooleanField(
        default=False,
        verbose_name="Notificado",
        help_text="True cuando ya se envió por los canales configurados.",
    )
    dispatched_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name="Notificado el",
    )

    class Meta:
        verbose_name = "Evento de dispositivo"
        verbose_name_plural = "Eventos de dispositivos"
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["device", "event_type", "timestamp"]),
            models.Index(fields=["severity", "is_dispatched"]),
        ]

    def __str__(self):
        return f"{self.event_type} {self.device} @ {self.timestamp}"
