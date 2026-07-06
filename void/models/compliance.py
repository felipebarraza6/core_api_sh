"""Compliance models for void.

Modela entidades regulatorias (DGA, SMA, etc.), la configuración por punto
y la trazabilidad de cada envío.
"""
import base64
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from .base import VoidModel


class ComplianceAuthority(VoidModel):
    """Entidad regulatoria configurable (DGA, SMA, SEA, SISS, etc.).

    Separa la configuración DEL SISTEMA (URL, credenciales, protocolo) de la
    configuración POR PUNTO que vive en ``PointComplianceProfile``.
    """

    PROTOCOL_CHOICES = [
        ("HTTP_REST", "HTTP REST (JSON)"),
        ("HTTP_SOAP", "HTTP SOAP/XML"),
        ("WEBHOOK", "Webhook"),
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
        help_text="Identificador único. Ej: dga, sma, sea, siss.",
        db_index=True,
    )
    name = models.CharField(max_length=100, verbose_name="Nombre")

    protocol = models.CharField(
        max_length=20,
        choices=PROTOCOL_CHOICES,
        default="HTTP_REST",
        verbose_name="Protocolo",
    )
    auth_type = models.CharField(
        max_length=20,
        choices=AUTH_CHOICES,
        default="NONE",
        verbose_name="Autenticación",
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
        help_text="Opcional. Solo si el login es en endpoint separado (ej: SMA /auth).",
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
        verbose_name="Nombre del header",
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

    timeout_seconds = models.IntegerField(
        default=10,
        verbose_name="Timeout (segundos)",
        validators=[MinValueValidator(1)],
    )
    retry_attempts = models.IntegerField(
        default=3,
        verbose_name="Reintentos",
        validators=[MinValueValidator(0)],
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Activo",
        db_index=True,
    )

    class Meta:
        verbose_name = "Entidad de cumplimiento"
        verbose_name_plural = "Entidades de cumplimiento"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.code})"

    def get_auth_payload(self) -> dict:
        """Retorna payload de auth según auth_type."""
        if self.auth_type == "JSON_BODY":
            return {
                "usuario": self.auth_username,
                "password": self.auth_password,
            }
        return {}

    def get_auth_headers(self) -> dict:
        """Retorna headers de auth según auth_type."""
        headers = {}
        if self.auth_type == "BEARER":
            headers[self.auth_header_name] = f"Bearer {self.auth_token}"
        elif self.auth_type == "API_KEY_HEADER":
            headers[self.auth_header_name] = self.auth_token
        elif self.auth_type == "BASIC":
            creds = base64.b64encode(
                f"{self.auth_username}:{self.auth_password}".encode()
            ).decode()
            headers[self.auth_header_name] = f"Basic {creds}"
        return headers


