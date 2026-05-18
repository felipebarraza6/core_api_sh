"""Modelo CRUD para proveedores de telemetría."""

from django.db import models

from .utils import ModelApi


class TelemetryProvider(ModelApi):
    """
    Proveedor de API de telemetría configurable desde el admin.
    Soporta handlers específicos (tdata, thethings, tago) para retrocompatibilidad,
    y parser genérico JSON para proveedores nuevos sin tocar código.
    """

    PROTOCOL_CHOICES = [
        ("HTTP_REST", "HTTP REST (GET/POST JSON)"),
        ("HTTP_GET", "HTTP GET genérico"),
        ("MQTT", "MQTT Broker"),
        ("WEBSOCKET", "WebSocket"),
        ("CUSTOM", "Custom / Script"),
    ]

    AUTH_CHOICES = [
        ("NONE", "Sin autenticación"),
        ("BASIC", "Basic Auth (usuario + password)"),
        ("BEARER", "Bearer Token"),
        ("API_KEY_HEADER", "API Key en Header"),
        ("QUERY_PARAM", "API Key en Query Param"),
    ]

    HANDLER_CHOICES = [
        ("generic_json", "JSON Genérico (parser_config)"),
        ("tdata", "TDATA (TwinDimension - login + bearer)"),
        ("thethings", "TheThings.io v2"),
        ("tago", "Tago.io"),
    ]

    name = models.CharField(max_length=100, verbose_name="Nombre")
    protocol = models.CharField(
        max_length=20,
        choices=PROTOCOL_CHOICES,
        default="HTTP_REST",
        verbose_name="Protocolo",
    )
    base_url = models.URLField(
        max_length=500,
        blank=True,
        verbose_name="URL base",
        help_text="Ej: https://api.twindimension.com/tdata/v1",
    )
    endpoint_template = models.CharField(
        max_length=500,
        blank=True,
        verbose_name="Template de endpoint",
        help_text="Variables: {token}, {variable}. Ej: /things/{token}/resources/{variable}",
    )

    auth_type = models.CharField(
        max_length=20,
        choices=AUTH_CHOICES,
        default="NONE",
        verbose_name="Autenticación",
    )
    auth_username = models.CharField(max_length=200, blank=True, verbose_name="Usuario")
    auth_password = models.CharField(max_length=200, blank=True, verbose_name="Password")
    auth_token = models.CharField(
        max_length=500,
        blank=True,
        verbose_name="Token / API Key",
        help_text="Para Bearer, API Key o Header personalizado",
    )
    auth_header_name = models.CharField(
        max_length=100,
        blank=True,
        default="Authorization",
        verbose_name="Nombre del Header",
    )

    # Handler: qué lógica de parsing usar
    handler_name = models.CharField(
        max_length=20,
        choices=HANDLER_CHOICES,
        default="generic_json",
        verbose_name="Handler de datos",
        help_text="tdata/thethings/tago = lógica específica hardcodeada. generic_json = configurable vía parser_config.",
    )
    parser_config = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Configuración del parser",
        help_text="""
        Solo para handler "generic_json". Ej:
        {
            "value_field": "value",
            "timestamp_field": "ts",
            "timestamp_format": "epoch_ms",
            "response_is_array": true,
            "response_root_key": "result",
            "response_array_index": 0
        }
        """,
    )

    timeout_seconds = models.IntegerField(default=5, verbose_name="Timeout (segundos)")
    retry_attempts = models.IntegerField(default=3, verbose_name="Reintentos")
    is_active = models.BooleanField(default=True, db_index=True, verbose_name="Activo")

    class Meta:
        verbose_name = "Proveedor de Telemetría"
        verbose_name_plural = "Proveedores de Telemetría"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.handler_name})"
