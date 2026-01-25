"""
Infrastructure Models - Hardware físico (Fabricantes, Modelos, Dispositivos).

Este módulo gestiona el inventario de hardware. La configuración MQTT
se maneja en telemetry.providers.mqtt_models.
"""

import uuid
from django.db import models
from api.core.models.utils import ModelApi


def generate_device_token():
    """Genera un token único para dispositivos."""
    return uuid.uuid4().hex


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

    class Meta:
        verbose_name = "Modelo de Equipo"
        verbose_name_plural = "Modelos de Equipos"
        unique_together = ["manufacturer", "model_code"]

    def __str__(self):
        return f"{self.manufacturer.name} - {self.model_name}"


class Device(ModelApi):
    """IoT Device con campos dinámicos (igual que CatchmentPoint)."""

    device_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        help_text="ID único del dispositivo (generado automáticamente)",
    )
    name = models.CharField(
        max_length=100, help_text="Nombre descriptivo del dispositivo"
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
        ],
        default="OFFLINE",
        help_text="Estado actual del dispositivo",
    )

    last_seen = models.DateTimeField(null=True, blank=True)

    # Identificación para comunicación con proveedor
    imei = models.CharField(
        max_length=20,
        blank=True,
        help_text="IMEI del dispositivo (opcional)"
    )

    # Configuración de autenticación
    use_internal_mqtt = models.BooleanField(
        default=True,
        help_text="Si es True, usa MQTT interno y genera token automático. Si es False, usa proveedor externo."
    )
    token = models.CharField(
        max_length=255,
        unique=True,
        blank=True,
        help_text="Token para autenticación. Auto-generado si usa MQTT interno, manual si es proveedor externo."
    )

    # NUEVO: Campos dinámicos (igual que CatchmentPoint)
    configuration_scheme = models.ForeignKey(
        "telemetry.ConfigurationScheme",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="devices",
        verbose_name="Esquema de Configuración",
        help_text="Plantilla de configuración dinámica para este dispositivo"
    )

    class Meta:
        db_table = 'core_iotdevice'
        verbose_name = "Dispositivo IoT"
        verbose_name_plural = "Dispositivos IoT"

    def save(self, *args, **kwargs):
        """Genera token automático si usa MQTT interno y no tiene token."""
        if self.use_internal_mqtt and not self.token:
            self.token = generate_device_token()
        super().save(*args, **kwargs)

    def clean(self):
        """Validar configuración del dispositivo."""
        from django.core.exceptions import ValidationError

        # Si no usa MQTT interno, debe tener token manual
        if not self.use_internal_mqtt and not self.token:
            raise ValidationError({
                'token': 'Debe ingresar el token del proveedor externo.'
            })

    def __str__(self):
        return f"{self.name} ({self.device_id})"

    def get_config_dict(self) -> dict:
        """
        Obtiene todas las configuraciones del dispositivo como diccionario.
        Igual que CatchmentPoint.get_config_dict() para consistencia.

        Returns:
            Dict con formato {field_code: value}
        """
        return {
            cv.field.code: cv.value
            for cv in self.configuration_values.select_related('field')
        }


class DeviceConfigurationValue(ModelApi):
    """
    Valor de configuración para un dispositivo específico.
    Espejo de PointConfigurationValue pero para Device.
    """

    device = models.ForeignKey(
        Device,
        related_name='configuration_values',
        on_delete=models.CASCADE,
        verbose_name="Dispositivo"
    )
    field = models.ForeignKey(
        "telemetry.ConfigurationSchemeField",
        on_delete=models.CASCADE,
        verbose_name="Campo de Configuración"
    )
    value = models.JSONField(
        verbose_name="Valor",
        help_text="Valor de la configuración según el tipo de dato del campo"
    )

    class Meta:
        db_table = "infrastructure_deviceconfigurationvalue"
        verbose_name = "Valor de Configuración de Dispositivo"
        verbose_name_plural = "Valores de Configuración de Dispositivo"
        unique_together = ('device', 'field')

    def __str__(self):
        return f"{self.device.name} - {self.field.code}: {self.value}"