class ComplianceStandard(VoidModel):
    """Estándar de envío de cumplimiento configurable dinámicamente.

    Cada estándar define la frecuencia con la que se deben enviar datos a la
    entidad regulatoria. Reemplaza la lógica hardcodeada de validate_frequency.
    """

    code = models.CharField(
        max_length=50,
        unique=True,
        verbose_name="Código",
        help_text="Ej: MAYOR, MEDIO, MENOR, SIN_ESTANDAR, CUSTOM.",
        db_index=True,
    )
    name = models.CharField(max_length=200, verbose_name="Nombre")
    description = models.TextField(
        blank=True,
        default="",
        verbose_name="Descripción",
    )

    frequency_minutes = models.PositiveIntegerField(
        default=60,
        verbose_name="Frecuencia base (minutos)",
        help_text="Frecuencia teórica de envío. Se usa solo para referencia/SLA.",
    )

    # Reglas de schedule: un valor >=0 significa "enviar solo cuando coincida".
    # None/null significa "cualquier valor".
    send_minute = models.IntegerField(
        blank=True,
        null=True,
        verbose_name="Minuto de envío",
        help_text="Ej: 0 para enviar en punto. Null = cualquier minuto.",
    )
    minute_interval = models.PositiveIntegerField(
        blank=True,
        null=True,
        verbose_name="Intervalo de minutos",
        help_text="Ej: 5 para enviar cuando minuto % 5 == 0. Null = no usar intervalo.",
    )
    send_hour = models.IntegerField(
        blank=True,
        null=True,
        verbose_name="Hora de envío",
        help_text="Ej: 0 para medianoche. Null = cualquier hora.",
    )
    send_day = models.IntegerField(
        blank=True,
        null=True,
        verbose_name="Día de envío",
        help_text="Ej: 1 para primer día del mes. Null = cualquier día.",
    )
    send_month = models.IntegerField(
        blank=True,
        null=True,
        verbose_name="Mes de envío",
        help_text="Ej: 1 o 7 para semestral. Null = cualquier mes.",
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name="Activo",
        db_index=True,
    )

    class Meta:
        verbose_name = "Estándar de cumplimiento"
        verbose_name_plural = "Estándares de cumplimiento"
        ordering = ["code"]

    def __str__(self):
        return f"{self.name} ({self.code})"

    def matches_timestamp(self, dt) -> bool:
        """Retorna True si el timestamp califica para envío según este estándar."""
        if self.minute_interval is not None and dt.minute % self.minute_interval != 0:
            return False
        if self.send_minute is not None and dt.minute != self.send_minute:
            return False
        if self.send_hour is not None and dt.hour != self.send_hour:
            return False
        if self.send_day is not None and dt.day != self.send_day:
            return False
        if self.send_month is not None and dt.month != self.send_month:
            return False
        return True


class PointComplianceProfile(VoidModel):
    """Configuración de cumplimiento para un punto y una entidad regulatoria."""

    point = models.ForeignKey(
        "void.Point",
        on_delete=models.CASCADE,
        related_name="compliance_profiles",
        verbose_name="Punto",
    )
    authority = models.ForeignKey(
        ComplianceAuthority,
        on_delete=models.CASCADE,
        related_name="point_profiles",
        verbose_name="Entidad",
    )
    standard = models.ForeignKey(
        ComplianceStandard,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="profiles",
        verbose_name="Estándar",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Activo",
        db_index=True,
    )

    external_code = models.CharField(
        max_length=300,
        blank=True,
        default="",
        verbose_name="Código externo",
        help_text="Código de obra, device id, etc.",
    )
    standard_legacy = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="Estándar (legacy)",
        help_text="Código legacy conservado para trazabilidad. Ej: MAYOR, MEDIO, MENOR.",
    )
    type_key = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="Tipo",
        help_text="Ej: SUBTERRANEO, SUPERFICIAL.",
    )
    region = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="Región",
    )
    shac = models.CharField(
        max_length=300,
        blank=True,
        default="",
        verbose_name="Sector hidrológico (SHAC)",
    )

    flow_granted = models.DecimalField(
        max_digits=15,
        decimal_places=3,
        blank=True,
        null=True,
        verbose_name="Caudal otorgado (l/s)",
    )
    total_granted = models.DecimalField(
        max_digits=15,
        decimal_places=3,
        blank=True,
        null=True,
        verbose_name="Totalizado otorgado (m³)",
    )

    informant_name = models.CharField(
        max_length=300,
        blank=True,
        default="",
        verbose_name="Nombre informante",
    )
    informant_rut = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="RUT informante",
    )

    date_start_compliance = models.DateField(
        blank=True,
        null=True,
        verbose_name="Fecha inicio envío",
    )
    date_created_code = models.DateField(
        blank=True,
        null=True,
        verbose_name="Fecha creación código",
    )

    aggregate_points = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Puntos agregados",
        help_text="Lista de IDs de puntos cuyo total se suma al enviar (ej: [84, 85]).",
    )
    variable_mapping = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Mapeo de variables",
        help_text="""
        Mapea variables de ProcessedReading a campos del payload.
        Ejemplo DGA:
        {"total": "total", "flow": "flow", "water_table": "water_table"}
        """,
    )
    extra_config = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Config extra",
    )

    class Meta:
        verbose_name = "Perfil de cumplimiento"
        verbose_name_plural = "Perfiles de cumplimiento"
        unique_together = ("point", "authority")
        indexes = [
            models.Index(fields=["point", "authority", "is_active"]),
            models.Index(fields=["authority", "is_active"]),
            models.Index(fields=["external_code"]),
        ]

    def __str__(self):
        return f"{self.point} → {self.authority}"

    def resolve_value(self, reading, field: str):
        """Resuelve un valor del ProcessedReading según variable_mapping.

        Si el campo no está mapeado, retorna el atributo del modelo directamente.
        """
        mapped = (self.variable_mapping or {}).get(field, field)
        if mapped.startswith("extra_values."):
            key = mapped.split(".", 1)[1]
            return (reading.extra_values or {}).get(key)
        return getattr(reading, mapped, None)


