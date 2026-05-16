"""Modelo CRUD para proveedores de telemetría."""

from django.db import models

from .utils import ModelApi


class TelemetryProvider(ModelApi):
    """
    Proveedor de API de telemetría (TDATA, TheThings, Tago, etc.)
    Permite configurar URLs, credenciales y autenticación desde el admin
    sin tocar código ni .env.
    """

    PROVIDER_TYPES = [
        ("TWIN", "TWIN (TwinDimension / TDATA)"),
        ("NETTRA", "NETTRA (TheThings.io)"),
        ("NOVUS", "NOVUS (Tago.io)"),
        ("CUSTOM", "Custom / Otro"),
    ]

    AUTH_TYPES = [
        ("NONE", "Sin autenticación"),
        ("BASIC", "Basic Auth (usuario + password)"),
        ("BEARER", "Bearer Token"),
        ("API_KEY", "API Key en Header"),
        ("HEADER", "Header personalizado"),
    ]

    name = models.CharField(max_length=100, verbose_name="Nombre")
    provider_type = models.CharField(
        max_length=20,
        choices=PROVIDER_TYPES,
        verbose_name="Tipo de proveedor",
    )
    base_url = models.URLField(
        max_length=500,
        blank=True,
        verbose_name="URL base",
        help_text="Ej: https://api.twindimension.com/tdata/v1",
    )
    auth_type = models.CharField(
        max_length=20,
        choices=AUTH_TYPES,
        default="NONE",
        verbose_name="Tipo de autenticación",
    )
    auth_username = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Usuario",
        help_text="Para Basic Auth",
    )
    auth_password = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Password",
        help_text="Para Basic Auth",
    )
    auth_token = models.CharField(
        max_length=500,
        blank=True,
        verbose_name="Token / API Key",
        help_text="Para Bearer, API Key o Header personalizado",
    )
    auth_header_name = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Nombre del Header",
        help_text="Ej: Authorization, authorization, x-api-key",
    )
    is_active = models.BooleanField(default=True, verbose_name="Activo")

    class Meta:
        verbose_name = "Proveedor de Telemetría"
        verbose_name_plural = "Proveedores de Telemetría"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.provider_type})"
