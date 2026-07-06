"""Device and hardware inventory models for void."""
from django.db import models

from .base import VoidModel


class Device(VoidModel):
    """Dispositivo de telemetría asociado a un punto."""

    point = models.OneToOneField(
        "Point",
        on_delete=models.CASCADE,
        related_name="device",
        verbose_name="Punto",
    )
    provider = models.ForeignKey(
        "void.Provider",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="devices",
        verbose_name="Proveedor de telemetría",
    )
    external_id = models.CharField(
        max_length=300,
        blank=True,
        default="",
        verbose_name="ID externo",
        help_text="ID del dispositivo en la plataforma del proveedor.",
    )
    serial_number = models.CharField(
        max_length=300,
        blank=True,
        default="",
        verbose_name="Número de serie",
    )
    model = models.CharField(
        max_length=300,
        blank=True,
        default="",
        verbose_name="Modelo",
    )
    firmware_version = models.CharField(
        max_length=200,
        blank=True,
        default="",
        verbose_name="Firmware",
    )
    configuration = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Configuración",
        help_text='Variables, offsets y factores. Ej: {"pulses_factor": 1000, "variables": ["pulses", "nivel"]}',
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Activo",
        db_index=True,
    )
    activated_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name="Fecha de activación",
    )

    class Meta:
        verbose_name = "Dispositivo (void)"
        verbose_name_plural = "Dispositivos (void)"
        indexes = [
            models.Index(fields=["provider", "is_active"]),
            models.Index(fields=["external_id"]),
        ]

    def __str__(self):
        return f"{self.model or 'Device'} {self.serial_number or self.external_id or self.id}"


class DeviceHardware(VoidModel):
    """Inventario de hardware asociado a un device."""

    COMPONENT_CHOICES = [
        ("logger", "Logger / Datalogger"),
        ("sensor_flow", "Sensor de caudal"),
        ("sensor_level", "Sensor de nivel"),
        ("antenna", "Antena"),
        ("battery", "Batería"),
        ("solar_panel", "Panel solar"),
        ("modem", "Módem"),
        ("other", "Otro"),
    ]

    STATUS_CHOICES = [
        ("active", "Activo"),
        ("replaced", "Reemplazado"),
        ("decommissioned", "Dado de baja"),
        ("spare", "Repuesto"),
    ]

    device = models.ForeignKey(
        Device,
        on_delete=models.CASCADE,
        related_name="hardware",
        verbose_name="Dispositivo",
    )
    component_type = models.CharField(
        max_length=30,
        choices=COMPONENT_CHOICES,
        verbose_name="Tipo de componente",
        db_index=True,
    )
    serial = models.CharField(
        max_length=300,
        blank=True,
        default="",
        verbose_name="Número de serie",
    )
    model = models.CharField(
        max_length=300,
        blank=True,
        default="",
        verbose_name="Modelo",
    )
    manufacturer = models.CharField(
        max_length=300,
        blank=True,
        default="",
        verbose_name="Fabricante",
    )
    installation_date = models.DateField(
        blank=True,
        null=True,
        verbose_name="Fecha de instalación",
    )
    warranty_until = models.DateField(
        blank=True,
        null=True,
        verbose_name="Garantía hasta",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="active",
        verbose_name="Estado",
        db_index=True,
    )
    notes = models.TextField(
        blank=True,
        default="",
        verbose_name="Notas",
    )

    class Meta:
        verbose_name = "Componente de hardware"
        verbose_name_plural = "Componentes de hardware"
        indexes = [
            models.Index(fields=["device", "component_type", "status"]),
            models.Index(fields=["warranty_until", "status"]),
        ]

    def __str__(self):
        return f"{self.get_component_type_display()} {self.serial or self.model or self.id}"


class DeviceVariableConfig(VoidModel):
    """Configuración de procesamiento para cada variable que envía un logger.

    Permite que el mismo proveedor (p. ej. Novus) tenga escalas distintas
    (10, 100, 1000) por punto, y que lleguen variables nuevas sin romper el
    sistema: se crean inactivas hasta que un operador las clasifique.
    """

    PROCESSING_TYPE_CHOICES = [
        ("stateful", "Stateful rules (motor de reglas con memoria)"),
        ("formula", "Fórmula configurable"),
        ("passthrough", "Paso directo (sin transformar)"),
        ("none", "Sin clasificar"),
    ]

    device = models.ForeignKey(
        Device,
        on_delete=models.CASCADE,
        related_name="variable_configs",
        verbose_name="Dispositivo",
    )
    source_variable = models.CharField(
        max_length=80,
        verbose_name="Variable del logger",
        help_text="Nombre original que envía el logger/proveedor (ej: '5000', 'flow', 'lvl').",
        db_index=True,
    )
    internal_variable = models.CharField(
        max_length=40,
        verbose_name="Variable interna",
        help_text="Tipo genérico dentro del sistema.",
    )
    processing_type = models.CharField(
        max_length=20,
        choices=PROCESSING_TYPE_CHOICES,
        default="none",
        verbose_name="Tipo de procesamiento",
        db_index=True,
    )
    pulses_factor = models.IntegerField(
        default=1000,
        verbose_name="Factor de pulsos",
        help_text="Solo aplica a totalizador: (pulsos * factor) / 1000 = m³.",
    )
    offset = models.DecimalField(
        max_digits=15,
        decimal_places=3,
        default=0,
        verbose_name="Offset",
        help_text="Suma fija al resultado (m³, metros, etc.).",
    )
    scale = models.DecimalField(
        max_digits=15,
        decimal_places=6,
        default=1,
        verbose_name="Escala",
        help_text="Factor multiplicador/divisor para convertir unidades del proveedor.",
    )
    max_diff_m3_per_hour = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=500,
        verbose_name="Máx diff m³/hora",
        help_text="Umbral anti-salto masivo (solo totalizador).",
    )
    reconnection_threshold_hours = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=2,
        verbose_name="Umbral reconexión (horas)",
        help_text="Gap que se considera reconexión legítima (solo totalizador).",
    )
    compute_flow = models.BooleanField(
        default=False,
        verbose_name="Calcular caudal derivado",
        help_text="Solo para totalizadores stateful: calcula caudal promedio (L/s) como derivada del total.",
    )
    unit = models.CharField(
        max_length=20,
        blank=True,
        default="",
        verbose_name="Unidad",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Activa",
        db_index=True,
    )
    display_name = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="Nombre visible",
    )
    output_field = models.CharField(
        max_length=40,
        blank=True,
        default="",
        verbose_name="Campo de salida",
        help_text="Nombre del campo donde se guarda el resultado (ej: flow, nivel, ph). "
                  "Si está vacío, usa internal_variable.",
    )
    formula = models.CharField(
        max_length=500,
        blank=True,
        default="",
        verbose_name="Fórmula",
        help_text="Fórmula Python segura. Variables disponibles: value, scale, offset, "
                  "y constantes del punto (d1, d2, d3, etc.).",
    )
    custom_schema = models.ForeignKey(
        "void.ProcessingSchema",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="variable_configs",
        verbose_name="Schema stateful",
        help_text="Schema declarativo propio de esta variable. Usado cuando processing_type='stateful'.",
    )
    extra_data = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Datos extra",
        help_text="Configuración adicional específica de la variable (ej: calculate_nivel).",
    )

    class Meta:
        verbose_name = "Configuración de variable"
        verbose_name_plural = "Configuraciones de variables"
        unique_together = ("device", "source_variable")
        indexes = [
            models.Index(fields=["device", "processing_type", "is_active"]),
        ]

    def __str__(self):
        return f"{self.device} | {self.source_variable} → {self.processing_type}"
