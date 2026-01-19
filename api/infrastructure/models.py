"""
Infrastructure Models - IoT Devices and MQTT
"""

from datetime import timedelta
from django.db import models
from django.db.models import JSONField
from django.core.validators import MaxValueValidator, MinValueValidator
from django.utils import timezone
from api.core.models.utils import ModelApi
from api.core.models.users import User


class Manufacturer(ModelApi):
    """Manufacturer (renamed from EquipmentProvider)."""

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

    def __str__(self):
        return f"{self.name} ({self.code})"


class DeviceModel(ModelApi):
    """Device Model (renamed from EquipmentModel)."""

    manufacturer = models.ForeignKey(
        Manufacturer,
        on_delete=models.CASCADE,
        related_name="models",
        help_text="Proveedor del equipo",
    )
    model_name = models.CharField(max_length=100, help_text="Nombre del modelo")
    model_code = models.CharField(max_length=50, help_text="Código del modelo")
    description = models.TextField(blank=True, help_text="Descripción del modelo")

    is_active = models.BooleanField(default=True, help_text="Modelo activo")

    class Meta:
        verbose_name = "Modelo de Equipo"
        verbose_name_plural = "Modelos de Equipos"
        unique_together = ["manufacturer", "model_code"]

    def __str__(self):
        return f"{self.manufacturer.name} - {self.model_name}"


class Device(ModelApi):
    """IoT Device (renamed from IoTDevice)."""

    device_id = models.CharField(
        max_length=100,
        unique=True,
        help_text="ID único del dispositivo (MAC, Serial, etc.)",
    )
    name = models.CharField(
        max_length=100, help_text="Nombre descriptivo del dispositivo"
    )

    catchment_point = models.ForeignKey(
        "telemetry.CatchmentPoint",
        on_delete=models.CASCADE,
        related_name="devices",
        help_text="Punto de captación al que pertenece",
    )

    device_model = models.ForeignKey(
        DeviceModel,
        on_delete=models.PROTECT,
        related_name="devices",
        help_text="Modelo del equipo",
    )

    status = models.CharField(
        max_length=20,
        choices=[
            ("OFFLINE", "Offline"),
            ("ONLINE", "Online"),
            ("ERROR", "Error"),
            ("MAINTENANCE", "Mantenimiento"),
            ("BATTERY_LOW", "Batería baja"),
        ],
        default="OFFLINE",
        help_text="Estado actual del dispositivo",
    )

    last_seen = models.DateTimeField(null=True, blank=True)
    battery_level = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )

    class Meta:
        db_table = 'core_iotdevice'
        verbose_name = "Dispositivo IoT"
        verbose_name_plural = "Dispositivos IoT"

    def clean(self):
        """Validate device integrity."""
        from django.core.exceptions import ValidationError
        
        # Validación 1: Un dispositivo no puede estar en dos puntos al mismo tiempo
        # Si este dispositivo ya existe (self.pk) y se está cambiando de punto...
        # O si es nuevo.
        
        # Buscar otros dispositivos con el mismo device_id
        # (device_id ya es unique en DB, pero validamos lógica de negocio adicional si fuera necesario)
        pass

    def __str__(self):
        return f"{self.name} ({self.device_id})"


class Connection(ModelApi):
    """MQTT Connection (renamed from MQTTConnection)."""

    manufacturer = models.ForeignKey(
        Manufacturer,
        on_delete=models.CASCADE,
        related_name="connections",
    )
    connection_name = models.CharField(max_length=100)
    broker_host = models.CharField(max_length=255)
    broker_port = models.PositiveIntegerField(default=1883)
    username = models.CharField(max_length=100, blank=True)
    password = models.CharField(max_length=255, blank=True)
    client_id = models.CharField(max_length=100, unique=True)
    status = models.CharField(
        max_length=15,
        choices=[
            ("DISCONNECTED", "Desconectado"),
            ("CONNECTING", "Conectando"),
            ("CONNECTED", "Conectado"),
            ("ERROR", "Error"),
        ],
        default="DISCONNECTED",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Conexión MQTT"
        verbose_name_plural = "Conexiones MQTT"

    def __str__(self):
        return f"{self.connection_name} ({self.manufacturer.name})"
