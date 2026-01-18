"""
Modelos Avanzados para Super Gestión de SmartHydro
Modelos que proporcionan capacidades empresariales avanzadas
"""

from datetime import timedelta

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import JSONField
from django.utils import timezone

from .catchment_points import CatchmentPoint, Client
from .users import User
from .utils import ModelApi


class SystemConfiguration(ModelApi):
    """
    Configuración global del sistema - reemplaza settings hardcoded
    """

    key = models.CharField(
        max_length=100, unique=True, help_text="Clave de configuración única"
    )

    value = JSONField(help_text="Valor de configuración (JSON)")

    category = models.CharField(
        max_length=50,
        choices=[
            ("TELEMETRY", "Telemetría"),
            ("MQTT", "MQTT"),
            ("SECURITY", "Seguridad"),
            ("PERFORMANCE", "Performance"),
            ("NOTIFICATIONS", "Notificaciones"),
            ("REPORTING", "Reportes"),
        ],
        help_text="Categoría de configuración",
    )

    is_encrypted = models.BooleanField(default=False, help_text="Valor encriptado")

    description = models.TextField(
        blank=True, help_text="Descripción de la configuración"
    )

    class Meta:
        verbose_name = "Configuración del Sistema"
        verbose_name_plural = "Configuraciones del Sistema"
        indexes = [
            models.Index(fields=["category", "key"]),
        ]

    def __str__(self):
        return f"{self.category}: {self.key}"


class EquipmentProvider(ModelApi):
    """
    Proveedores/fabricantes de equipos IoT
    """

    name = models.CharField(
        max_length=100, unique=True, help_text="Nombre del proveedor/fabricante"
    )

    code = models.CharField(
        max_length=20, unique=True, help_text="Código único del proveedor"
    )

    description = models.TextField(blank=True, help_text="Descripción del proveedor")

    website = models.URLField(blank=True, help_text="Sitio web del proveedor")

    contact_email = models.EmailField(blank=True, help_text="Email de contacto")

    contact_phone = models.CharField(
        max_length=20, blank=True, help_text="Teléfono de contacto"
    )

    # MQTT Configuration
    mqtt_broker_host = models.CharField(
        max_length=255, blank=True, help_text="Host del broker MQTT del proveedor"
    )

    mqtt_broker_port = models.PositiveIntegerField(
        default=1883,
        validators=[MinValueValidator(1), MaxValueValidator(65535)],
        help_text="Puerto del broker MQTT",
    )

    mqtt_username = models.CharField(
        max_length=100, blank=True, help_text="Usuario MQTT"
    )

    mqtt_password = models.CharField(
        max_length=255, blank=True, help_text="Contraseña MQTT"
    )

    mqtt_use_tls = models.BooleanField(default=False, help_text="Usar TLS para MQTT")

    # Capabilities
    supported_protocols = models.JSONField(
        default=list,
        blank=True,
        help_text="Protocolos soportados (MQTT, HTTP, CoAP, etc.)",
    )

    supported_sensors = models.JSONField(
        default=list,
        blank=True,
        help_text="Tipos de sensores soportados",
    )

    # Status
    is_active = models.BooleanField(default=True, help_text="Proveedor activo")

    integration_status = models.CharField(
        max_length=20,
        choices=[
            ("NOT_STARTED", "No iniciado"),
            ("IN_PROGRESS", "En progreso"),
            ("TESTING", "En pruebas"),
            ("PRODUCTION", "En producción"),
            ("DEPRECATED", "Obsoleto"),
        ],
        default="NOT_STARTED",
        help_text="Estado de integración",
    )

    class Meta:
        verbose_name = "Proveedor de Equipos"
        verbose_name_plural = "Proveedores de Equipos"
        indexes = [
            models.Index(fields=["is_active", "integration_status"]),
            models.Index(fields=["code"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.code})"


class EquipmentModel(ModelApi):
    """
    Modelos específicos de equipos por proveedor
    """

    provider = models.ForeignKey(
        EquipmentProvider,
        on_delete=models.CASCADE,
        related_name="equipment_models",
        help_text="Proveedor del equipo",
    )

    model_name = models.CharField(max_length=100, help_text="Nombre del modelo")

    model_code = models.CharField(max_length=50, help_text="Código del modelo")

    description = models.TextField(blank=True, help_text="Descripción del modelo")

    # Technical specifications
    power_supply = models.CharField(
        max_length=100, blank=True, help_text="Tipo de alimentación"
    )

    battery_life_days = models.PositiveIntegerField(
        null=True, blank=True, help_text="Vida útil de batería en días"
    )

    operating_temperature_min = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        null=True,
        blank=True,
        help_text="Temperatura mínima de operación (°C)",
    )

    operating_temperature_max = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        null=True,
        blank=True,
        help_text="Temperatura máxima de operación (°C)",
    )

    # Sensor capabilities
    available_sensors = JSONField(
        default=dict, help_text="Sensores disponibles y sus especificaciones"
    )

    # Communication
    communication_range_meters = models.PositiveIntegerField(
        null=True, blank=True, help_text="Rango de comunicación en metros"
    )

    data_transmission_interval_min = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Intervalo mínimo de transmisión de datos (minutos)",
    )

    # Status
    is_active = models.BooleanField(default=True, help_text="Modelo activo")

    release_date = models.DateField(
        null=True, blank=True, help_text="Fecha de lanzamiento del modelo"
    )

    end_of_life_date = models.DateField(
        null=True, blank=True, help_text="Fecha de fin de vida útil"
    )

    class Meta:
        verbose_name = "Modelo de Equipo"
        verbose_name_plural = "Modelos de Equipos"
        indexes = [
            models.Index(fields=["provider", "model_code"]),
            models.Index(fields=["is_active"]),
        ]
        unique_together = ["provider", "model_code"]

    def __str__(self):
        return f"{self.provider.name} - {self.model_name}"


