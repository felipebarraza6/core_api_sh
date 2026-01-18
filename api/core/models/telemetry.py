from django.contrib.postgres.indexes import GinIndex
from django.db import models

from .catchment_points import CatchmentPoint
from .utils import ModelApi


class TelemetryScheme(ModelApi):
    """Reusable processing scheme for multiple points."""

    name = models.CharField(max_length=200, verbose_name="Nombre del Esquema")
    description = models.TextField(blank=True, verbose_name="Descripción")

    class Meta:
        db_table = "core_telemetryscheme"
        verbose_name = "Esquema de Telemetría"
        verbose_name_plural = "Esquemas de Telemetría"

    def __str__(self):
        return self.name


class SchemeVariable(ModelApi):
    """Template variable within a scheme."""

    scheme = models.ForeignKey(
        TelemetryScheme, related_name="variables", on_delete=models.CASCADE
    )
    name = models.CharField(max_length=200, verbose_name="Nombre")
    internal_code = models.CharField(max_length=100, verbose_name="Código Interno")
    unit = models.CharField(max_length=50, blank=True, null=True, verbose_name="Unidad")

    VARIABLE_TYPES = [
        ("TOTALIZADO", "Totalizado (Pulsos)"),
        ("NIVEL", "Nivel Freático"),
        ("CAUDAL", "Caudal Instantáneo"),
        ("CAUDAL_PROMEDIO", "Caudal Promedio"),
        ("GENERIC", "Genérico / Directo"),
    ]
    type_variable = models.CharField(
        max_length=50,
        choices=VARIABLE_TYPES,
        default="GENERIC",
        verbose_name="Tipo de Procesamiento",
    )

    provider_key = models.CharField(
        max_length=100, blank=True, null=True, verbose_name="Key Proveedor"
    )
    scale_factor = models.FloatField(default=1.0, verbose_name="Factor Escala")
    offset = models.FloatField(default=0.0, verbose_name="Offset")

    # Campos de operaciones dinámicas (consistentes con CoreVariable)
    OPERATIONS = [
        ("PHYSICAL", "Dato Físico (Sensor)"),
        ("SUM", "Suma"),
        ("DIFF", "Resta (A - B)"),
        ("MUL", "Multiplicación"),
        ("AVG", "Promedio"),
        ("FORMULA", "Fórmula Personalizada"),
    ]
    operation = models.CharField(
        max_length=20,
        choices=OPERATIONS,
        default="PHYSICAL",
        verbose_name="Tipo de Operación",
    )
    formula = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        verbose_name="Fórmula",
        help_text="Ej: ({var1} + {var2}) * 0.5. Use los internal_codes entre llaves.",
    )
    sources = models.JSONField(
        default=list,
        blank=True,
        help_text="Lista de internal_codes de origen para operaciones",
        verbose_name="Variables de Origen",
    )
    priority = models.IntegerField(
        default=0,
        verbose_name="Prioridad de Cálculo",
        help_text="Menor valor se calcula antes.",
    )
    is_virtual = models.BooleanField(
        default=False,
        verbose_name="Es Virtual",
        help_text="Indica si la variable es calculada internamente.",
    )

    # Validaciones de rango
    min_value = models.FloatField(
        blank=True,
        null=True,
        verbose_name="Valor Mínimo",
        help_text="Si el dato es menor a este valor, se ignorará.",
    )
    max_value = models.FloatField(
        blank=True,
        null=True,
        verbose_name="Valor Máximo",
        help_text="Si el dato es mayor a este valor, se ignorará.",
    )

    configuration = models.JSONField(
        default=dict,
        blank=True,
        help_text="Configuración específica (ej: pulses_factor, d3, etc.)",
        verbose_name="Configuración Extra",
    )
    is_active = models.BooleanField(default=True, verbose_name="Activo")

    class Meta:
        db_table = "core_schemevariable"
        verbose_name = "Variable de Esquema"
        verbose_name_plural = "Variables de Esquema"
        unique_together = ("scheme", "internal_code")

    def __str__(self):
        return f"{self.scheme.name} - {self.name}"


