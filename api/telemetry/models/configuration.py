"""
Modelos de Configuración Dinámica para Telemetría

Incluye:
- ConfigurationScheme: Esquemas reutilizables de configuración
- ConfigurationSchemeField: Campos dentro de los esquemas
- PointConfigurationValue: Valores de configuración por punto
- SamplingFrequency: Frecuencias de muestreo dinámicas
- VariableType: Tipos de variables configurables
"""

from django.db import models
from django.core.exceptions import ValidationError

from api.core.models.utils import ModelApi
from .catchment_points import CatchmentPoint


class ConfigurationScheme(ModelApi):
    """
    Esquema reutilizable de configuración para puntos.
    Similar a TelemetryScheme pero para datos estáticos del pozo/sensor.
    
    Ejemplo: "Pozo Subterráneo Estándar" con campos d1, d2, d3, pulses_factor
    """
    
    name = models.CharField(
        max_length=200,
        verbose_name="Nombre del Esquema"
    )
    code = models.CharField(
        max_length=50,
        unique=True,
        verbose_name="Código",
        help_text="Identificador único del esquema (ej: 'pozo_std')"
    )
    description = models.TextField(
        blank=True,
        verbose_name="Descripción"
    )
    
    # Organización
    category = models.CharField(
        max_length=100,
        default='general',
        verbose_name="Categoría",
        help_text="Ej: 'pozo', 'sensor', 'superficial'"
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Activo"
    )
    
    class Meta:
        db_table = "telemetry_configurationscheme"
        verbose_name = "Esquema de Configuración"
        verbose_name_plural = "Esquemas de Configuración"
        ordering = ['category', 'name']
    
    def __str__(self):
        return self.name
    
    def clean(self):
        """Validar que el código sea válido."""
        if not self.code:
            raise ValidationError("El código es requerido")
        if not self.code.replace('_', '').isalnum():
            raise ValidationError("El código solo puede contener letras, números y guiones bajos")


class ConfigurationSchemeField(ModelApi):
    """
    Campo dentro de un esquema de configuración.
    Define la estructura: qué campos existen, su tipo, validaciones, etc.
    """
    
    scheme = models.ForeignKey(
        ConfigurationScheme,
        related_name='fields',
        on_delete=models.CASCADE,
        verbose_name="Esquema"
    )
    
    code = models.CharField(
        max_length=50,
        verbose_name="Código del Campo",
        help_text="Identificador único dentro del esquema (ej: 'd3', 'pulses_factor')"
    )
    name = models.CharField(
        max_length=200,
        verbose_name="Nombre para Mostrar"
    )
    description = models.TextField(
        blank=True,
        verbose_name="Descripción"
    )
    
    DATA_TYPES = [
        ('decimal', 'Decimal'),
        ('integer', 'Entero'),
        ('text', 'Texto'),
        ('boolean', 'Booleano'),
    ]
    data_type = models.CharField(
        max_length=20,
        choices=DATA_TYPES,
        default='decimal',
        verbose_name="Tipo de Dato"
    )
    unit = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Unidad",
        help_text="Ej: 'mt', 'pulsos/m3', 'L/s'"
    )
    default_value = models.JSONField(
        null=True,
        blank=True,
        verbose_name="Valor por Defecto"
    )
    
    # Validaciones
    min_value = models.DecimalField(
        null=True,
        blank=True,
        max_digits=15,
        decimal_places=6,
        verbose_name="Valor Mínimo"
    )
    max_value = models.DecimalField(
        null=True,
        blank=True,
        max_digits=15,
        decimal_places=6,
        verbose_name="Valor Máximo"
    )
    is_required = models.BooleanField(
        default=False,
        verbose_name="Requerido"
    )
    
    # Presentación
    display_order = models.IntegerField(
        default=0,
        verbose_name="Orden de Visualización"
    )
    help_text = models.CharField(
        max_length=500,
        blank=True,
        verbose_name="Texto de Ayuda"
    )
    
    # Para fórmulas: indica si este campo puede usarse como {config.code}
    is_formula_accessible = models.BooleanField(
        default=True,
        verbose_name="Accesible en Fórmulas",
        help_text="Si está marcado, puede usarse en fórmulas como {config.code}"
    )
    
    class Meta:
        db_table = "telemetry_configurationschemefield"
        verbose_name = "Campo de Esquema"
        verbose_name_plural = "Campos de Esquema"
        unique_together = ('scheme', 'code')
        ordering = ['display_order', 'code']
    
    def __str__(self):
        return f"{self.scheme.name} - {self.name}"