class IoTDevice(ModelApi):
    """
    Dispositivos IoT físicos conectados al sistema
    """

    device_id = models.CharField(
        max_length=100,
        unique=True,
        help_text="ID único del dispositivo (MAC, Serial, etc.)",
    )

    name = models.CharField(
        max_length=100, help_text="Nombre descriptivo del dispositivo"
    )

    # Relationships
    catchment_point = models.ForeignKey(
        CatchmentPoint,
        on_delete=models.CASCADE,
        related_name="iot_devices",
        help_text="Punto de captación al que pertenece",
    )

    equipment_model = models.ForeignKey(
        EquipmentModel,
        on_delete=models.PROTECT,
        related_name="devices",
        help_text="Modelo del equipo",
    )

    # Device configuration
    firmware_version = models.CharField(
        max_length=50, blank=True, help_text="Versión de firmware actual"
    )

    config_parameters = JSONField(
        default=dict, help_text="Parámetros de configuración del dispositivo"
    )

    # MQTT Configuration
    mqtt_topic_prefix = models.CharField(
        max_length=255,
        blank=True,
        help_text="Prefijo del topic MQTT para este dispositivo",
    )

    mqtt_publish_interval = models.PositiveIntegerField(
        default=60, help_text="Intervalo de publicación MQTT en minutos"
    )

    # Status and monitoring
    DEVICE_STATUS_CHOICES = [
        ("OFFLINE", "Offline"),
        ("ONLINE", "Online"),
        ("ERROR", "Error"),
        ("MAINTENANCE", "Mantenimiento"),
        ("BATTERY_LOW", "Batería baja"),
    ]

    status = models.CharField(
        max_length=20,
        choices=DEVICE_STATUS_CHOICES,
        default="OFFLINE",
        help_text="Estado actual del dispositivo",
    )

    last_seen = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Última vez que se recibió data del dispositivo",
    )

    battery_level = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Nivel de batería (%)",
    )

    signal_strength = models.IntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(-120), MaxValueValidator(0)],
        help_text="Intensidad de señal (dBm)",
    )

    # Location data (if different from catchment point)
    device_latitude = models.DecimalField(
        max_digits=10,
        decimal_places=8,
        null=True,
        blank=True,
        help_text="Latitud específica del dispositivo",
    )

    device_longitude = models.DecimalField(
        max_digits=11,
        decimal_places=8,
        null=True,
        blank=True,
        help_text="Longitud específica del dispositivo",
    )

    # Management
    installed_date = models.DateField(
        null=True, blank=True, help_text="Fecha de instalación"
    )

    last_maintenance_date = models.DateField(
        null=True, blank=True, help_text="Fecha del último mantenimiento"
    )

    next_maintenance_date = models.DateField(
        null=True, blank=True, help_text="Fecha del próximo mantenimiento"
    )

    notes = models.TextField(blank=True, help_text="Notas adicionales del dispositivo")

    class Meta:
        verbose_name = "Dispositivo IoT"
        verbose_name_plural = "Dispositivos IoT"
        indexes = [
            models.Index(fields=["device_id"]),
            models.Index(fields=["catchment_point", "status"]),
            models.Index(fields=["equipment_model"]),
            models.Index(fields=["last_seen"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.device_id})"

    def is_online(self):
        """Check if device is considered online"""
        if not self.last_seen:
            return False

        # Consider online if seen within last 2x publish interval
        max_age = timedelta(minutes=self.mqtt_publish_interval * 2)
        return timezone.now() - self.last_seen < max_age

    def update_status_from_data(self, data):
        """Update device status based on received data"""
        self.last_seen = timezone.now()

        if "battery" in data:
            self.battery_level = data["battery"]

        if "signal" in data:
            self.signal_strength = data["signal"]

        # Determine status
        if self.battery_level and self.battery_level < 10:
            self.status = "BATTERY_LOW"
        elif data.get("error"):
            self.status = "ERROR"
        else:
            self.status = "ONLINE"

        self.save()


class MQTTConnection(ModelApi):
    """
    Conexiones MQTT activas y su estado
    """

    provider = models.ForeignKey(
        EquipmentProvider,
        on_delete=models.CASCADE,
        related_name="mqtt_connections",
        help_text="Proveedor para esta conexión MQTT",
    )

    connection_name = models.CharField(
        max_length=100, help_text="Nombre descriptivo de la conexión"
    )

    # Connection details
    broker_host = models.CharField(max_length=255, help_text="Host del broker MQTT")

    broker_port = models.PositiveIntegerField(
        default=1883,
        validators=[MinValueValidator(1), MaxValueValidator(65535)],
        help_text="Puerto del broker MQTT",
    )

    username = models.CharField(max_length=100, blank=True, help_text="Usuario MQTT")

    password = models.CharField(max_length=255, blank=True, help_text="Contraseña MQTT")

    use_tls = models.BooleanField(default=False, help_text="Usar TLS/SSL")

    client_id = models.CharField(
        max_length=100, unique=True, help_text="Client ID único para esta conexión"
    )

    # Topics
    subscribe_topics = models.JSONField(
        default=list,
        blank=True,
        help_text="Topics a los que suscribirse",
    )

    publish_topic_prefix = models.CharField(
        max_length=255, blank=True, help_text="Prefijo para topics de publicación"
    )

    # Status
    CONNECTION_STATUS_CHOICES = [
        ("DISCONNECTED", "Desconectado"),
        ("CONNECTING", "Conectando"),
        ("CONNECTED", "Conectado"),
        ("ERROR", "Error"),
    ]

    status = models.CharField(
        max_length=15,
        choices=CONNECTION_STATUS_CHOICES,
        default="DISCONNECTED",
        help_text="Estado de la conexión",
    )

    last_connected = models.DateTimeField(
        null=True, blank=True, help_text="Última vez que se conectó exitosamente"
    )

    last_disconnected = models.DateTimeField(
        null=True, blank=True, help_text="Última vez que se desconectó"
    )

    connection_errors = models.PositiveIntegerField(
        default=0, help_text="Número de errores de conexión consecutivos"
    )

    # Monitoring
    messages_received_today = models.PositiveIntegerField(
        default=0, help_text="Mensajes recibidos hoy"
    )

    messages_sent_today = models.PositiveIntegerField(
        default=0, help_text="Mensajes enviados hoy"
    )

    bytes_received_today = models.PositiveBigIntegerField(
        default=0, help_text="Bytes recibidos hoy"
    )

    # Configuration
    reconnect_interval = models.PositiveIntegerField(
        default=30, help_text="Intervalo de reconexión en segundos"
    )

    keep_alive_interval = models.PositiveIntegerField(
        default=60, help_text="Intervalo keep-alive en segundos"
    )

    is_active = models.BooleanField(default=True, help_text="Conexión activa")

    class Meta:
        verbose_name = "Conexión MQTT"
        verbose_name_plural = "Conexiones MQTT"
        indexes = [
            models.Index(fields=["provider", "status"]),
            models.Index(fields=["client_id"]),
            models.Index(fields=["is_active", "status"]),
        ]

    def __str__(self):
        return f"{self.connection_name} ({self.provider.name}) - {self.status}"

    def reset_daily_stats(self):
        """Reset daily statistics counters"""
        self.messages_received_today = 0
        self.messages_sent_today = 0
        self.bytes_received_today = 0
        self.save(
            update_fields=[
                "messages_received_today",
                "messages_sent_today",
                "bytes_received_today",
            ]
        )


class MQTTMessageLog(ModelApi):
    """
    Log de mensajes MQTT para debugging y auditoría
    """

    connection = models.ForeignKey(
        MQTTConnection,
        on_delete=models.CASCADE,
        related_name="message_logs",
        help_text="Conexión MQTT relacionada",
    )

    device = models.ForeignKey(
        IoTDevice,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="mqtt_messages",
        help_text="Dispositivo que envió el mensaje",
    )

    MESSAGE_TYPE_CHOICES = [
        ("PUBLISH", "Publicación"),
        ("SUBSCRIBE", "Suscripción"),
        ("CONNECT", "Conexión"),
        ("DISCONNECT", "Desconexión"),
        ("ERROR", "Error"),
    ]

    message_type = models.CharField(
        max_length=15, choices=MESSAGE_TYPE_CHOICES, help_text="Tipo de mensaje"
    )

    topic = models.CharField(max_length=500, help_text="Topic MQTT")

    payload = JSONField(help_text="Contenido del mensaje")

    qos = models.PositiveIntegerField(
        default=0,
        validators=[MaxValueValidator(2)],
        help_text="QoS del mensaje (0, 1, 2)",
    )

    retained = models.BooleanField(default=False, help_text="Mensaje retenido")

    # Processing info
    processed_successfully = models.BooleanField(
        default=False, help_text="Mensaje procesado exitosamente"
    )

    processing_error = models.TextField(
        blank=True, help_text="Error de procesamiento si ocurrió"
    )

    processing_time_ms = models.PositiveIntegerField(
        null=True, blank=True, help_text="Tiempo de procesamiento en ms"
    )

    class Meta:
        verbose_name = "Log de Mensaje MQTT"
        verbose_name_plural = "Logs de Mensajes MQTT"
        indexes = [
            models.Index(fields=["connection", "created"]),
            models.Index(fields=["device", "created"]),
            models.Index(fields=["message_type", "processed_successfully"]),
            models.Index(fields=["created"]),
        ]

    def __str__(self):
        return f"{self.message_type} - {self.topic} ({self.created})"


class DeviceMaintenanceSchedule(ModelApi):
    """
    Programación de mantenimiento para dispositivos
    """

    device = models.ForeignKey(
        IoTDevice,
        on_delete=models.CASCADE,
        related_name="maintenance_schedules",
        help_text="Dispositivo a mantener",
    )

    MAINTENANCE_TYPE_CHOICES = [
        ("ROUTINE", "Mantenimiento rutinario"),
        ("BATTERY_REPLACEMENT", "Reemplazo de batería"),
        ("SOFTWARE_UPDATE", "Actualización de software"),
        ("CALIBRATION", "Calibración"),
        ("REPAIR", "Reparación"),
        ("REPLACEMENT", "Reemplazo"),
    ]

    maintenance_type = models.CharField(
        max_length=20,
        choices=MAINTENANCE_TYPE_CHOICES,
        help_text="Tipo de mantenimiento",
    )

    scheduled_date = models.DateField(
        help_text="Fecha programada para el mantenimiento"
    )

    estimated_duration_hours = models.DecimalField(
        max_digits=4, decimal_places=1, help_text="Duración estimada en horas"
    )

    # Assignment
    assigned_technician = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_maintenance",
        help_text="Técnico asignado",
    )

    # Status
    STATUS_CHOICES = [
        ("SCHEDULED", "Programado"),
        ("IN_PROGRESS", "En progreso"),
        ("COMPLETED", "Completado"),
        ("CANCELLED", "Cancelado"),
        ("POSTPONED", "Pospuesto"),
    ]

    status = models.CharField(
        max_length=15,
        choices=STATUS_CHOICES,
        default="SCHEDULED",
        help_text="Estado del mantenimiento",
    )

    # Completion details
    actual_start_date = models.DateTimeField(
        null=True, blank=True, help_text="Fecha y hora de inicio real"
    )

    actual_completion_date = models.DateTimeField(
        null=True, blank=True, help_text="Fecha y hora de finalización real"
    )

    actual_duration_hours = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        null=True,
        blank=True,
        help_text="Duración real en horas",
    )

    # Work details
    work_performed = models.TextField(blank=True, help_text="Trabajo realizado")

    parts_replaced = models.JSONField(
        default=list, blank=True, help_text="Piezas reemplazadas"
    )

    issues_found = models.TextField(blank=True, help_text="Problemas encontrados")

    recommendations = models.TextField(
        blank=True, help_text="Recomendaciones para el futuro"
    )

    # Costs
    labor_cost = models.DecimalField(
        max_digits=10, decimal_places=2, default=0, help_text="Costo de mano de obra"
    )

    parts_cost = models.DecimalField(
        max_digits=10, decimal_places=2, default=0, help_text="Costo de piezas"
    )

    total_cost = models.DecimalField(
        max_digits=10, decimal_places=2, default=0, help_text="Costo total"
    )

    class Meta:
        verbose_name = "Programación de Mantenimiento"
        verbose_name_plural = "Programaciones de Mantenimiento"
        indexes = [
            models.Index(fields=["device", "scheduled_date"]),
            models.Index(fields=["assigned_technician", "status"]),
            models.Index(fields=["status", "scheduled_date"]),
        ]

    def __str__(self):
        return f"{self.device.name} - {self.maintenance_type} ({self.scheduled_date})"


