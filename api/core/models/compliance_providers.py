"""Modelo CRUD para proveedores de cumplimiento regulatorio."""

from django.db import models

from .utils import ModelApi


class ComplianceProvider(ModelApi):
    """
    Protocolo de cumplimiento regulatorio configurable desde el admin.

    Sigue el mismo patrón que TelemetryProvider pero orientado a
    entidades regulatorias: DGA, SMA, SEA, SISS, etc.

    Separa la config DEL SISTEMA (URL, credenciales) de la config
    POR PUNTO (código de obra, estándar, etc. que vive en
    DgaDataConfigCatchment o modelos similares).
    """

    PROTOCOL_CHOICES = [
        ("HTTP_REST", "HTTP REST (JSON)"),
        ("HTTP_SOAP", "HTTP SOAP/XML"),
        ("WEBHOOK", "Webhook (Google Chat, Slack, etc.)"),
        ("CUSTOM", "Custom / Script"),
    ]

    AUTH_CHOICES = [
        ("NONE", "Sin autenticación"),
        ("BASIC", "Basic Auth"),
        ("BEARER", "Bearer Token"),
        ("API_KEY_HEADER", "API Key en Header"),
        ("JSON_BODY", "Credenciales en JSON Body"),
    ]

    code = models.CharField(
        max_length=20,
        unique=True,
        verbose_name="Código",
        help_text="Identificador único del sistema. Ej: dga, sma, sea",
    )
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
        help_text="Ej: https://apimee.mop.gob.cl/api/v1",
    )
    auth_url = models.URLField(
        max_length=500,
        blank=True,
        verbose_name="URL de autenticación",
        help_text="Opcional. Solo si el login es en endpoint separado (ej: SMA /auth)",
    )

    auth_type = models.CharField(
        max_length=20,
        choices=AUTH_CHOICES,
        default="NONE",
        verbose_name="Autenticación",
    )
    auth_username = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Usuario / RUT",
    )
    auth_password = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Password / Clave",
    )
    auth_token = models.CharField(
        max_length=500,
        blank=True,
        verbose_name="Token / API Key",
    )
    auth_header_name = models.CharField(
        max_length=100,
        blank=True,
        default="Authorization",
        verbose_name="Nombre del Header",
    )

    protocol_config = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Configuración del protocolo",
        help_text="""
        Config específica del protocolo en JSON.
        DGA ejemplo:
        {
            "subterraneo_endpoint": "/mediciones/subterraneas",
            "superficial_endpoint": "/mediciones/superficiales/flujometro",
            "default_rut_empresa": "76944359-2"
        }
        SMA ejemplo:
        {
            "token_header": "Authorization",
            "token_prefix": "Bearer"
        }
        """,
    )

    timeout_seconds = models.IntegerField(default=10, verbose_name="Timeout (segundos)")
    retry_attempts = models.IntegerField(default=3, verbose_name="Reintentos")
    is_active = models.BooleanField(default=True, db_index=True, verbose_name="Activo")

    class Meta:
        verbose_name = "Proveedor de Cumplimiento"
        verbose_name_plural = "Proveedores de Cumplimiento"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.code})"

    def get_auth_payload(self):
        """Retorna payload de auth según auth_type."""
        if self.auth_type == "JSON_BODY":
            return {
                "usuario": self.auth_username,
                "password": self.auth_password,
            }
        return None

    def get_auth_headers(self):
        """Retorna headers de auth según auth_type."""
        headers = {}
        if self.auth_type == "BEARER":
            headers[self.auth_header_name] = f"Bearer {self.auth_token}"
        elif self.auth_type == "API_KEY_HEADER":
            headers[self.auth_header_name] = self.auth_token
        elif self.auth_type == "BASIC":
            import base64
            creds = base64.b64encode(
                f"{self.auth_username}:{self.auth_password}".encode()
            ).decode()
            headers[self.auth_header_name] = f"Basic {creds}"
        return headers