class PointConfigurationValue(ModelApi):
    """
    Valor de configuración para un punto específico.
    El punto tiene un esquema asignado, y aquí se guardan los valores de cada campo.
    """
    
    point = models.ForeignKey(
        CatchmentPoint,
        related_name='configuration_values',
        on_delete=models.CASCADE,
        verbose_name="Punto de Captación"
    )
    field = models.ForeignKey(
        ConfigurationSchemeField,
        on_delete=models.CASCADE,
        verbose_name="Campo"
    )
    value = models.JSONField(
        verbose_name="Valor",
        help_text="Almacena el valor según el tipo de dato del campo"
    )
    
    class Meta:
        db_table = "telemetry_pointconfigurationvalue"
        verbose_name = "Valor de Configuración"
        verbose_name_plural = "Valores de Configuración"
        unique_together = ('point', 'field')
        indexes = [
            models.Index(fields=['point', 'field']),
        ]
    
    def __str__(self):
        return f"{self.point.title} - {self.field.code}: {self.value}"
    
    def clean(self):
        """Validar que el valor coincida con el tipo de dato del campo."""
        field = self.field
        val = self.value
        
        if field.data_type == 'decimal':
            try:
                float(val)
            except (ValueError, TypeError):
                raise ValidationError(f"El valor debe ser un número decimal para el campo {field.code}")
        
        elif field.data_type == 'integer':
            try:
                int(val)
            except (ValueError, TypeError):
                raise ValidationError(f"El valor debe ser un número entero para el campo {field.code}")
        
        elif field.data_type == 'boolean':
            if not isinstance(val, bool):
                raise ValidationError(f"El valor debe ser booleano para el campo {field.code}")
        
        # Validar rangos
        if field.min_value is not None or field.max_value is not None:
            try:
                num_val = float(val)
                if field.min_value is not None and num_val < float(field.min_value):
                    raise ValidationError(f"El valor debe ser >= {field.min_value}")
                if field.max_value is not None and num_val > float(field.max_value):
                    raise ValidationError(f"El valor debe ser <= {field.max_value}")
            except (ValueError, TypeError):
                pass  # Ya se validó arriba


class SamplingFrequency(ModelApi):
    """
    Frecuencias de muestreo disponibles.
    Reemplaza las opciones hardcodeadas FRECUENCY_OPTIONS.
    """
    
    code = models.CharField(
        max_length=20,
        unique=True,
        verbose_name="Código",
        help_text="Identificador único (ej: '1', '5', '60')"
    )
    name = models.CharField(
        max_length=100,
        verbose_name="Nombre",
        help_text="Ej: '1 minuto', '5 minutos', '1 hora'"
    )
    minutes = models.IntegerField(
        verbose_name="Minutos",
        help_text="Valor en minutos"
    )
    
    # Configuración Celery Beat
    cron_expression = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Expresión Cron",
        help_text="Ej: '*/5 * * * *' para cada 5 minutos"
    )
    
    is_active = models.BooleanField(
        default=True,
        verbose_name="Activo"
    )
    display_order = models.IntegerField(
        default=0,
        verbose_name="Orden de Visualización"
    )
    
    class Meta:
        db_table = "telemetry_samplingfrequency"
        verbose_name = "Frecuencia de Muestreo"
        verbose_name_plural = "Frecuencias de Muestreo"
        ordering = ['display_order', 'minutes']
    
    def __str__(self):
        return self.name
    
    def clean(self):
        """Validar que los minutos sean positivos."""
        if self.minutes <= 0:
            raise ValidationError("Los minutos deben ser mayores a 0")
        
        # Generar cron expression si no está definida
        if not self.cron_expression and self.minutes:
            if self.minutes == 1:
                self.cron_expression = "* * * * *"
            elif self.minutes < 60:
                self.cron_expression = f"*/{self.minutes} * * * *"
            elif self.minutes == 60:
                self.cron_expression = "0 * * * *"
            else:
                # Para frecuencias mayores, usar horas
                hours = self.minutes // 60
                self.cron_expression = f"0 */{hours} * * *"


class VariableType(ModelApi):
    """
    Tipos de variables disponibles.
    Reemplaza las opciones hardcodeadas VARIABLE_TYPES.
    """
    
    code = models.CharField(
        max_length=50,
        unique=True,
        verbose_name="Código",
        help_text="Identificador único (ej: 'TOTALIZADO', 'NIVEL', 'CAUDAL')"
    )
    name = models.CharField(
        max_length=200,
        verbose_name="Nombre"
    )
    description = models.TextField(
        blank=True,
        verbose_name="Descripción"
    )
    
    # Procesamiento por defecto (puede ser overrideado por CoreVariable.formula)
    default_formula = models.CharField(
        max_length=1000,
        blank=True,
        verbose_name="Fórmula por Defecto",
        help_text="Fórmula que se usa si CoreVariable no tiene una propia"
    )
    
    # Variables requeridas para este tipo
    required_inputs = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Inputs Requeridos",
        help_text="Lista de variables que deben existir (ej: ['pulses', 'factor'])"
    )
    
    # Unidad de salida por defecto
    default_unit = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Unidad por Defecto",
        help_text="Ej: 'm3', 'L/s', 'mt'"
    )
    
    is_active = models.BooleanField(
        default=True,
        verbose_name="Activo"
    )
    
    class Meta:
        db_table = "telemetry_variabletype"
        verbose_name = "Tipo de Variable"
        verbose_name_plural = "Tipos de Variable"
        ordering = ['code']
    
    def __str__(self):
        return f"{self.name} ({self.code})"
    
    def clean(self):
        """Validar que el código sea válido."""
        if not self.code:
            raise ValidationError("El código es requerido")
        if not self.code.replace('_', '').isalnum():
            raise ValidationError("El código solo puede contener letras, números y guiones bajos")