class SystemMetrics(ModelApi):
    """
    Métricas de sistema para monitoreo avanzado
    """

    metric_name = models.CharField(max_length=100, help_text="Nombre de la métrica")

    metric_category = models.CharField(
        max_length=50,
        choices=[
            ("PERFORMANCE", "Performance"),
            ("TELEMETRY", "Telemetría"),
            ("MQTT", "MQTT"),
            ("DATABASE", "Base de datos"),
            ("SYSTEM", "Sistema"),
        ],
        help_text="Categoría de la métrica",
    )

    value_numeric = models.DecimalField(
        max_digits=15,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Valor numérico de la métrica",
    )

    value_text = models.TextField(blank=True, help_text="Valor textual de la métrica")

    unit = models.CharField(
        max_length=20, blank=True, help_text="Unidad de medida (ms, %, MB, etc.)"
    )

    tags = JSONField(default=dict, help_text="Tags adicionales para categorización")

    collected_at = models.DateTimeField(help_text="Cuándo se recolectó la métrica")

    class Meta:
        verbose_name = "Métrica del Sistema"
        verbose_name_plural = "Métricas del Sistema"
        ordering = ["-collected_at"]
        indexes = [
            models.Index(fields=["metric_name", "collected_at"]),
            models.Index(fields=["metric_category", "collected_at"]),
            models.Index(fields=["collected_at"]),
        ]

    def __str__(self):
        return (
            f"{self.metric_name}: {self.value_numeric or self.value_text} {self.unit}"
        )


