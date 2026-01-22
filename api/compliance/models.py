"""
Compliance Models
=================
Gestión de cumplimiento normativo (DGA, SMA, INDH, etc.)
"""

from django.db import models
from django.core.validators import URLValidator
from django.core.exceptions import ValidationError
from datetime import datetime

from api.core.models.utils import ModelApi
from api.core.models.users import User


class ComplianceStandard(ModelApi):
    """
    Estándar de cumplimiento con frecuencia configurable.
    Reemplaza los estándares hardcodeados MAYOR/MEDIO/MENOR/CMP.
    """
    code = models.CharField(
        max_length=50, 
        unique=True,
        help_text="Código corto (ej: MAYOR, MEDIO, MENOR, CMP)"
    )
    name = models.CharField(
        max_length=100,
        help_text="Nombre descriptivo (ej: Estándar Mayor)"
    )
    description = models.TextField(blank=True)
    
    # Frecuencia de envío
    FREQUENCY_CHOICES = [
        ('hourly', 'Por hora'),
        ('daily', 'Diario'),
        ('monthly', 'Mensual'),
        ('semestral', 'Semestral'),
        ('custom', 'Personalizado'),
    ]
    frequency_type = models.CharField(
        max_length=20,
        choices=FREQUENCY_CHOICES,
        default='daily'
    )
    
    # Configuración de timing
    hour = models.IntegerField(
        default=0,
        help_text="Hora del envío (0-23)"
    )
    minute = models.IntegerField(
        default=0,
        help_text="Minuto del envío (0-59)"
    )
    day_of_month = models.IntegerField(
        null=True, 
        blank=True,
        help_text="Día del mes para el envío (1-31)"
    )
    months = models.JSONField(
        default=list,
        blank=True,
        help_text="Lista de meses para envío (ej: [1, 7] para semestral)"
    )
    
    # Expresión cron informativa
    cron_expression = models.CharField(
        max_length=100, 
        blank=True,
        help_text="Expresión cron equivalente (informativo)"
    )
    
    # Metadata para reportes
    records_per_period = models.IntegerField(
        default=1,
        help_text="Cantidad de datos esperados por período"
    )
    
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'compliance_standard'
        verbose_name = "Estándar de Cumplimiento"
        verbose_name_plural = "Estándares de Cumplimiento"
        ordering = ['code']

    def __str__(self):
        return f"{self.name} ({self.code})"

    def matches_time(self, dt: datetime) -> bool:
        """
        Verifica si el datetime coincide con el patrón de envío del estándar.
        """
        if not self.is_active:
            return False

        # Validamos minuto siempre
        if dt.minute != self.minute:
            return False

        if self.frequency_type == 'hourly':
            return True
        
        # Validamos hora para daily en adelante
        if dt.hour != self.hour:
            return False

        if self.frequency_type == 'daily':
            return True
        
        # Validamos día para monthly en adelante
        if self.day_of_month is not None and dt.day != self.day_of_month:
            return False

        if self.frequency_type == 'monthly':
            return True
        
        # Validamos mes para semestral
        if self.frequency_type == 'semestral':
            return dt.month in self.months
        
        return False


