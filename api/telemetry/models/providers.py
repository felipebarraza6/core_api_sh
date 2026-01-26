"""Telemetry Provider Models."""
from django.db import models

from api.core.models.utils import ModelApi
from api.telemetry.models.catchment_points import CatchmentPoint


class TelemetryProvider(ModelApi):
    """Telemetry provider model."""

    name = models.CharField(max_length=100, unique=True, verbose_name="Nombre")
    PROVIDER_TYPE_CHOICES = [
        ("api", "REST API"),
        ("mqtt", "MQTT"),
        ("modbus", "ModBus TCP"),
    ]
    provider_type = models.CharField(
        max_length=50,
        choices=PROVIDER_TYPE_CHOICES,
        verbose_name="Tipo de Proveedor",
    )
    base_url = models.URLField(
        max_length=500, blank=True, null=True, verbose_name="URL Base"
    )
    AUTH_METHOD_CHOICES = [
        ("bearer", "Bearer Token"),
        ("basic", "Basic Auth"),
        ("api_key", "API Key"),
        ("none", "Sin autenticación"),
    ]
    auth_method = models.CharField(
        max_length=50,
        choices=AUTH_METHOD_CHOICES,
        default="none",
        verbose_name="Método de Autenticación",
    )
    auth_config = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Configuración de Autenticación",
        help_text="Credenciales, como tokens, API keys, etc.",
    )
    endpoint_template = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        verbose_name="Plantilla de Endpoint",
        help_text="Ej: /devices/{device_id}/data",
    )
    request_template = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Plantilla de Request",
        help_text="Cuerpo del request para enviar datos.",
    )
    response_mapping = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Mapeo de Respuesta",
        help_text="Define cómo interpretar la respuesta del proveedor.",
    )
    is_active = models.BooleanField(default=True, verbose_name="Activo")

    class Meta:
        db_table = "telemetry_provider"
        verbose_name = "Proveedor de Telemetría"
        verbose_name_plural = "Proveedores de Telemetría"

    def __str__(self):
        return self.name


class CatchmentPointProvider(ModelApi):
    """Catchment point provider configuration."""

    point = models.ForeignKey(
        CatchmentPoint,
        related_name="providers",
        on_delete=models.CASCADE,
        verbose_name="Punto de Captación",
    )
    provider = models.ForeignKey(
        TelemetryProvider,
        related_name="catchment_points",
        on_delete=models.CASCADE,
        verbose_name="Proveedor",
    )
    config_override = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Configuración Específica",
        help_text="Sobrescribe la configuración general del proveedor para este punto.",
    )
    is_active = models.BooleanField(default=True, verbose_name="Activo")
    priority = models.IntegerField(
        default=0,
        verbose_name="Prioridad",
        help_text="Prioridad de uso en caso de múltiples proveedores activos (0 es la más alta).",
    )

    class Meta:
        db_table = "telemetry_catchmentpoint_provider"
        verbose_name = "Proveedor del Punto de Captación"
        verbose_name_plural = "Proveedores del Punto de Captación"
        unique_together = ("point", "provider")
        ordering = ["priority"]

    def __str__(self):
        return f"{self.point.title} - {self.provider.name}"
