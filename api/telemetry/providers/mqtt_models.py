"""
Modelos específicos para configuración MQTT dinámica.

Estos modelos extienden el sistema de proveedores para permitir
configuración completamente dinámica de conexiones MQTT y parsing
de payloads de diferentes formatos.
"""

import re
import uuid
from django.db import models
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator

from .models import TelemetryProvider


class MQTTProviderConfig(models.Model):
    """
    Configuración específica MQTT para proveedores.

    Extiende TelemetryProvider con parámetros específicos de MQTT.
    """

    provider = models.OneToOneField(
        TelemetryProvider,
        on_delete=models.CASCADE,
        related_name='mqtt_config',
        verbose_name="Proveedor"
    )

    # Identificación del Servicio (ej: netra, novus, twin)
    service_identifier = models.SlugField(
        max_length=50,
        default="generic",
        help_text="Identificador único del servicio/protocolo (ej: 'netra', 'novus')"
    )
    service_description = models.TextField(
        blank=True,
        help_text="Descripción del propósito de este servicio MQTT"
    )

    # Modo MQTT (cliente vs servidor)
    MQTT_MODES = [
        ('server', 'Servidor MQTT (escuchar broker local)'),
        ('client', 'Cliente MQTT (conectar a broker externo)'),
    ]
    mqtt_mode = models.CharField(
        max_length=10,
        choices=MQTT_MODES,
        default='server',
        help_text="""
        Rol MQTT:
        - server: SmartHydro ESCUCHA topics en broker local (equipos publican hacia SmartHydro)
        - client: SmartHydro se CONECTA a broker externo (SmartHydro consume de terceros)
        """
    )

    # Conexión al broker
    broker_host = models.CharField(
        max_length=255,
        help_text="Host/IP del broker MQTT (ej: broker.hivemq.com)"
    )
    broker_port = models.IntegerField(
        default=1883,
        help_text="Puerto del broker MQTT (1883 para MQTT, 8883 para MQTTS)"
    )
    use_tls = models.BooleanField(
        default=False,
        help_text="¿Usar TLS/SSL para la conexión?"
    )
    client_id_prefix = models.CharField(
        max_length=50,
        default="smarthydro",
        help_text="Prefijo para generar client_id únicos (ej: smarthydro)"
    )

    # Templates de topics
    subscribe_topic_template = models.CharField(
        max_length=500,
        help_text="""
        Template para topics de suscripción. Usa {variables}:
        - {provider}: Nombre del proveedor
        - {device_id}: ID del dispositivo
        - {point_code}: Código del punto
        Ejemplo: "{provider}/{device_id}/telemetry"
        """,
        validators=[RegexValidator(
            regex=r'\{[^}]+\}',
            message="Debe contener al menos una variable entre llaves {variable}"
        )]
    )
    publish_topic_template = models.CharField(
        max_length=500,
        blank=True,
        help_text="""
        Template para topics de publicación (opcional).
        Usa las mismas variables que subscribe_topic_template.
        """
    )

    # Configuración de QoS y persistencia
    default_qos = models.IntegerField(
        default=1,
        choices=[(0, '0 - Al menos una vez'), (1, '1 - Al menos una vez'), (2, '2 - Exactamente una vez')],
        help_text="QoS por defecto para mensajes"
    )
    retain_messages = models.BooleanField(
        default=False,
        help_text="¿Retener mensajes en el broker?"
    )

    # Credenciales adicionales
    username = models.CharField(
        max_length=100,
        blank=True,
        help_text="Usuario para autenticación MQTT (opcional)"
    )
    password = models.CharField(
        max_length=255,
        blank=True,
        help_text="Contraseña para autenticación MQTT (opcional)"
    )

    # Configuración avanzada
    keep_alive = models.IntegerField(
        default=60,
        help_text="Intervalo keep-alive en segundos"
    )
    reconnect_delay = models.IntegerField(
        default=5,
        help_text="Delay entre reintentos de conexión en segundos"
    )

    class Meta:
        verbose_name = "Configuración MQTT del Proveedor"
        verbose_name_plural = "Configuraciones MQTT de Proveedores"

    def __str__(self):
        return f"MQTT Config: {self.service_identifier} ({self.provider.display_name})"

    def clean(self):
        """Validar configuración MQTT."""
        if self.use_tls and self.broker_port == 1883:
            raise ValidationError("Para TLS debe usar puerto 8883 (MQTTS)")

        if not self.use_tls and self.broker_port == 8883:
            raise ValidationError("Puerto 8883 es para MQTTS (TLS)")

        # Validar que los templates tengan variables
        if '{' not in self.subscribe_topic_template:
            raise ValidationError("subscribe_topic_template debe contener variables entre llaves")

    def generate_client_id(self) -> str:
        """Generar un client_id único para esta conexión."""
        unique_id = uuid.uuid4().hex[:8]
        return f"{self.client_id_prefix}_{self.service_identifier}_{unique_id}"

    def build_subscribe_topic(self, **kwargs) -> str:
        """Construir topic de suscripción con variables."""
        try:
            # Inject service_identifier into variables
            kwargs.setdefault('service', self.service_identifier)
            return self.subscribe_topic_template.format(**kwargs)
        except KeyError as e:
            raise ValueError(f"Variable faltante en template de suscripción: {e}")

    def build_publish_topic(self, **kwargs) -> str:
        """Construir topic de publicación con variables."""
        if not self.publish_topic_template:
            raise ValueError("No hay template de publicación configurado")

        try:
            # Inject service_identifier into variables
            kwargs.setdefault('service', self.service_identifier)
            return self.publish_topic_template.format(**kwargs)
        except KeyError as e:
            raise ValueError(f"Variable faltante en template de publicación: {e}")


