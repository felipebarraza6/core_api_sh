from django.db import models
from api.core.models.utils import ModelApi

class TelemetryMeasurement(ModelApi):
    """
    Individual measurement for a specific variable at a specific time.
    Standardizes storage for high-volume time-series data.
    """

    record = models.ForeignKey(
        "telemetry.TelemetryRecord",
        on_delete=models.CASCADE,
        related_name="measurements",
        verbose_name="Registro Origen"
    )
    
    variable = models.ForeignKey(
        "telemetry.CoreVariable",
        on_delete=models.PROTECT,
        related_name="measurements",
        verbose_name="Variable"
    )

    timestamp = models.DateTimeField(
        db_index=True,
        verbose_name="Timestamp Medición"
    )

    # Value stages
    raw_value = models.FloatField(
        null=True, blank=True,
        verbose_name="Valor Crudo"
    )
    processed_value = models.FloatField(
        null=True, blank=True,
        verbose_name="Valor Procesado (Fórmula)"
    )
    final_value = models.FloatField(
        verbose_name="Valor Final"
    )

    # Status & Metadata
    is_validated = models.BooleanField(
        default=False,
        verbose_name="Validado"
    )
    
    quality_code = models.CharField(
        max_length=50,
        default="RAW",
        verbose_name="Código de Calidad"
    )

    tags = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Etiquetas / Metadata",
        help_text="Metadatos extra: trigger_rule, is_interpolated, etc."
    )

    class Meta:
        db_table = "telemetry_measurement"
        verbose_name = "Medición de Telemetría"
        verbose_name_plural = "Mediciones de Telemetría"
        indexes = [
            models.Index(fields=["variable", "timestamp"]),
            models.Index(fields=["record", "variable"]),
        ]
        ordering = ["-timestamp"]

    def __str__(self):
        return f"{self.variable.internal_code} @ {self.timestamp}: {self.final_value}"