class AlertRule(ModelApi):
    """
    Reglas avanzadas de alertas con lógica compleja
    """

    name = models.CharField(max_length=100, help_text="Nombre de la regla de alerta")

    description = models.TextField(blank=True, help_text="Descripción de la regla")

    # Scope
    SCOPE_CHOICES = [
        ("SYSTEM", "Sistema completo"),
        ("CLIENT", "Cliente específico"),
        ("PROJECT", "Proyecto específico"),
        ("POINT", "Punto específico"),
        ("DEVICE", "Dispositivo específico"),
    ]

    scope = models.CharField(
        max_length=15,
        choices=SCOPE_CHOICES,
        default="SYSTEM",
        help_text="Alcance de la regla",
    )

    # Target objects (depending on scope)
    target_client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="alert_rules",
        help_text="Cliente objetivo (si scope=CLIENT)",
    )

    target_project = models.ForeignKey(
        "core.ProjectCatchments",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="alert_rules",
        help_text="Proyecto objetivo (si scope=PROJECT)",
    )

    target_point = models.ForeignKey(
        CatchmentPoint,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="alert_rules",
        help_text="Punto objetivo (si scope=POINT)",
    )

    target_device = models.ForeignKey(
        IoTDevice,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="alert_rules",
        help_text="Dispositivo objetivo (si scope=DEVICE)",
    )

    # Alert logic
    CONDITION_CHOICES = [
        ("THRESHOLD", "Umbral simple"),
        ("TREND", "Tendencia"),
        ("PATTERN", "Patrón"),
        ("COMPLEX", "Lógica compleja"),
    ]

    condition_type = models.CharField(
        max_length=15,
        choices=CONDITION_CHOICES,
        default="THRESHOLD",
        help_text="Tipo de condición",
    )

    condition_config = JSONField(
        default=dict, help_text="Configuración de la condición (JSON)"
    )

    # Action
    ACTION_CHOICES = [
        ("EMAIL", "Enviar email"),
        ("SMS", "Enviar SMS"),
        ("NOTIFICATION", "Crear notificación"),
        ("WEBHOOK", "Llamar webhook"),
        ("COMMAND", "Ejecutar comando"),
    ]

    action_type = models.CharField(
        max_length=15, choices=ACTION_CHOICES, help_text="Tipo de acción"
    )

    action_config = JSONField(
        default=dict, help_text="Configuración de la acción (JSON)"
    )

    # Scheduling
    is_active = models.BooleanField(default=True, help_text="Regla activa")

    check_interval_minutes = models.PositiveIntegerField(
        default=60, help_text="Intervalo de verificación en minutos"
    )

    last_checked = models.DateTimeField(
        null=True, blank=True, help_text="Última vez que se verificó la regla"
    )

    last_triggered = models.DateTimeField(
        null=True, blank=True, help_text="Última vez que se activó la regla"
    )

    trigger_count = models.PositiveIntegerField(
        default=0, help_text="Número de veces que se ha activado"
    )

    # Cooldown to prevent spam
    cooldown_minutes = models.PositiveIntegerField(
        default=60, help_text="Tiempo de cooldown entre activaciones"
    )

    class Meta:
        verbose_name = "Regla de Alerta"
        verbose_name_plural = "Reglas de Alertas"
        indexes = [
            models.Index(fields=["scope", "is_active"]),
            models.Index(fields=["is_active", "last_checked"]),
            models.Index(fields=["last_triggered"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.scope})"

    def can_trigger(self):
        """Check if rule can trigger based on cooldown"""
        if not self.last_triggered:
            return True

        cooldown_period = timedelta(minutes=self.cooldown_minutes)
        return timezone.now() - self.last_triggered > cooldown_period
