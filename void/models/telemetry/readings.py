"""Raw telemetry readings for void."""
from django.db import models

from void.models.base import VoidModel


class RawReading(VoidModel):
    """Lectura cruda recibida desde un proveedor de telemetría."""

    VARIABLE_CHOICES = [
        ("pulses", "Pulsos"),
        ("total", "Total acumulado"),
        ("flow", "Caudal"),
        ("nivel", "Nivel"),
        ("water_table", "Nivel freático"),
        ("battery", "Batería"),
        ("signal", "Señal"),
        ("temperature", "Temperatura"),
        ("other", "Otro"),
    ]

    device = models.ForeignKey(
        "void.Device",
        on_delete=models.CASCADE,
        related_name="raw_readings",
        verbose_name="Dispositivo",
    )
    source_variable = models.CharField(
        max_length=80,
        blank=True,
        default="",
        verbose_name="Variable del logger",
        help_text="Nombre original enviado por el proveedor/logger.",
        db_index=True,
    )
    variable = models.CharField(
        max_length=40,
        choices=VARIABLE_CHOICES,
        verbose_name="Variable interna",
        help_text="Tipo genérico dentro del sistema.",
        db_index=True,
    )
    timestamp = models.DateTimeField(
        verbose_name="Timestamp del logger",
        db_index=True,
    )
    received_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Recibido en",
    )
    raw_value = models.CharField(
        max_length=400,
        verbose_name="Valor crudo",
        help_text="Valor original como string para preservar precisión del proveedor.",
    )
    unit = models.CharField(
        max_length=50,
        blank=True,
        default="",
        verbose_name="Unidad",
    )
    provider_payload = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Payload del proveedor",
        help_text="Fragmento reducido del payload original para trazabilidad.",
    )
    ingest_task_id = models.CharField(
        max_length=200,
        blank=True,
        default="",
        verbose_name="Task ID de ingesta",
    )
    is_valid = models.BooleanField(
        default=True,
        verbose_name="Válido",
        help_text="False si falló validación básica de formato.",
    )
    validation_error = models.CharField(
        max_length=500,
        blank=True,
        default="",
        verbose_name="Error de validación",
    )

    class Meta:
        verbose_name = "Lectura cruda (void)"
        verbose_name_plural = "Lecturas crudas (void)"
        indexes = [
            models.Index(fields=["device", "source_variable", "timestamp"]),
            models.Index(fields=["device", "variable", "timestamp"]),
            models.Index(fields=["device", "timestamp"]),
            models.Index(fields=["timestamp", "is_valid"]),
        ]
        ordering = ["-timestamp"]

    def save(self, *args, **kwargs):
        if not self.source_variable:
            self.source_variable = self.variable
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.device} | {self.source_variable}={self.raw_value} @ {self.timestamp}"
