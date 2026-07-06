"""Project models for void."""
from django.db import models

from .base import VoidModel


class Project(VoidModel):
    """Proyecto dentro de un cliente. Agrupa puntos de captación."""

    name = models.CharField(
        max_length=300,
        verbose_name="Nombre",
    )
    description = models.TextField(
        blank=True,
        default="",
        verbose_name="Descripción",
    )
    client = models.ForeignKey(
        "void.Client",
        on_delete=models.CASCADE,
        related_name="projects",
        verbose_name="Cliente",
    )
    code_internal = models.CharField(
        max_length=300,
        blank=True,
        default="",
        verbose_name="Código interno",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Activo",
        db_index=True,
    )

    class Meta:
        verbose_name = "Proyecto"
        verbose_name_plural = "Proyectos"
        ordering = ["name"]
        indexes = [
            models.Index(fields=["client", "is_active"]),
        ]

    def __str__(self):
        return f"{self.client} | {self.name}"