class PayloadParsingRule(models.Model):
    """
    Reglas dinámicas para parsear payloads MQTT.

    Permite configurar cómo extraer datos de diferentes formatos
    de payload (JSON, binario, texto, etc.)
    """

    provider = models.ForeignKey(
        TelemetryProvider,
        on_delete=models.CASCADE,
        related_name='parsing_rules',
        verbose_name="Proveedor"
    )

    name = models.CharField(
        max_length=100,
        help_text="Nombre descriptivo de la regla"
    )
    description = models.TextField(
        blank=True,
        help_text="Descripción detallada de cuándo y cómo usar esta regla"
    )

    # Condición de aplicación
    RULE_TYPES = [
        ('topic_match', 'Coincidencia de Topic (Regex)'),
        ('payload_field', 'Campo específico en Payload'),
        ('device_type', 'Tipo de Dispositivo'),
        ('always', 'Siempre Aplicar (Default)'),
    ]
    rule_type = models.CharField(
        max_length=20,
        choices=RULE_TYPES,
        default='always',
        help_text="Tipo de condición para aplicar esta regla"
    )

    rule_condition = models.JSONField(
        blank=True,
        default=dict,
        help_text="""
        Condición para aplicar la regla según rule_type:

        topic_match: {"pattern": "novus/+/data"}
        payload_field: {"field": "device_type", "value": "nxperience"}
        device_type: {"type": "plc_siemens"}
        always: {} (vacío)
        """
    )

    # Método de parsing
    PARSING_METHODS = [
        ('template', 'Template con Variables'),
        ('jsonpath', 'JSONPath/JMESPath'),
        ('python', 'Script Python'),
        ('regex', 'Expresiones Regulares'),
    ]
    parsing_method = models.CharField(
        max_length=20,
        choices=PARSING_METHODS,
        default='jsonpath',
        help_text="Método para extraer datos del payload"
    )

    # Configuración de extracción
    field_mappings = models.JSONField(
        help_text="""
        Mapeo de campos a extraer. Formato depende del parsing_method:

        template: {"field_name": "payload.{json_field}"}
        jsonpath: {"field_name": {"source": "$.data.value", "type": "jsonpath"}}
        python: {"field_name": "extract_custom_field(payload)"}
        regex: {"field_name": {"pattern": "value:(\\d+)", "group": 1}}
        """,
        default=dict
    )

    transformations = models.JSONField(
        blank=True,
        default=list,
        help_text="""
        Lista de transformaciones a aplicar a los campos extraídos.
        Ejemplo: [
            {"field": "timestamp", "type": "unix_to_datetime"},
            {"field": "flow", "type": "unit_conversion", "from": "m3/h", "to": "L/s"}
        ]
        """
    )

    # Validación
    validation_rules = models.JSONField(
        blank=True,
        default=dict,
        help_text="""
        Reglas de validación para campos extraídos.
        Ejemplo: {
            "flow": {"min": 0, "max": 1000},
            "timestamp": {"not_null": true}
        }
        """
    )

    # Prioridad y estado
    priority = models.IntegerField(
        default=0,
        help_text="Prioridad de aplicación (mayor = primero)"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="¿Esta regla está activa?"
    )

    class Meta:
        verbose_name = "Regla de Parsing de Payload"
        verbose_name_plural = "Reglas de Parsing de Payload"
        ordering = ['-priority', 'name']
        unique_together = ['provider', 'name']

    def __str__(self):
        return f"{self.provider.display_name} - {self.name}"

    def clean(self):
        """Validar configuración de regla."""
        if not self.field_mappings:
            raise ValidationError("field_mappings es requerido")

        # Validar condición según tipo
        if self.rule_type == 'topic_match':
            if 'pattern' not in self.rule_condition:
                raise ValidationError("rule_condition debe tener 'pattern' para topic_match")
            try:
                re.compile(self.rule_condition['pattern'])
            except re.error as e:
                raise ValidationError(f"Patrón regex inválido: {e}")

        elif self.rule_type == 'payload_field':
            required = ['field', 'value']
            for field in required:
                if field not in self.rule_condition:
                    raise ValidationError(f"rule_condition debe tener '{field}' para payload_field")

    def matches_condition(self, topic: str, payload: dict, device_id: str = None) -> bool:
        """Verificar si esta regla aplica a un mensaje."""
        if not self.is_active:
            return False

        if self.rule_type == 'always':
            return True

        elif self.rule_type == 'topic_match':
            pattern = self.rule_condition.get('pattern', '')
            return bool(re.match(pattern, topic))

        elif self.rule_type == 'payload_field':
            field = self.rule_condition.get('field')
            expected_value = self.rule_condition.get('value')
            actual_value = payload.get(field)
            return actual_value == expected_value

        elif self.rule_type == 'device_type':
            device_type = self.rule_condition.get('type')
            # Aquí podríamos consultar el tipo del dispositivo desde BD
            # Por ahora, comparación simple
            return device_id and device_type in device_id.lower()

        return False

    def validate_parsed_data(self, data: dict) -> list:
        """Validar datos parseados según validation_rules."""
        errors = []

        for field, rules in self.validation_rules.items():
            if field not in data:
                if rules.get('required', False):
                    errors.append(f"Campo requerido faltante: {field}")
                continue

            value = data[field]

            # Validación de rango
            if 'min' in rules and value < rules['min']:
                errors.append(f"{field}: {value} < mínimo {rules['min']}")
            if 'max' in rules and value > rules['max']:
                errors.append(f"{field}: {value} > máximo {rules['max']}")

            # Validación de nulidad
            if rules.get('not_null', False) and value is None:
                errors.append(f"{field}: no puede ser null")

        return errors


