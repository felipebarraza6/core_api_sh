"""Sistema Avanzado de Constantes Históricas."""

from django.db import models
from api.telemetry.models.catchment_points import CatchmentPoint
from api.infrastructure.models import Device
from api.core.models.users import User
from api.core.models.utils import ModelApi


class ConstantDefinition(ModelApi):
    """Definición de constantes aplicables por rangos de tiempo."""

    name = models.CharField(max_length=100)
    code = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)

    device = models.ForeignKey(
        Device,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="constants",
    )

    point = models.ForeignKey(
        CatchmentPoint,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="constants",
    )

    CONSTANT_TYPES = [
        ("TOTALIZER_OFFSET", "Offset de Totalizador"),
        ("FLOW_MULTIPLIER", "Multiplicador de Caudal"),
        ("LEVEL_OFFSET", "Offset de Nivel"),
        ("BATTERY_CALIBRATION", "Calibración de Batería"),
        ("CONVERSION_FACTOR", "Factor de Conversión"),
        ("CUSTOM", "Personalizada"),
    ]

    constant_type = models.CharField(
        max_length=20,
        choices=CONSTANT_TYPES,
        default="TOTALIZER_OFFSET",
    )

    value_numeric = models.DecimalField(max_digits=15, decimal_places=6)
    value_text = models.TextField(blank=True)
    unit = models.CharField(max_length=20, blank=True)
    is_active = models.BooleanField(default=True)
    priority = models.PositiveIntegerField(default=100)

    class Meta:
        db_table = "core_constantdefinition"
        verbose_name = "Definición de Constante"
        verbose_name_plural = "Definiciones de Constantes"

    def __str__(self):
        return f"{self.name} = {self.value_numeric}"


class ConstantApplication(ModelApi):
    """Aplicación temporal de constantes."""

    constant = models.ForeignKey(
        ConstantDefinition,
        on_delete=models.CASCADE,
        related_name="applications",
    )
    start_date = models.DateTimeField()
    end_date = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    change_reason = models.TextField()

    new_value = models.DecimalField(max_digits=15, decimal_places=6)

    class Meta:
        db_table = "core_constantapplication"
        verbose_name = "Aplicación de Constante"
        verbose_name_plural = "Aplicaciones de Constantes"

    def __str__(self):
        return f"{self.constant.name}"
