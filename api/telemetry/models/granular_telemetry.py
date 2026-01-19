"""Modelos Mejorados para Almacenamiento Granular de Datos de Telemetría."""

import uuid
from django.db import models
from django.core.validators import MaxValueValidator, MinValueValidator
from django.utils import timezone

from api.telemetry.models.catchment_points import CatchmentPoint
from api.infrastructure.models import Device
from api.core.models.users import User
from api.core.models.utils import ModelApi


class DataStream(ModelApi):
    """
    Stream de datos - Define qué tipo de datos se esperan de cada dispositivo.
    """

    name = models.CharField(
        max_length=100, help_text="Nombre descriptivo del stream de datos"
    )
    code = models.CharField(
        max_length=50, unique=True, help_text="Código único del stream"
    )
    description = models.TextField(
        blank=True, help_text="Descripción detallada del stream"
    )

    device = models.ForeignKey(
        Device,
        on_delete=models.CASCADE,
        related_name="data_streams",
        help_text="Dispositivo que genera este stream",
    )

    STREAM_TYPES = [
        ("TELEMETRY", "Telemetría"),
        ("DIAGNOSTIC", "Diagnóstico"),
        ("EVENT", "Evento"),
        ("COMMAND_RESPONSE", "Respuesta a Comando"),
        ("CONFIGURATION", "Configuración"),
        ("MAINTENANCE", "Mantenimiento"),
    ]

    stream_type = models.CharField(
        max_length=20,
        choices=STREAM_TYPES,
        default="TELEMETRY",
        help_text="Tipo de stream de datos",
    )

    is_active = models.BooleanField(default=True, help_text="Stream activo")
    sampling_rate_seconds = models.PositiveIntegerField(
        default=60, help_text="Frecuencia de muestreo en segundos"
    )
    retention_days = models.PositiveIntegerField(
        default=90, help_text="Días de retención de datos"
    )

    validation_rules = models.JSONField(
        default=dict, help_text="Reglas de validación para los datos"
    )
    transformations = models.JSONField(
        default=dict, help_text="Transformaciones aplicadas a los datos"
    )

    class Meta:
        db_table = "core_datastream"
        verbose_name = "Stream de Datos"
        verbose_name_plural = "Streams de Datos"
        unique_together = ["device", "code"]

    def __str__(self):
        return f"{self.device.name} - {self.name}"


class DataPoint(ModelApi):
    """
    Punto de dato granular.
    """

    data_point_id = models.UUIDField(
        default=uuid.uuid4, unique=True, help_text="ID único global del punto de dato"
    )
    stream = models.ForeignKey(
        DataStream,
        on_delete=models.CASCADE,
        related_name="data_points",
    )

    collected_at = models.DateTimeField()
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    DATA_QUALITY_CHOICES = [
        ("EXCELLENT", "Excelente"),
        ("GOOD", "Buena"),
        ("FAIR", "Regular"),
        ("POOR", "Mala"),
        ("INVALID", "Inválida"),
    ]

    quality = models.CharField(
        max_length=10,
        choices=DATA_QUALITY_CHOICES,
        default="GOOD",
    )

    raw_value = models.TextField()
    processed_value = models.DecimalField(
        max_digits=20,
        decimal_places=6,
        null=True,
        blank=True,
    )

    unit = models.CharField(max_length=20, blank=True)
    metadata = models.JSONField(default=dict)
    is_valid = models.BooleanField(default=True)
    is_processed = models.BooleanField(default=False)

    device = models.ForeignKey(
        Device,
        on_delete=models.CASCADE,
        related_name="granular_data_points",
    )

    point = models.ForeignKey(
        CatchmentPoint,
        on_delete=models.CASCADE,
        related_name="granular_data_points",
    )

    class Meta:
        db_table = "core_datapoint"
        verbose_name = "Punto de Dato"
        verbose_name_plural = "Puntos de Datos"
        unique_together = ["stream", "collected_at"]
        ordering = ["-collected_at"]

    def __str__(self):
        return f"{self.stream.name}: {self.raw_value} ({self.collected_at})"


class VariableDefinition(ModelApi):
    """
    Definición granular de variables.
    """

    name = models.CharField(max_length=100)
    code = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)

    variable_type = models.CharField(
        max_length=10,
        choices=[
            ("NUMERIC", "Numérica"),
            ("TEXT", "Texto"),
            ("BOOLEAN", "Booleana"),
            ("JSON", "JSON"),
            ("BINARY", "Binaria"),
        ],
        default="NUMERIC",
    )

    unit = models.CharField(max_length=20, blank=True)
    conversion_factor = models.DecimalField(max_digits=10, decimal_places=6, default=1.0)
    conversion_offset = models.DecimalField(max_digits=10, decimal_places=6, default=0.0)

    streams = models.ManyToManyField(
        DataStream,
        related_name="variable_definitions",
    )

    class Meta:
        db_table = "core_variabledefinition"
        verbose_name = "Definición de Variable"
        verbose_name_plural = "Definiciones de Variables"

    def __str__(self):
        return f"{self.name} ({self.code})"


class DataAggregation(ModelApi):
    """
    Agregaciones pre-calculadas para consultas rápidas.
    """

    point = models.ForeignKey(
        CatchmentPoint,
        on_delete=models.CASCADE,
        related_name="data_aggregations",
    )
    variable_definition = models.ForeignKey(
        VariableDefinition,
        on_delete=models.CASCADE,
        related_name="aggregations",
    )

    period = models.CharField(
        max_length=10,
        choices=[
            ("HOURLY", "Por hora"),
            ("DAILY", "Diario"),
            ("WEEKLY", "Semanal"),
            ("MONTHLY", "Mensual"),
        ],
    )

    period_start = models.DateTimeField()
    period_end = models.DateTimeField()

    count = models.PositiveIntegerField()
    avg_value = models.DecimalField(max_digits=15, decimal_places=6, null=True, blank=True)
    min_value = models.DecimalField(max_digits=15, decimal_places=6, null=True, blank=True)
    max_value = models.DecimalField(max_digits=15, decimal_places=6, null=True, blank=True)
    sum_value = models.DecimalField(max_digits=20, decimal_places=6, null=True, blank=True)

    data_quality = models.DecimalField(
        max_digits=5, decimal_places=4, validators=[MinValueValidator(0), MaxValueValidator(1)]
    )

    class Meta:
        db_table = "core_dataaggregation"
        verbose_name = "Agregación de Datos"
        verbose_name_plural = "Agregaciones de Datos"
        unique_together = ["point", "variable_definition", "period", "period_start"]

    def __str__(self):
        return f"{self.point.title} - {self.variable_definition.name}"
