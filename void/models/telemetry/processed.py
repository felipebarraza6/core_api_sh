"""Processed telemetry readings for void."""
from django.db import models

from void.models.base import VoidModel


class ProcessedReading(VoidModel):
    """Lectura procesada tras aplicar el esquema de procesamiento."""

    raw_reading = models.ForeignKey(
        "void.RawReading",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="processed",
        verbose_name="Lectura cruda origen",
    )
    device = models.ForeignKey(
        "void.Device",
        on_delete=models.CASCADE,
        related_name="processed_readings",
        verbose_name="Dispositivo",
    )
    variable = models.CharField(
        max_length=40,
        verbose_name="Variable",
        db_index=True,
    )
    timestamp = models.DateTimeField(
        verbose_name="Timestamp",
        db_index=True,
    )

    # Valores numéricos procesados
    pulses = models.IntegerField(
        blank=True,
        null=True,
        verbose_name="Pulsos",
    )
    total = models.DecimalField(
        max_digits=15,
        decimal_places=3,
        blank=True,
        null=True,
        verbose_name="Total (m³)",
    )
    flow = models.DecimalField(
        max_digits=15,
        decimal_places=3,
        blank=True,
        null=True,
        verbose_name="Caudal (l/s o m³/s según config)",
    )
    nivel = models.DecimalField(
        max_digits=15,
        decimal_places=3,
        blank=True,
        null=True,
        verbose_name="Nivel (m)",
    )
    water_table = models.DecimalField(
        max_digits=15,
        decimal_places=3,
        blank=True,
        null=True,
        verbose_name="Nivel freático (m)",
    )
    total_diff = models.DecimalField(
        max_digits=15,
        decimal_places=3,
        blank=True,
        null=True,
        verbose_name="Consumo en período (m³)",
    )
    total_today_diff = models.DecimalField(
        max_digits=15,
        decimal_places=3,
        blank=True,
        null=True,
        verbose_name="Consumo hoy (m³)",
    )
    extra_values = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Valores adicionales",
        help_text="Valores de variables dinámicas que no tienen campo propio.",
    )

    # Flags de procesamiento
    is_reset = models.BooleanField(
        default=False,
        verbose_name="Reset detectado",
    )
    is_reconnection = models.BooleanField(
        default=False,
        verbose_name="Reconexión",
    )
    is_interpolated = models.BooleanField(
        default=False,
        verbose_name="Interpolado",
    )
    is_error = models.BooleanField(
        default=False,
        verbose_name="Error",
    )
    error_message = models.CharField(
        max_length=500,
        blank=True,
        default="",
        verbose_name="Mensaje de error",
    )

    processing_schema = models.ForeignKey(
        "void.ProcessingSchema",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="processed_readings",
        verbose_name="Esquema de procesamiento",
    )
    processed_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Procesado el",
    )
    processor_version = models.CharField(
        max_length=50,
        blank=True,
        default="",
        verbose_name="Versión del procesador",
    )

    class Meta:
        verbose_name = "Lectura procesada (void)"
        verbose_name_plural = "Lecturas procesadas (void)"
        indexes = [
            models.Index(fields=["device", "variable", "timestamp"]),
            models.Index(fields=["device", "timestamp"]),
            models.Index(fields=["is_error", "timestamp"]),
        ]
        ordering = ["-timestamp"]
        unique_together = ("device", "variable", "timestamp")

    def __str__(self):
        return f"{self.device} | {self.variable} @ {self.timestamp}"