class ComplianceProvider(ModelApi):
    """
    Dynamic Compliance Provider Configuration
    
    Defines a regulatory compliance service (DGA, SMA, etc.)
    that can be used by multiple catchment points.
    """

    # Basic Information
    name = models.CharField(
        max_length=50,
        unique=True,
        help_text="Unique identifier (e.g., 'dga', 'sma', 'indh')"
    )
    display_name = models.CharField(
        max_length=200,
        help_text="Human-readable name (e.g., 'DGA - Dirección General de Aguas')"
    )
    description = models.TextField(
        blank=True,
        help_text="Detailed description of the compliance provider"
    )

    # Service Type
    SERVICE_TYPES = [
        ('water_rights', 'Derechos de Agua'),
        ('environmental', 'Ambiental'),
        ('energy', 'Energía'),
        ('custom', 'Personalizado'),
    ]
    service_type = models.CharField(
        max_length=20,
        choices=SERVICE_TYPES,
        default='water_rights',
        help_text="Type of regulatory service"
    )

    # Connection Configuration
    base_url = models.URLField(
        validators=[URLValidator()],
        help_text="Base URL for API endpoints (e.g., https://dga.cl/api)"
    )
    
    auth_endpoint = models.CharField(
        max_length=200,
        blank=True,
        help_text="Authentication endpoint (e.g., /v1/auth)"
    )
    
    data_endpoint_template = models.CharField(
        max_length=500,
        help_text="Template for data submission endpoint. Use {variables}. "
                  "Example: /ufs/{uf_id}/procesos/{process_id}/registros"
    )
    
    timeout_seconds = models.IntegerField(
        default=30,
        help_text="Request timeout in seconds"
    )

    # Authentication Configuration
    AUTH_METHODS = [
        ('none', 'Sin Autenticación'),
        ('bearer', 'Bearer Token'),
        ('basic', 'Basic Auth'),
        ('oauth2', 'OAuth2 (user/pass → token)'),
        ('api_key', 'API Key'),
        ('custom', 'Personalizada'),
    ]
    auth_method = models.CharField(
        max_length=20,
        choices=AUTH_METHODS,
        default='bearer',
        help_text="Authentication method to use"
    )

    auth_config = models.JSONField(
        blank=True,
        default=dict,
        help_text="""
        Default authentication configuration as JSON. Examples:
        - Bearer: {"token": "your_token"}
        - Basic: {"username": "user", "password": "pass"}
        - OAuth2: {"username": "user", "password": "pass", "token_field": "token"}
        - API Key: {"key": "api_key", "header": "X-API-Key"}
        """
    )

    # Payload Template
    payload_template = models.JSONField(
        default=dict,
        help_text="""
        Template for building request payload. Use {config.*} for point config,
        {record.*} for telemetry data. Example:
        {
            "codigo_obra": "{config.codigo_obra}",
            "caudal": "{record.data.flow}",
            "fecha": "{record.timestamp}"
        }
        """
    )

    # Response Mapping
    response_mapping = models.JSONField(
        blank=True,
        default=dict,
        help_text="""
        Mapping for parsing API responses. Example:
        {
            "success_field": "status",
            "success_value": "ok",
            "voucher_field": "comprobante",
            "message_field": "mensaje"
        }
        """
    )

    # Required Fields Definition
    required_fields = models.JSONField(
        default=list,
        help_text="""
        Fields required for point configuration. Example:
        [
            {"name": "codigo_obra", "type": "string", "label": "Código de Obra"},
            {"name": "rut_informante", "type": "string", "label": "RUT Informante"},
            {"name": "caudal_otorgado", "type": "decimal", "label": "Caudal Otorgado (lt/s)"}
        ]
        """
    )

    # Variables definition for data
    data_variables = models.JSONField(
        default=list,
        help_text="""
        Variables to capture from telemetry or manual input. Example:
        [
            {"name": "caudal", "type": "decimal", "label": "Caudal (lt/s)", "unit": "l/s"},
            {"name": "nivel", "type": "decimal", "label": "Nivel (m)", "unit": "m"},
            {"name": "total", "type": "decimal", "label": "Totalizado (m³)", "unit": "m3"}
        ]
        """
    )

    # Validation Rules
    validation_rules = models.JSONField(
        blank=True,
        default=dict,
        help_text="Validation rules for data before submission"
    )

    # Submission Frequency
    FREQUENCY_CHOICES = [
        ('on_record', 'Cada registro'),
        ('hourly', 'Cada hora'),
        ('daily', 'Diario'),
        ('weekly', 'Semanal'),
        ('monthly', 'Mensual'),
    ]
    submission_frequency = models.CharField(
        max_length=20,
        choices=FREQUENCY_CHOICES,
        default='hourly',
        help_text="How often to submit data"
    )

    # Status & Retry Config
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this provider is available for use"
    )

    max_retries = models.IntegerField(
        default=3,
        help_text="Maximum number of retry attempts for failed requests"
    )

    retry_delay_seconds = models.IntegerField(
        default=60,
        help_text="Delay between retry attempts in seconds"
    )

    # Metadata
    documentation_url = models.URLField(
        blank=True,
        help_text="URL to provider documentation"
    )

    class Meta:
        db_table = 'compliance_provider'
        verbose_name = "Proveedor de Cumplimiento"
        verbose_name_plural = "Proveedores de Cumplimiento"
        ordering = ['name']

    def __str__(self):
        return f"{self.display_name} ({self.name})"

    def clean(self):
        """Validate provider configuration."""
        if self.auth_method != 'none' and not self.auth_config:
            raise ValidationError("auth_config is required when auth_method is not 'none'")
        
        if not self.data_endpoint_template:
            raise ValidationError("data_endpoint_template is required")


