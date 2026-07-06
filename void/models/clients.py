"""Client and organization models for void."""
from django.db import models

from void.models.base import VoidModel


class Client(VoidModel):
    """Cliente o organización que contrata servicios SmartHydro."""

    STATUS_CHOICES = [
        ("active", "Activo"),
        ("inactive", "Inactivo"),
        ("prospect", "Prospecto"),
        ("churned", "De baja"),
    ]

    name = models.CharField(
        max_length=300,
        verbose_name="Razón social / Nombre",
    )
    tax_id = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="RUT / Tax ID",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="active",
        verbose_name="Estado",
        db_index=True,
    )

    # Contacto principal
    contact_name = models.CharField(
        max_length=300,
        blank=True,
        default="",
        verbose_name="Nombre de contacto",
    )
    contact_email = models.EmailField(
        blank=True,
        default="",
        verbose_name="Email de contacto",
    )
    contact_phone = models.CharField(
        max_length=120,
        blank=True,
        default="",
        verbose_name="Teléfono de contacto",
    )

    # Facturación
    billing_email = models.EmailField(
        blank=True,
        default="",
        verbose_name="Email de facturación",
    )
    billing_phone = models.CharField(
        max_length=120,
        blank=True,
        default="",
        verbose_name="Teléfono de facturación",
    )
    billing_address = models.TextField(
        blank=True,
        default="",
        verbose_name="Dirección de facturación",
    )

    # Comercial
    account_manager = models.ForeignKey(
        "VoidUserProfile",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="managed_clients",
        verbose_name="Ejecutivo a cargo",
    )

    notes = models.TextField(
        blank=True,
        default="",
        verbose_name="Notas",
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Metadatos",
    )

    class Meta:
        verbose_name = "Cliente"
        verbose_name_plural = "Clientes"
        ordering = ["name"]
        indexes = [
            models.Index(fields=["status", "name"]),
            models.Index(fields=["tax_id"]),
        ]

    def __str__(self):
        return self.name
