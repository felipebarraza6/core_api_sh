"""
Dynamic Provider Models

These models replace the hardcoded provider fields in CatchmentPoint
with a flexible, extensible architecture.
"""

from django.db import models
from django.core.validators import URLValidator
from django.core.exceptions import ValidationError

from api.core.models.utils import ModelApi
from ..models.catchment_points import CatchmentPoint


class TelemetryProvider(ModelApi):
    """
    Dynamic Telemetry Provider Configuration

    Defines a telemetry provider that can be used by multiple points.
    Supports different communication protocols and authentication methods.
    """

    # Basic Information
    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Unique identifier for the provider (e.g., 'nettra', 'twin', 'novus')"
    )
    display_name = models.CharField(
        max_length=200,
        help_text="Human-readable name (e.g., 'Nettra IoT Platform')"
    )
    description = models.TextField(
        blank=True,
        help_text="Detailed description of the provider"
    )

    # Provider Type & Protocol
    PROVIDER_TYPES = [
        ('api', 'REST API'),
        ('mqtt_server', 'MQTT Server (broker local - equipos publican hacia SmartHydro)'),
        ('mqtt_client', 'MQTT Client (broker externo - SmartHydro consume de terceros)'),
        ('mqtt', 'MQTT (legacy - usar mqtt_server o mqtt_client)'),
        ('modbus', 'ModBus TCP'),
        ('http', 'HTTP Endpoint'),
        ('websocket', 'WebSocket'),
    ]
    provider_type = models.CharField(
        max_length=20,
        choices=PROVIDER_TYPES,
        default='api',
        help_text="""
        Protocolo de comunicación:
        - api: REST API de terceros
        - mqtt_server: Broker local, equipos publican hacia SmartHydro
        - mqtt_client: Broker externo, SmartHydro se conecta como cliente
        - modbus: ModBus TCP/IP
        """
    )

    # Connection Configuration
    base_url = models.URLField(
        validators=[URLValidator()],
        help_text="Base URL for API endpoints (e.g., https://api.nettra.cl)"
    )
    timeout_seconds = models.IntegerField(
        default=30,
        help_text="Request timeout in seconds"
    )

    # Authentication Configuration
    AUTH_METHODS = [
        ('none', 'No Authentication'),
        ('bearer', 'Bearer Token'),
        ('basic', 'Basic Authentication'),
        ('api_key', 'API Key'),
        ('oauth2', 'OAuth2'),
        ('custom', 'Custom Authentication'),
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
        Authentication configuration as JSON. Examples:
        - Bearer: {"token": "your_token"}
        - Basic: {"username": "user", "password": "pass"}
        - API Key: {"key": "api_key", "header": "X-API-Key"}
        - OAuth2: {"client_id": "id", "client_secret": "secret", "token_url": "url"}
        """
    )

    # Request/Response Configuration
    endpoint_template = models.CharField(
        max_length=500,
        help_text="""
        Template for building endpoint URLs. Use {variables}.
        Examples:
        - "/api/v1/devices/{device_id}/data"
        - "/data?point={point_code}&variable={variable}"
        """
    )

    request_template = models.JSONField(
        blank=True,
        default=dict,
        help_text="""
        Template for request payload as JSON.
        Use {variables} for dynamic content.
        Example: {"device_id": "{device_code}", "variable": "{variable_type}"}
        """
    )

    response_mapping = models.JSONField(
        blank=True,
        default=dict,
        help_text="""
        Mapping for parsing API responses to standardized format.
        Example: {
            "timestamp": "data.time",
            "value": "data.value",
            "unit": "data.unit"
        }
        """
    )

    # Status & Configuration
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this provider is available for use"
    )

    max_retries = models.IntegerField(
        default=3,
        help_text="Maximum number of retry attempts for failed requests"
    )

    retry_delay_seconds = models.IntegerField(
        default=1,
        help_text="Delay between retry attempts in seconds"
    )

    # Metadata
    version = models.CharField(
        max_length=20,
        default="1.0",
        help_text="Provider API version"
    )

    documentation_url = models.URLField(
        blank=True,
        help_text="URL to provider documentation"
    )

    class Meta:
        verbose_name = "Proveedor de Telemetría"
        verbose_name_plural = "Proveedores de Telemetría"
        ordering = ['name']

    def __str__(self):
        return f"{self.display_name} ({self.name})"

    def clean(self):
        """Validate provider configuration."""
        if self.auth_method != 'none' and not self.auth_config:
            raise ValidationError("auth_config is required when auth_method is not 'none'")

        if self.provider_type == 'api' and not self.endpoint_template:
            raise ValidationError("endpoint_template is required for API providers")

    def get_auth_headers(self):
        """Generate authentication headers based on auth_method."""
        if self.auth_method == 'bearer' and 'token' in self.auth_config:
            return {'Authorization': f'Bearer {self.auth_config["token"]}'}

        elif self.auth_method == 'basic':
            import base64
            username = self.auth_config.get('username', '')
            password = self.auth_config.get('password', '')
            credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
            return {'Authorization': f'Basic {credentials}'}

        elif self.auth_method == 'api_key':
            key_name = self.auth_config.get('header', 'X-API-Key')
            key_value = self.auth_config.get('key', '')
            return {key_name: key_value}

        return {}

    def build_endpoint_url(self, **kwargs):
        """Build complete endpoint URL using template and variables."""
        try:
            return f"{self.base_url.rstrip('/')}{self.endpoint_template.format(**kwargs)}"
        except KeyError as e:
            raise ValueError(f"Missing required variable for endpoint template: {e}")

    def build_request_payload(self, **kwargs):
        """Build request payload using template and variables."""
        if not self.request_template:
            return {}

        # Deep copy and format template
        import json
        template_str = json.dumps(self.request_template)
        try:
            formatted_str = template_str.format(**kwargs)
            return json.loads(formatted_str)
        except KeyError as e:
            raise ValueError(f"Missing required variable for request template: {e}")


class CatchmentPointProvider(ModelApi):
    """
    Association between Catchment Points and Telemetry Providers

    Allows multiple providers per point with different configurations.
    Supports provider failover and load balancing.
    """

    point = models.ForeignKey(
        CatchmentPoint,
        related_name="provider_configs",
        on_delete=models.CASCADE,
        verbose_name="Punto de Captación"
    )

    provider = models.ForeignKey(
        TelemetryProvider,
        on_delete=models.CASCADE,
        verbose_name="Proveedor"
    )

    # Device físico (opcional, para trazabilidad - el Device principal está en CatchmentPoint)
    device = models.ForeignKey(
        'infrastructure.Device',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='provider_configs',
        verbose_name="Dispositivo Físico",
        help_text="Dispositivo físico que genera los datos (opcional, para trazabilidad)"
    )

    # Variable que esta configuración de proveedor alimenta
    variable = models.ForeignKey(
        'telemetry.CoreVariable',
        on_delete=models.CASCADE,
        related_name='provider_configs',
        verbose_name="Variable",
        help_text="Variable del punto que recibe datos de este proveedor"
    )

    # Configuration Override
    config_override = models.JSONField(
        blank=True,
        default=dict,
        help_text="""
        Override provider configuration for this specific point.
        Same format as TelemetryProvider.auth_config.
        """
    )

    # Point-specific Configuration
    provider_device_id = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="ID del Dispositivo en el Proveedor",
        help_text="""
        Identificador del dispositivo en el sistema del proveedor externo.
        Ejemplos:
        - Nettra: "station_123"
        - TTN: "eui-70b3d57ed0012345"
        - MQTT: "device_001" o serial del equipo
        """
    )

    device_config = models.JSONField(
        blank=True,
        default=dict,
        help_text="Device-specific configuration (e.g., sensor mappings, calibration data)"
    )

    # Status & Priority
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this provider configuration is active for the point"
    )

    priority = models.IntegerField(
        default=0,
        help_text="Priority for load balancing/failover (higher = preferred)"
    )

    # Monitoring
    last_success = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last successful data retrieval"
    )

    last_error = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last failed attempt"
    )

    error_count = models.IntegerField(
        default=0,
        help_text="Consecutive error count"
    )

    consecutive_successes = models.IntegerField(
        default=0,
        help_text="Consecutive successful requests"
    )

    class Meta:
        verbose_name = "Configuración de Proveedor por Punto"
        verbose_name_plural = "Configuraciones de Proveedor por Punto"
        unique_together = ['point', 'provider', 'variable']
        ordering = ['-priority', 'provider__name']

    def __str__(self):
        status = "✅" if self.is_active else "❌"
        return f"{status} {self.point} → {self.provider}"

    def get_effective_config(self):
        """Get merged configuration (provider + override)."""
        base_config = self.provider.auth_config.copy()
        base_config.update(self.config_override)
        return base_config

    def record_success(self):
        """Record successful data retrieval."""
        from django.utils import timezone
        self.last_success = timezone.now()
        self.last_error = None
        self.error_count = 0
        self.consecutive_successes += 1
        self.save(update_fields=['last_success', 'last_error', 'error_count', 'consecutive_successes'])

    def record_error(self, error_message=None):
        """Record failed data retrieval."""
        from django.utils import timezone
        self.last_error = timezone.now()
        self.error_count += 1
        self.consecutive_successes = 0
        self.save(update_fields=['last_error', 'error_count', 'consecutive_successes'])

        # Log error if provided
        if error_message:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Provider error for {self}: {error_message}")

    @property
    def is_healthy(self):
        """Check if provider is healthy based on error rate."""
        # Consider healthy if error rate < 20% in last 10 attempts
        total_attempts = self.error_count + self.consecutive_successes
        if total_attempts < 10:
            return True  # Not enough data
        return (self.error_count / total_attempts) < 0.2



class ProviderDataSync(ModelApi):
    """
    Estado de Sincronización de Datos con Proveedores.
    Rastrea el progreso y estado de los trabajos de sincronización.
    """
    
    provider = models.ForeignKey(
        TelemetryProvider,
        on_delete=models.CASCADE,
        related_name='sync_jobs',
        verbose_name="Proveedor"
    )

    SYNC_TYPES = [
        ('FULL_HISTORICAL', 'Histórico Completo'),
        ('INCREMENTAL', 'Incremental'),
        ('REALTIME', 'Tiempo Real (Polling)'),
    ]
    sync_type = models.CharField(
        max_length=20,
        choices=SYNC_TYPES,
        default='INCREMENTAL'
    )

    current_status = models.CharField(
        max_length=20,
        choices=[
            ('IDLE', 'Inactivo'),
            ('RUNNING', 'Ejecutando'),
            ('SUCCESS', 'Exitoso'),
            ('PARTIAL_SUCCESS', 'Parcialmente Exitoso'),
            ('FAILED', 'Fallido'),
            ('CANCELLED', 'Cancelado')
        ],
        default='IDLE'
    )

    last_sync_attempt = models.DateTimeField(null=True, blank=True)
    last_successful_sync = models.DateTimeField(null=True, blank=True)
    
    # Stats
    total_records_synced = models.BigIntegerField(default=0)
    last_sync_records = models.IntegerField(default=0)
    consecutive_failures = models.IntegerField(default=0)
    last_error_message = models.TextField(blank=True)
    
    # Configuration for this specific job
    sync_config = models.JSONField(
        default=dict, 
        blank=True,
        help_text="Configuración específica del trabajo (buffer, threads, etc)"
    )
    
    # Scheduling
    is_active = models.BooleanField(default=True)
    sync_interval_minutes = models.IntegerField(default=60)
    
    # New Fields for Metrics
    messages_received_today = models.IntegerField(default=0)
    messages_sent_today = models.IntegerField(default=0)
    bytes_received_today = models.BigIntegerField(default=0)

    class Meta:
        verbose_name = "Sincronización de Proveedor"
        verbose_name_plural = "Sincronizaciones de Proveedores"
        unique_together = ['provider', 'sync_type']

    def __str__(self):
        return f"{self.provider.display_name} - {self.get_sync_type_display()}"
    
    def update_sync_status(self, status, records=0, error_message=None):
        """Helper to update status efficiently."""
        from django.utils import timezone
        self.current_status = status
        self.last_sync_attempt = timezone.now()
        
        if status == 'SUCCESS' or status == 'PARTIAL_SUCCESS':
            self.last_successful_sync = timezone.now()
            self.consecutive_failures = 0
            self.last_sync_records = records
            self.total_records_synced += records
            self.messages_received_today += records # Simplification
        elif status == 'FAILED':
            self.consecutive_failures += 1
            if error_message:
                self.last_error_message = error_message[:1000]
                
        self.save()


# Import compliance models to make them available in this module
# This allows Django to auto-discover them during migrations
from .compliance_models import (
    ComplianceProvider,
    PointComplianceConfig,
    ManualComplianceRecord,
)

from .compliance_standard import ComplianceStandard

# Import MQTT models to make them available in this module
# This allows Django to auto-discover them during migrations
from .mqtt_models import (
    MQTTProviderConfig,
    PayloadParsingRule,
    CatchmentPointMQTT,
)