class CatchmentPointMQTT(models.Model):
    """
    Configuración MQTT específica por punto de captación.

    Permite overrides específicos para puntos individuales.
    """

    point = models.OneToOneField(
        'telemetry.CatchmentPoint',
        on_delete=models.CASCADE,
        related_name='mqtt_config',
        verbose_name="Punto de Captación"
    )

    provider = models.ForeignKey(
        TelemetryProvider,
        on_delete=models.CASCADE,
        verbose_name="Proveedor MQTT"
    )

    # Override de configuración
    custom_device_id = models.CharField(
        max_length=100,
        blank=True,
        help_text="ID personalizado del dispositivo (override del point_code)"
    )

    custom_topics = models.JSONField(
        blank=True,
        default=dict,
        help_text="""
        Topics personalizados para este punto.
        Ejemplo: {"subscribe": "custom/{device_id}/data"}
        """
    )

    # Configuración específica del dispositivo
    device_config = models.JSONField(
        blank=True,
        default=dict,
        help_text="""
        Configuración específica del dispositivo.
        Ejemplo: {"calibration_factor": 1.23, "sensor_offset": 0.5}
        """
    )

    # Estado
    is_active = models.BooleanField(
        default=True,
        help_text="¿Esta configuración está activa?"
    )

    last_seen = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Última vez que se recibió mensaje de este dispositivo"
    )

    class Meta:
        verbose_name = "Configuración MQTT del Punto"
        verbose_name_plural = "Configuraciones MQTT de Puntos"
        unique_together = ['point', 'provider']

    def __str__(self):
        return f"MQTT Config: {self.point} → {self.provider.display_name}"

    def get_effective_device_id(self) -> str:
        """Obtener el device_id efectivo (con override si existe)."""
        return self.custom_device_id or self.point.point_code

    def get_subscribe_topic(self) -> str:
        """Obtener topic de suscripción efectivo."""
        if self.custom_topics.get('subscribe'):
            template = self.custom_topics['subscribe']
        else:
            template = self.provider.mqtt_config.subscribe_topic_template

        return template.format(
            provider=self.provider.name,
            device_id=self.get_effective_device_id(),
            point_code=self.point.point_code
        )

    def get_publish_topic(self) -> str:
        """Obtener topic de publicación efectivo."""
        if self.custom_topics.get('publish'):
            template = self.custom_topics['publish']
        elif self.provider.mqtt_config.publish_topic_template:
            template = self.provider.mqtt_config.publish_topic_template
        else:
            raise ValueError("No hay template de publicación configurado")

        return template.format(
            provider=self.provider.name,
            device_id=self.get_effective_device_id(),
            point_code=self.point.point_code
        )