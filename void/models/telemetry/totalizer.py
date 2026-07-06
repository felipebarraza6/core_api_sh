"""Auditoría de totalizadores para void.

El estado persistente del totalizador ahora vive en ``DeviceVariableState``
(JSON genérico) y es gestionado por ``StatefulRuleHandler``. Este archivo solo
conserva ``CounterResetLog`` como log de auditoría.
"""
from django.db import models

from void.models.base import VoidModel


class CounterResetLog(VoidModel):
    """Auditoría de resets de contador detectados por el pipeline."""

    RESET_TYPE_CHOICES = [
        ("ZERO_KEPT", "Reset a 0 - total preservado"),
        ("PARTIAL", "Reset parcial (0 < actual < anterior)"),
        ("PARTIAL_REJECTED", "Reset parcial rechazado (sin evidencia de desconexión)"),
        ("NOISE_DROP", "Caída de ruido (<1%)"),
        ("NEGATIVE_PULSES", "Pulsos negativos"),
        ("MASSIVE_JUMP_OK", "Salto masivo aceptado"),
    ]

    device = models.ForeignKey(
        "void.Device",
        on_delete=models.CASCADE,
        related_name="counter_reset_logs",
        verbose_name="Dispositivo",
    )
    variable = models.CharField(
        max_length=40,
        verbose_name="Variable",
    )
    timestamp = models.DateTimeField(
        verbose_name="Timestamp de la medición",
    )
    reset_type = models.CharField(
        max_length=30,
        choices=RESET_TYPE_CHOICES,
        verbose_name="Tipo de reset",
    )
    last_pulses = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        verbose_name="Pulsos anteriores",
    )
    current_pulses = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        verbose_name="Pulsos actuales",
    )
    pulses_factor = models.IntegerField(
        verbose_name="Factor de pulsos",
    )
    addition_before = models.DecimalField(
        max_digits=15,
        decimal_places=3,
        blank=True,
        null=True,
        verbose_name="Offset antes",
    )
    amount_to_add = models.DecimalField(
        max_digits=15,
        decimal_places=3,
        blank=True,
        null=True,
        verbose_name="Volumen compensado (m³)",
    )
    addition_after = models.DecimalField(
        max_digits=15,
        decimal_places=3,
        blank=True,
        null=True,
        verbose_name="Offset después",
    )
    total_before = models.DecimalField(
        max_digits=15,
        decimal_places=3,
        blank=True,
        null=True,
        verbose_name="Total anterior (m³)",
    )
    total_after = models.DecimalField(
        max_digits=15,
        decimal_places=3,
        blank=True,
        null=True,
        verbose_name="Total calculado (m³)",
    )
    is_reconnection = models.BooleanField(
        default=False,
        verbose_name="Detectado como reconexión",
    )
    time_diff_hours = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        verbose_name="Horas desde última medición",
    )
    days_not_connection = models.IntegerField(
        blank=True,
        null=True,
        verbose_name="Días sin conexión",
    )

    class Meta:
        verbose_name = "Log de reset de contador"
        verbose_name_plural = "Logs de resets de contadores"
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["device", "variable", "timestamp"]),
            models.Index(fields=["reset_type", "timestamp"]),
        ]

    def __str__(self):
        return f"{self.reset_type} {self.device} @ {self.timestamp}"
