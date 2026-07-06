"""Configurable processing schema for void telemetry."""
from django.db import models

from void.models.base import VoidModel


class ProcessingSchema(VoidModel):
    """Esquema de procesamiento aplicable a dispositivos."""

    name = models.CharField(
        max_length=200,
        verbose_name="Nombre",
    )
    description = models.TextField(
        blank=True,
        default="",
        verbose_name="Descripción",
    )
    version = models.CharField(
        max_length=20,
        default="1.0",
        verbose_name="Versión",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Activo",
        db_index=True,
    )
    is_template = models.BooleanField(
        default=False,
        verbose_name="Es plantilla",
        db_index=True,
        help_text="Las plantillas se reutilizan entre múltiples variables/configuraciones.",
    )
    applies_to = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Aplica a",
        help_text='Ej: {"providers": ["tdata"], "point_groups": ["grupo_a"], "devices": ["uuid"]}',
    )

    class Meta:
        verbose_name = "Esquema de procesamiento"
        verbose_name_plural = "Esquemas de procesamiento"
        ordering = ["-created"]

    def __str__(self):
        return f"{self.name} v{self.version}"


class ProcessingStep(VoidModel):
    """Paso ordenado dentro de un esquema de procesamiento."""

    STEP_TYPE_CHOICES = [
        ("filter", "Filtrar"),
        ("transform", "Transformar"),
        ("validate", "Validar"),
        ("calculate", "Calcular"),
        ("aggregate", "Agregar"),
        ("stateful", "Con estado"),
    ]

    schema = models.ForeignKey(
        ProcessingSchema,
        on_delete=models.CASCADE,
        related_name="steps",
        verbose_name="Esquema",
    )
    order = models.PositiveIntegerField(
        default=0,
        verbose_name="Orden",
    )
    step_type = models.CharField(
        max_length=20,
        choices=STEP_TYPE_CHOICES,
        verbose_name="Tipo de paso",
    )
    name = models.CharField(
        max_length=200,
        blank=True,
        default="",
        verbose_name="Nombre",
    )
    input_variables = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Variables de entrada",
        help_text='Ej: ["pulses", "total"]',
    )
    output_variable = models.CharField(
        max_length=80,
        blank=True,
        default="",
        verbose_name="Variable de salida",
    )
    configuration = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Configuración",
        help_text="Parámetros específicos del tipo de paso.",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Activo",
    )

    class Meta:
        verbose_name = "Paso de procesamiento"
        verbose_name_plural = "Pasos de procesamiento"
        ordering = ["schema", "order"]
        unique_together = ("schema", "order")

    def __str__(self):
        return f"{self.schema} | {self.order}. {self.get_step_type_display()}"


class ProcessingRule(VoidModel):
    """Regla condicional dentro de un paso de procesamiento.

    Las reglas stateful usan ``condition`` como expresión Python evaluable
    contra el namespace del contexto (string vacío = siempre verdadera) y
    ``action`` como nombre de acción registrada en el motor stateful.
    """

    step = models.ForeignKey(
        ProcessingStep,
        on_delete=models.CASCADE,
        related_name="rules",
        verbose_name="Paso",
    )
    order = models.PositiveIntegerField(
        default=0,
        verbose_name="Orden",
    )
    condition = models.TextField(
        blank=True,
        default="",
        verbose_name="Condición",
        help_text="Expresión Python evaluable. Vacío = siempre ejecuta.",
    )
    action = models.CharField(
        max_length=40,
        verbose_name="Acción",
        help_text="Nombre de la acción registrada en el motor (stateful o pipeline).",
    )
    action_params = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Parámetros de acción",
        help_text='Ej: {"output": "total", "formula": "value * scale"}.',
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Activo",
    )

    class Meta:
        verbose_name = "Regla de procesamiento"
        verbose_name_plural = "Reglas de procesamiento"
        ordering = ["step", "order"]

    def __str__(self):
        return f"{self.step} | {self.action}"