class VirtualVariable(ModelApi):
    """Calculated variable based on other variables in the scheme."""

    scheme = models.ForeignKey(
        TelemetryScheme, related_name="virtual_variables", on_delete=models.CASCADE
    )
    name = models.CharField(max_length=200, verbose_name="Nombre")
    internal_code = models.CharField(max_length=100, verbose_name="Código Interno")
    unit = models.CharField(max_length=50, blank=True, null=True, verbose_name="Unidad")

    OPERATIONS = [
        ("SUM", "Suma"),
        ("DIFF", "Resta (A - B)"),
        ("MUL", "Multiplicación"),
        ("AVG", "Promedio"),
        ("FORMULA", "Fórmula Personalizada"),
    ]
    operation = models.CharField(
        max_length=20, choices=OPERATIONS, verbose_name="Operación"
    )

    formula = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        verbose_name="Fórmula",
        help_text="Ej: ({var1} + {var2}) * 0.5. Use los códigos entre llaves.",
    )

    sources = models.JSONField(
        default=list,
        blank=True,
        help_text="Lista de internal_codes de origen",
        verbose_name="Variables de Origen",
    )

    priority = models.IntegerField(
        default=0,
        verbose_name="Prioridad de Cálculo",
        help_text="Menor valor se calcula antes.",
    )

    is_active = models.BooleanField(default=True, verbose_name="Activo")

    class Meta:
        db_table = "core_virtualvariable"
        verbose_name = "Variable Virtual"
        verbose_name_plural = "Variables Virtuales"
        unique_together = ("scheme", "internal_code")

    def __str__(self):
        return f"{self.scheme.name} - {self.name} (Virtual)"


class CoreVariable(ModelApi):
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
        null=True,
    )
    unit = models.CharField(max_length=50, verbose_name="Unidad", blank=True, null=True)

    # Reusing choices for consistency
    type_variable = models.CharField(
        max_length=50,
        choices=SchemeVariable.VARIABLE_TYPES,
        default="GENERIC",
        verbose_name="Tipo de Procesamiento",
    )

    # Configuration for ingestion
    provider_key = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name="Key en JSON del proveedor",
    )
    scale_factor = models.FloatField(default=1.0, verbose_name="Factor de escala")
    offset = models.FloatField(default=0.0, verbose_name="Offset / Calibración")

    # Dynamic Processing & Virtual Features
    OPERATIONS = [
        ("PHYSICAL", "Dato Físico (Sensor)"),
        ("SUM", "Suma"),
        ("DIFF", "Resta (A - B)"),
        ("MUL", "Multiplicación"),
        ("AVG", "Promedio"),
        ("FORMULA", "Fórmula Personalizada"),
    ]
    operation = models.CharField(
        max_length=20,
        choices=OPERATIONS,
        default="PHYSICAL",
        verbose_name="Tipo de Operación",
    )
    formula = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        verbose_name="Fórmula",
        help_text="Ej: ({var1} + {var2}) * 0.5. Use los internal_codes entre llaves.",
    )
    sources = models.JSONField(
        default=list,
        blank=True,
        help_text="Lista de internal_codes de origen",
        verbose_name="Variables de Origen",
    )
    priority = models.IntegerField(
        default=0,
        verbose_name="Prioridad de Cálculo",
        help_text="Menor valor se calcula antes.",
    )
    is_virtual = models.BooleanField(
        default=False,
        verbose_name="Es Virtual",
        help_text="Indica si la variable es calculada internamente.",
    )

    # Validations
    min_value = models.FloatField(
        blank=True,
        null=True,
        verbose_name="Valor Mínimo",
        help_text="Si el dato es menor a este valor, se ignorará.",
    )
    max_value = models.FloatField(
        blank=True,
        null=True,
        verbose_name="Valor Máximo",
        help_text="Si el dato es mayor a este valor, se ignorará.",
    )

    configuration = models.JSONField(
        default=dict,
        blank=True,
        help_text="Configuración específica (ej: pulses_factor, d3, etc.)",
        verbose_name="Configuración Extra",
    )

    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "core_variable"
        verbose_name = "Variable"
        verbose_name_plural = "Variables"
        unique_together = ("point", "internal_code")

    def clean(self):
        import re

        from django.core.exceptions import ValidationError

        super().clean()

        if self.operation == "FORMULA":
            if not self.formula:
                raise ValidationError(
                    {"formula": "La fórmula es requerida para esta operación."}
                )

            # Reemplazar tokens {var} por un número seguro para validar sintaxis
            processed = re.sub(r"\{[a-zA-Z0-9_]+\}", "1", self.formula)

            # Validar whitelist de caracteres
            if not re.match(r"^[0-9\.\+\-\*\/\(\)\s]+$", processed):
                raise ValidationError(
                    {
                        "formula": (
                            "La fórmula contiene caracteres no permitidos. "
                            "Solo se permiten números, operadores y {variables}."
                        )
                    }
                )

            # Validar sintaxis (balance de paréntesis, etc.)
            try:
                eval(processed, {"__builtins__": {}})
            except SyntaxError:
                raise ValidationError({"formula": "Error de sintaxis en la fórmula."})
            except Exception:
                # Otros errores runtime (ej. division por zero) no invalidan la sintaxis
                pass

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
        db_table = "core_telemetryrecord"
        verbose_name = "Registro Telemetría"
        verbose_name_plural = "Registros Telemetría"
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["point", "-timestamp"]),
            GinIndex(fields=["data"]),
        ]

    def __str__(self):
        return f"{self.point.title} @ {self.timestamp}"
