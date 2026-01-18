from django.db import models

from .catchment_points import CatchmentPoint
from .utils import ModelApi


class Variable(ModelApi):
    """Modern Dynamic Variable Model."""

    point = models.ForeignKey(
        CatchmentPoint,
        related_name="variables",
        on_delete=models.CASCADE,
        verbose_name="Punto de captación",
    )
    name = models.CharField(max_length=200, verbose_name="Nombre para mostrar")
    internal_code = models.CharField(
        max_length=100,
        verbose_name="Código interno / Sensor ID",
        blank=True,
        null=True
    )
    unit = models.CharField(max_length=50, verbose_name="Unidad", blank=True, null=True)

    # Configuration for ingestion
    provider_key = models.CharField(
        max_length=100, blank=True, null=True, verbose_name="Key en JSON del proveedor"
    )
    scale_factor = models.FloatField(default=1.0, verbose_name="Factor de escala")
    offset = models.FloatField(default=0.0, verbose_name="Offset / Calibración")

    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "core_variablev3"
        verbose_name = "Variable"
        verbose_name_plural = "Variables"
        unique_together = ("point", "internal_code")

    def __str__(self):
        return f"{self.point.title} - {self.name}"


class TelemetryRecord(ModelApi):
    """Modern Dynamic Telemetry Record."""

    point = models.ForeignKey(
        CatchmentPoint, related_name="telemetry", on_delete=models.CASCADE
    )
    timestamp = models.DateTimeField(db_index=True)
    data = models.JSONField(
        default=dict, help_text="Valores dinámicos: {'code': value}"
    )
    metadata = models.JSONField(
        default=dict, blank=True, help_text="Metadata del proveedor"
    )

    # DGA and Status fields (promoted from metadata for performance)
    send_dga = models.BooleanField(default=False, db_index=True)
    n_voucher = models.CharField(max_length=200, blank=True, null=True, db_index=True)
    return_dga = models.TextField(blank=True, null=True)

    is_error = models.BooleanField(default=False, db_index=True)
    is_partial = models.BooleanField(default=False, db_index=True)

    @property
    def flow(self):
        """Dynamic access to flow/caudal from data JSON."""
        return self.data.get("flow", self.data.get("caudal", 0))

    @property
    def total(self):
        """Dynamic access to total from data JSON."""
        return self.data.get("total", 0)

    @property
    def nivel(self):
        """Dynamic access to nivel from data JSON."""
        return self.data.get("nivel", 0)

    @property
    def water_table(self):
        """Dynamic access to water_table from data JSON."""
        return self.data.get("water_table", 0)

    @property
    def pulses(self):
        """Dynamic access to pulses from data JSON."""
        return self.data.get("pulses", 0)

    @property
    def total_diff(self):
        """Dynamic access to total_diff from data JSON."""
        return self.data.get("total_diff", 0)

    @property
    def total_today_diff(self):
        """Dynamic access to total_today_diff from data JSON."""
        return self.data.get("total_today_diff", 0)

    @property
    def date_time_last_logger(self):
        """Dynamic access to last_logger_timestamp from metadata JSON."""
        val = self.metadata.get("last_logger_timestamp")
        if val and isinstance(val, str):
            from django.utils.dateparse import parse_datetime

            return parse_datetime(val)
        return val

    @property
    def days_not_conection(self):
        val = self.metadata.get(
            "days_not_conection", self.metadata.get("days_not_connection", 0)
        )
        try:
            return int(val or 0)
        except (TypeError, ValueError):
            return 0

    @property
    def variable_details(self):
        val = self.metadata.get("variable_details")
        return val if isinstance(val, list) else []

    class Meta:
        db_table = "core_telemetryrecordv3"
        verbose_name = "Registro Telemetría"
        verbose_name_plural = "Registros Telemetría"
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["point", "-timestamp"]),
        ]

    def __str__(self):
        return f"{self.point.title} @ {self.timestamp}"
