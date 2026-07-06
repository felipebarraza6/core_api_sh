"""Estado genérico de variables procesadas para void."""
from django.db import models

from void.models.base import VoidModel


class DeviceVariableState(VoidModel):
    """Estado persistente genérico por device/variable.

    Permite a handlers con memoria (totalizadores, contadores, alarmas
    flanqueadas, etc.) guardar su contexto sin depender de modelos
    específicos.  El contenido de ``state`` es libre para cada handler.
    """

    device = models.ForeignKey(
        "void.Device",
        on_delete=models.CASCADE,
        related_name="variable_states",
        verbose_name="Dispositivo",
    )
    variable = models.CharField(
        max_length=80,
        verbose_name="Variable",
        db_index=True,
    )
    state = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Estado",
        help_text="Diccionario libre mantenido por el handler stateful.",
    )
    last_processed_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name="Último procesamiento",
    )

    class Meta:
        verbose_name = "Estado de variable"
        verbose_name_plural = "Estados de variables"
        unique_together = ("device", "variable")
        indexes = [
            models.Index(fields=["device", "variable"]),
        ]

    def __str__(self):
        return f"{self.device} | {self.variable}"
