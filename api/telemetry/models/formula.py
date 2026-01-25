
from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from api.core.models.utils import ModelApi


class TelemetryFormula(ModelApi):
    """
    Definición de una Fórmula Matemática reutilizable.
    Representa una expresión de cálculo pura, sin estado.
    
    Ejemplo:
    - Code: 'simple_mult'
    - Expression: '{value} * {factor}'
    """
    name = models.CharField(max_length=200, verbose_name="Nombre")
    code = models.SlugField(max_length=100, unique=True, verbose_name="Código Único")
    
    expression = models.TextField(
        verbose_name="Expresión Matemática",
        help_text="""
        Sintaxis soportada:
        - {value}: Valor crudo entrante
        - {config.x}: Valor de configuración
        - {prev.x}: Valor previo calculado
        - Operadores: +, -, *, /, (, )
        """
    )
    
    description = models.TextField(blank=True, verbose_name="Descripción")
    
    output_unit = models.CharField(
        max_length=50, 
        blank=True, 
        verbose_name="Unidad de Salida",
        help_text="Unidad resultante del cálculo (ej: m3, L/s)"
    )
    
    is_system = models.BooleanField(
        default=False,
        verbose_name="Es de Sistema",
        help_text="Si es True, no se puede eliminar ni modificar su código."
    )
    
    variables = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Variables Esperadas",
        help_text="Lista de tokens que esta fórmula espera (ej: ['value', 'factor'])"
    )
    
    class Meta:
        verbose_name = "Definición de Fórmula"
        verbose_name_plural = "Definiciones de Fórmulas"
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.code})"


class ProcessingRule(ModelApi):
    """
    Definición de una Regla de Procesamiento (Lógica/Comportamiento).
    Representa validaciones, detecciones de eventos o acciones condicionales.
    
    Ejemplo:
    - Name: 'Detección de Reinicio'
    - Type: 'RESET_DETECTOR'
    """
    name = models.CharField(max_length=200, verbose_name="Nombre")
    code = models.SlugField(max_length=100, unique=True, verbose_name="Código Único")
    
    RULE_TYPES = [
        ('PRE_CALC', 'Pre-Cálculo (Limpieza/Validación Raw)'),
        ('POST_CALC', 'Post-Cálculo (Validación Resultado/Eventos)'),
        ('RESET_DETECTOR', 'Detector de Reinicio (Lógica Especial)'),
        ('MAX_DIFF', 'Validación de Diferencia Máxima'),
        ('MIN_VALUE', 'Validación de Valor Mínimo'),
        ('MAX_VALUE', 'Validación de Valor Máximo'),
    ]
    rule_type = models.CharField(
        max_length=50,
        choices=RULE_TYPES,
        verbose_name="Tipo de Regla"
    )
    
    description = models.TextField(blank=True, verbose_name="Descripción")
    
    default_parameters = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Parámetros por Defecto",
        help_text="Parámetros base para la regla (ej: {'threshold': 500})"
    )
    
    is_system = models.BooleanField(
        default=False,
        verbose_name="Es de Sistema"
    )
    
    class Meta:
        verbose_name = "Regla de Procesamiento"
        verbose_name_plural = "Reglas de Procesamiento"
        ordering = ['rule_type', 'name']

    def __str__(self):
        return f"{self.name} ({self.rule_type})"


class FormulaAssignment(ModelApi):
    """
    Asignación Temporal de una Fórmula a una Variable.
    Permite definir qué fórmula aplica en qué rango de fechas.
    """
    variable = models.ForeignKey(
        'telemetry.CoreVariable',
        on_delete=models.CASCADE,
        related_name='formula_assignments',
        verbose_name="Variable"
    )
    
    formula = models.ForeignKey(
        TelemetryFormula,
        on_delete=models.PROTECT,
        verbose_name="Fórmula"
    )
    
    valid_from = models.DateTimeField(
        verbose_name="Válido Desde",
        default=timezone.now
    )
    
    valid_to = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Válido Hasta",
        help_text="Dejar vacío para vigencia indefinida"
    )
    
    priority = models.IntegerField(
        default=0,
        verbose_name="Prioridad",
        help_text="Mayor prioridad gana en caso de solapamiento de fechas"
    )
    
    class Meta:
        verbose_name = "Asignación de Fórmula"
        verbose_name_plural = "Asignaciones de Fórmulas"
        ordering = ['-valid_from', '-priority']
        indexes = [
            models.Index(fields=['variable', 'valid_from', 'valid_to']),
        ]

    def __str__(self):
        return f"{self.variable} -> {self.formula} ({self.valid_from.date()})"
        
    def clean(self):
        if self.valid_to and self.valid_from >= self.valid_to:
            raise ValidationError("La fecha de inicio debe ser anterior a la de fin.")


class RuleAssignment(ModelApi):
    """
    Asignación Temporal de una Regla a una Variable.
    Pérmite activar/desactivar reglas o cambiar sus parámetros por periodos.
    """
    variable = models.ForeignKey(
        'telemetry.CoreVariable',
        on_delete=models.CASCADE,
        related_name='rule_assignments',
        verbose_name="Variable"
    )
    
    rule = models.ForeignKey(
        ProcessingRule,
        on_delete=models.PROTECT,
        verbose_name="Regla"
    )
    
    parameters_override = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Override Parámetros",
        help_text="Sobreescribe los parámetros por defecto de la regla para este periodo"
    )
    
    valid_from = models.DateTimeField(
        verbose_name="Válido Desde",
        default=timezone.now
    )
    
    valid_to = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Válido Hasta",
        help_text="Dejar vacío para vigencia indefinida"
    )
    
    is_active = models.BooleanField(
        default=True,
        verbose_name="Activo",
        help_text="Desactivar para pausar la regla temporalmente"
    )
    
    priority = models.IntegerField(
        default=0,
        verbose_name="Prioridad"
    )
    
    class Meta:
        verbose_name = "Asignación de Regla"
        verbose_name_plural = "Asignaciones de Reglas"
        ordering = ['-valid_from', '-priority']
        indexes = [
            models.Index(fields=['variable', 'valid_from', 'valid_to']),
        ]

    def __str__(self):
        return f"{self.variable} + {self.rule} ({self.valid_from.date()})"

    def clean(self):
        if self.valid_to and self.valid_from >= self.valid_to:
            raise ValidationError("La fecha de inicio debe ser anterior a la de fin.")