class PointComplianceConfig(ModelApi):
    """
    Association between Catchment Points and Compliance Providers

    Allows a point to submit data to multiple regulatory services,
    each with its own configuration and optional credential override.
    """

    point = models.ForeignKey(
        'telemetry.CatchmentPoint',
        related_name="compliance_configs",
        on_delete=models.CASCADE,
        verbose_name="Punto de Captación"
    )

    provider = models.ForeignKey(
        ComplianceProvider,
        on_delete=models.CASCADE,
        verbose_name="Proveedor de Cumplimiento"
    )

    compliance_standard = models.ForeignKey(
        ComplianceStandard,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="point_configs",
        verbose_name="Estándar de Cumplimiento",
        help_text="Define la frecuencia de envío (Mayor, Medio, Menor, CMP)"
    )

    # Point-specific Configuration
    config_data = models.JSONField(
        default=dict,
        help_text="""
        Point-specific configuration values. Example:
        {
            "codigo_obra": "ND-0401-1234",
            "rut_informante": "12345678-9",
            "nombre_informante": "Juan Pérez",
            "caudal_otorgado": 10.5,
            "dispositivo_id": "12180"
        }
        """
    )

    # Credentials Override (uses provider's if empty)
    credentials_override = models.JSONField(
        blank=True,
        default=dict,
        help_text="""
        Override provider credentials for this point.
        If empty, uses provider's default auth_config.
        Example: {"username": "otro_rut", "password": "otra_clave"}
        """
    )

    # Data Source Configuration
    DATA_SOURCE_CHOICES = [
        ('telemetry', 'Telemetría Automática'),
        ('manual', 'Ingreso Manual'),
        ('both', 'Ambos'),
    ]
    data_source = models.CharField(
        max_length=20,
        choices=DATA_SOURCE_CHOICES,
        default='telemetry',
        help_text="Source of data for compliance submissions"
    )

    # Status
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this configuration is active"
    )

    send_compliance = models.BooleanField(
        default=False,
        help_text="Enable automatic submission to this provider"
    )

    # Submission Tracking
    last_submission = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last submission attempt"
    )

    last_success = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last successful submission"
    )

    last_error = models.TextField(
        blank=True,
        help_text="Last error message"
    )

    error_count = models.IntegerField(
        default=0,
        help_text="Consecutive error count"
    )

    total_submissions = models.IntegerField(
        default=0,
        help_text="Total submissions sent"
    )

    successful_submissions = models.IntegerField(
        default=0,
        help_text="Total successful submissions"
    )

    class Meta:
        db_table = 'point_compliance_config'
        verbose_name = "Configuración de Cumplimiento por Punto"
        verbose_name_plural = "Configuraciones de Cumplimiento por Punto"
        unique_together = ['point', 'provider']
        ordering = ['point__title', 'provider__name']

    def __str__(self):
        status = "✅" if self.send_compliance and self.is_active else "❌"
        # Since point is a lazy reference, we might need simple string representation or handle it safely
        return f"{status} {self.point_id} → {self.provider}"

    def get_effective_credentials(self):
        """
        Get credentials to use for authentication.
        Returns override if set, otherwise provider's default.
        """
        if self.credentials_override:
            return {**self.provider.auth_config, **self.credentials_override}
        return self.provider.auth_config

    def should_submit_now(self, current_time) -> bool:
        """
        Determina si el registro debe enviarse según el estándar configurado.
        
        Args:
            current_time (datetime): Timestamp del registro a validar.
            
        Returns:
            bool: True si debe enviarse, False si no.
        """
        if not self.compliance_standard:
            return True  # Sin estándar definido, envía siempre (backward compatibility)
            
        return self.compliance_standard.matches_time(current_time)

    def record_success(self):
        """Record successful submission."""
        from django.utils import timezone
        self.last_submission = timezone.now()
        self.last_success = timezone.now()
        self.last_error = ""
        self.error_count = 0
        self.total_submissions += 1
        self.successful_submissions += 1
        self.save(update_fields=[
            'last_submission', 'last_success', 'last_error',
            'error_count', 'total_submissions', 'successful_submissions'
        ])

    def record_error(self, error_message: str):
        """Record failed submission."""
        from django.utils import timezone
        self.last_submission = timezone.now()
        self.last_error = error_message[:1000]  # Limit error length
        self.error_count += 1
        self.total_submissions += 1
        self.save(update_fields=[
            'last_submission', 'last_error', 'error_count', 'total_submissions'
        ])


class ManualComplianceRecord(ModelApi):
    """
    Manual Compliance Record for points without telemetry.
    
    Allows users to manually enter measurements for compliance
    submission when automatic telemetry is not available.
    """

    config = models.ForeignKey(
        PointComplianceConfig,
        related_name="manual_records",
        on_delete=models.CASCADE,
        verbose_name="Configuración de Cumplimiento"
    )

    # Measurement Data
    measurement_timestamp = models.DateTimeField(
        verbose_name="Fecha/Hora de Medición",
        help_text="When the measurement was taken"
    )

    data = models.JSONField(
        default=dict,
        help_text="""
        Measurement data. Example:
        {"caudal": 10.5, "nivel": 15.2, "total": 1234}
        """
    )

    # Submission Status
    STATUS_CHOICES = [
        ('pending', 'Pendiente'),
        ('queued', 'En Cola'),
        ('sent', 'Enviado'),
        ('error', 'Error'),
        ('cancelled', 'Cancelado'),
    ]
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name="Estado"
    )

    # Response Data
    response_data = models.JSONField(
        blank=True,
        default=dict,
        help_text="Response received from the provider"
    )

    voucher = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Comprobante",
        help_text="Submission voucher/receipt from provider"
    )

    error_message = models.TextField(
        blank=True,
        help_text="Error message if submission failed"
    )

    # Audit Fields
    created_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="manual_compliance_records",
        verbose_name="Creado por"
    )

    submitted_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the record was submitted to the provider"
    )

    class Meta:
        db_table = 'manual_compliance_record'
        verbose_name = "Registro Manual de Cumplimiento"
        verbose_name_plural = "Registros Manuales de Cumplimiento"
        ordering = ['-measurement_timestamp']
        indexes = [
            models.Index(fields=['config', 'status']),
            models.Index(fields=['measurement_timestamp']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"{self.config.point_id} - {self.measurement_timestamp.strftime('%Y-%m-%d %H:%M')}"
