"""Provider and endpoint configuration models for void."""
from django.db import models

from .base import VoidModel


class Provider(VoidModel):
    """Proveedor de telemetría configurable (HTTP, MQTT, WebSocket, etc.).

    Cada proveedor define su protocolo, autenticación y endpoints. Esto permite
    agregar APIs internas o externas sin tocar código: solo se crea el proveedor,
    sus endpoints y se asigna a un device.
    """

    PROTOCOL_CHOICES = [
        ("HTTP_REST", "HTTP REST (JSON)"),
        ("HTTP_GET", "HTTP GET simple"),
        ("MQTT", "MQTT Broker"),
        ("WEBSOCKET", "WebSocket"),
        ("CUSTOM", "Custom / Script"),
    ]

    AUTH_TYPE_CHOICES = [
        ("NONE", "Sin autenticación"),
        ("BASIC", "Basic Auth"),
        ("BEARER", "Bearer Token"),
        ("API_KEY_HEADER", "API Key en Header"),
        ("API_KEY_QUERY", "API Key en Query Param"),
        ("OAUTH2_PASSWORD", "OAuth2 Password"),
        ("OAUTH2_CLIENT", "OAuth2 Client Credentials"),
        ("CUSTOM", "Custom"),
    ]

    name = models.CharField(
        max_length=200,
        verbose_name="Nombre",
    )
    description = models.TextField(
        blank=True,
        default="",
        verbose_name="Descripción",
    )
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
        help_text="Ej: https://api.twindimension.com/tdata/v1 o mqtt://broker.smarthydro.cl:1883",
    )

    auth_type = models.CharField(
        max_length=20,
        choices=AUTH_TYPE_CHOICES,
        default="NONE",
        verbose_name="Tipo de autenticación",
    )
    auth_config = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Configuración de autenticación",
        help_text='Ej: {"username": "x", "password": "y"}, {"token": "abc"}, {"api_key": "k", "header_name": "X-API-Key"}',
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name="Activo",
        db_index=True,
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Metadatos",
        help_text="Config extra del proveedor. Ej: timeout, retry, parser default.",
    )

    class Meta:
        verbose_name = "Proveedor (void)"
        verbose_name_plural = "Proveedores (void)"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.protocol})"

    def get_endpoint(self, endpoint_type: str):
        """Retorna el endpoint activo de un tipo dado."""
        return self.endpoints.filter(endpoint_type=endpoint_type, is_active=True).first()


class ProviderEndpoint(VoidModel):
    """Endpoint dinámico de un proveedor.

    Permite definir auth, ingest, health, refresh-token, etc. por separado.
    """

    ENDPOINT_TYPE_CHOICES = [
        ("AUTH", "Autenticación / Login"),
        ("TOKEN_REFRESH", "Refrescar token"),
        ("INGEST", "Ingesta de lecturas"),
        ("HEALTH", "Health check"),
        ("DEVICE_INFO", "Info de dispositivo"),
        ("WEBHOOK", "Webhook receptor"),
        ("CUSTOM", "Custom"),
    ]

    HTTP_METHOD_CHOICES = [
        ("GET", "GET"),
        ("POST", "POST"),
        ("PUT", "PUT"),
        ("PATCH", "PATCH"),
        ("DELETE", "DELETE"),
    ]

    provider = models.ForeignKey(
        Provider,
        on_delete=models.CASCADE,
        related_name="endpoints",
        verbose_name="Proveedor",
    )
    endpoint_type = models.CharField(
        max_length=20,
        choices=ENDPOINT_TYPE_CHOICES,
        verbose_name="Tipo de endpoint",
        db_index=True,
    )
    name = models.CharField(
        max_length=200,
        blank=True,
        default="",
        verbose_name="Nombre",
    )
    http_method = models.CharField(
        max_length=10,
        choices=HTTP_METHOD_CHOICES,
        default="GET",
        verbose_name="Método HTTP",
    )
    path_template = models.CharField(
        max_length=500,
        blank=True,
        default="",
        verbose_name="Template de ruta",
        help_text="Variables: {base_url}, {external_id}, {variable}, {token}, etc.",
    )
    headers = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Headers",
        help_text='Ej: {"Content-Type": "application/json"}',
    )
    query_params = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Query params",
        help_text='Variables soportadas: {startTs}, {endTs}, {limit}, {variable}.',
    )
    body_template = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Body template",
        help_text="Solo para POST/PUT/PATCH. Variables: {username}, {password}, {token}.",
    )
    response_parser = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Parser de respuesta",
        help_text='Ej: {"root": "data", "value_field": "value", "timestamp_field": "ts", "timestamp_format": "iso"}',
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Activo",
        db_index=True,
    )
    order = models.PositiveIntegerField(
        default=0,
        verbose_name="Orden",
    )

    class Meta:
        verbose_name = "Endpoint de proveedor"
        verbose_name_plural = "Endpoints de proveedores"
        ordering = ["provider", "endpoint_type", "order"]
        unique_together = ("provider", "endpoint_type", "order")

    def __str__(self):
        return f"{self.provider} | {self.get_endpoint_type_display()}"