class ComplianceSubmission(VoidModel):
    """Cada intento de envío de cumplimiento."""

    STATUS_CHOICES = [
        ("pending", "Pendiente"),
        ("sent", "Enviado"),
        ("confirmed", "Confirmado"),
        ("failed", "Fallido"),
        ("duplicate", "Duplicado"),
        ("unrecoverable", "Irrecuperable"),
        ("retrying", "Reintentando"),
    ]

    profile = models.ForeignKey(
        PointComplianceProfile,
        on_delete=models.CASCADE,
        related_name="submissions",
        verbose_name="Perfil",
    )
    processed_reading = models.ForeignKey(
        "void.ProcessedReading",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="compliance_submissions",
        verbose_name="Lectura procesada",
    )

    period_start = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name="Inicio período",
    )
    period_end = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name="Término período",
    )

    payload = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Payload enviado",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
        verbose_name="Estado",
        db_index=True,
    )
    attempt_number = models.PositiveIntegerField(
        default=0,
        verbose_name="Intento",
    )

    response_status = models.IntegerField(
        blank=True,
        null=True,
        verbose_name="HTTP status",
    )
    response_body = models.TextField(
        blank=True,
        default="",
        verbose_name="Respuesta cruda",
    )
    voucher = models.CharField(
        max_length=500,
        blank=True,
        default="",
        verbose_name="Comprobante / Voucher",
    )
    tracking_id = models.CharField(
        max_length=500,
        blank=True,
        default="",
        verbose_name="Tracking ID",
    )

    sent_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name="Enviado el",
    )
    confirmed_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name="Confirmado el",
    )
    last_retry_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name="Último reintento",
    )
    error_message = models.CharField(
        max_length=1000,
        blank=True,
        default="",
        verbose_name="Mensaje de error",
    )

    class Meta:
        verbose_name = "Envío de cumplimiento"
        verbose_name_plural = "Envíos de cumplimiento"
        indexes = [
            models.Index(fields=["profile", "status", "created"]),
            models.Index(fields=["status", "created"]),
            models.Index(fields=["processed_reading", "status"]),
        ]
        ordering = ["-created"]

    def __str__(self):
        return f"{self.profile} | {self.status} | {self.attempt_number}"

    def mark_final(self, status: str, voucher: str = "", tracking_id: str = "", response_body: str = "", error_message: str = ""):
        """Marca la submission con un estado terminal."""
        self.status = status
        self.voucher = voucher or self.voucher
        self.tracking_id = tracking_id or self.tracking_id
        self.response_body = response_body or self.response_body
        self.error_message = error_message or self.error_message
        if status in ("confirmed", "sent", "duplicate"):
            self.confirmed_at = self.confirmed_at or timezone.now()
        self.save(update_fields=[
            "status", "voucher", "tracking_id", "response_body",
            "error_message", "confirmed_at", "modified",
        ])
