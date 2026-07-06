"""Base model for void."""
from django.db import models


class VoidModel(models.Model):
    """Modelo base con created/modified para toda la app void."""

    created = models.DateTimeField(
        "creado el",
        auto_now_add=True,
        help_text="Fecha de creación.",
    )
    modified = models.DateTimeField(
        "modificado el",
        auto_now=True,
        help_text="Fecha de última modificación.",
    )

    class Meta:
        abstract = True
        ordering = ["-created", "-modified"]
