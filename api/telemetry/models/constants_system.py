"""
Sistema Avanzado de Constantes Históricas
Permite definir constantes por rangos de fechas y editar data histórica
"""

import logging
from datetime import timedelta

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from api.telemetry.models.catchment_points import CatchmentPoint
from api.telemetry.models.management_super import IoTDevice
from api.core.models.users import User
from api.core.models.utils import ModelApi

logger = logging.getLogger(__name__)


class ConstantDefinition(ModelApi):
    """
    Definición de constantes aplicables por rangos de tiempo
    Reemplaza el sistema simple de 'addition' con uno histórico completo
    """

    name = models.CharField(
        max_length=100, help_text="Nombre descriptivo de la constante"
    )

    code = models.CharField(
        max_length=50, unique=True, help_text="Código único de la constante"
    )

    description = models.TextField(blank=True, help_text="Descripción detallada")

    # Asociación - puede aplicarse a diferentes niveles
    device = models.ForeignKey(
        IoTDevice,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="constants",
        help_text="Dispositivo específico (opcional)",
    )

    point = models.ForeignKey(
        CatchmentPoint,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="constants",
        help_text="Punto de captación (opcional)",
    )

    # Si no se especifica device ni point, es global para el sistema
    # Si se especifica point pero no device, aplica a todos los devices del point
    # Si se especifica device, solo aplica a ese device

    # Tipo de constante
    CONSTANT_TYPES = [
        ("TOTALIZER_OFFSET", "Offset de Totalizador"),
        ("FLOW_MULTIPLIER", "Multiplicador de Caudal"),
        ("LEVEL_OFFSET", "Offset de Nivel"),
        ("BATTERY_CALIBRATION", "Calibración de Batería"),
        ("CONVERSION_FACTOR", "Factor de Conversión"),
        ("CUSTOM", "Personalizada"),
    ]

    constant_type = models.CharField(
        max_length=20,
        choices=CONSTANT_TYPES,
        default="TOTALIZER_OFFSET",
        help_text="Tipo de constante",
    )

    # Valor de la constante
    value_numeric = models.DecimalField(
        max_digits=15, decimal_places=6, help_text="Valor numérico de la constante"
    )

    value_text = models.TextField(blank=True, help_text="Valor textual si aplica")

    # Unidad
    unit = models.CharField(max_length=20, blank=True, help_text="Unidad de medida")

    # Aplicación temporal
    is_active = models.BooleanField(default=True, help_text="Constante activa")

    # Prioridad (para resolver conflictos cuando múltiples constantes aplican)
    priority = models.PositiveIntegerField(
        default=100, help_text="Prioridad (mayor número = mayor prioridad)"
    )

    # Metadata
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_constants",
        help_text="Usuario que creó la constante",
    )

    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_constants",
        help_text="Usuario que aprobó la constante",
    )

    approval_date = models.DateTimeField(
        null=True, blank=True, help_text="Fecha de aprobación"
    )

    tags = models.JSONField(
        default=list,
        blank=True,
        help_text="Tags para categorización",
    )

    custom_metadata = models.JSONField(default=dict, help_text="Metadata personalizada")

    class Meta:
        verbose_name = "Definición de Constante"
        verbose_name_plural = "Definiciones de Constantes"
        indexes = [
            models.Index(fields=["constant_type", "is_active"]),
            models.Index(fields=["device", "point", "constant_type"]),
            models.Index(fields=["priority", "is_active"]),
            models.Index(fields=["code"]),
        ]

    def __str__(self):
        scope = []
        if self.device:
            scope.append(f"Device: {self.device.name}")
        elif self.point:
            scope.append(f"Point: {self.point.title}")
        else:
            scope.append("Global")

        return f"{self.name} ({', '.join(scope)}) = {self.value_numeric}"


class ConstantApplication(ModelApi):
    """
    Aplicación temporal de constantes - define CUÁNDO aplica cada constante
    """

    constant = models.ForeignKey(
        ConstantDefinition,
        on_delete=models.CASCADE,
        related_name="applications",
        help_text="Constante que se aplica",
    )

    # Rango temporal de aplicación
    start_date = models.DateTimeField(help_text="Fecha y hora de inicio de aplicación")

    end_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Fecha y hora de fin de aplicación (null = indefinido)",
    )

    # Estado
    is_active = models.BooleanField(default=True, help_text="Aplicación activa")

    # Motivo del cambio
    change_reason = models.TextField(help_text="Motivo del cambio de constante")

    # Valores antes/después para auditoría
    previous_value = models.DecimalField(
        max_digits=15,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Valor anterior de la constante",
    )

    new_value = models.DecimalField(
        max_digits=15, decimal_places=6, help_text="Nuevo valor de la constante"
    )

    # Usuario que aplicó el cambio
    applied_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="applied_constant_changes",
        help_text="Usuario que aplicó el cambio",
    )

    # Aprobación si aplica
    requires_approval = models.BooleanField(
        default=False, help_text="Requiere aprobación antes de aplicar"
    )

    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_constant_applications",
        help_text="Usuario que aprobó la aplicación",
    )

    approval_date = models.DateTimeField(
        null=True, blank=True, help_text="Fecha de aprobación"
    )

    # Recálculo automático
    auto_recalculate = models.BooleanField(
        default=True, help_text="Recalcular automáticamente datos históricos"
    )

    recalculation_status = models.CharField(
        max_length=20,
        choices=[
            ("PENDING", "Pendiente"),
            ("IN_PROGRESS", "En Progreso"),
            ("COMPLETED", "Completado"),
            ("FAILED", "Falló"),
        ],
        default="PENDING",
        help_text="Estado del recálculo",
    )

    # Resultados del recálculo
    records_affected = models.PositiveIntegerField(
        default=0, help_text="Número de registros afectados por el cambio"
    )

    recalculation_errors = models.TextField(
        blank=True, help_text="Errores durante el recálculo"
    )

    class Meta:
        verbose_name = "Aplicación de Constante"
        verbose_name_plural = "Aplicaciones de Constantes"
        indexes = [
            models.Index(fields=["constant", "start_date"]),
            models.Index(fields=["start_date", "end_date"]),
            models.Index(fields=["is_active", "start_date"]),
            models.Index(fields=["recalculation_status"]),
        ]
        ordering = ["-start_date"]

    def __str__(self):
        return f"{self.constant.name}: {self.start_date.date()} - {self.end_date.date() if self.end_date else '∞'}"

    def is_currently_active(self):
        """Verifica si esta aplicación está actualmente activa"""
        now = timezone.now()
        return (
            self.is_active
            and self.start_date <= now
            and (self.end_date is None or self.end_date >= now)
        )

    def get_affected_date_range(self):
        """Obtiene el rango de fechas afectado por este cambio"""
        # Buscar la aplicación anterior para determinar el rango real afectado
        previous_application = (
            ConstantApplication.objects.filter(
                constant=self.constant, start_date__lt=self.start_date
            )
            .order_by("-start_date")
            .first()
        )

        if previous_application:
            affected_start = max(previous_application.start_date, self.start_date)
        else:
            affected_start = self.start_date

        affected_end = self.end_date if self.end_date else timezone.now()

        return affected_start, affected_end


class DataCorrectionLog(ModelApi):
    """
    Log de correcciones manuales de datos históricos
    """

    # Registro original
    original_record = models.ForeignKey(
        "core.DataPoint",
        on_delete=models.CASCADE,
        related_name="corrections",
        help_text="Registro original que fue corregido",
    )

    # Valores antes de corrección
    original_raw_value = models.TextField(help_text="Valor raw original")

    original_processed_value = models.DecimalField(
        max_digits=20,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Valor procesado original",
    )

    # Valores después de corrección
    corrected_raw_value = models.TextField(blank=True, help_text="Valor raw corregido")

    corrected_processed_value = models.DecimalField(
        max_digits=20,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Valor procesado corregido",
    )

    # Razón de la corrección
    CORRECTION_TYPES = [
        ("MANUAL_EDIT", "Edición Manual"),
        ("CONSTANT_CHANGE", "Cambio de Constante"),
        ("CALIBRATION", "Calibración"),
        ("ERROR_CORRECTION", "Corrección de Error"),
        ("DATA_RECOVERY", "Recuperación de Datos"),
        ("QUALITY_IMPROVEMENT", "Mejora de Calidad"),
    ]

    correction_type = models.CharField(
        max_length=20, choices=CORRECTION_TYPES, help_text="Tipo de corrección aplicada"
    )

    correction_reason = models.TextField(help_text="Razón detallada de la corrección")

    # Usuario que realizó la corrección
    corrected_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="data_corrections",
        help_text="Usuario que realizó la corrección",
    )

    # Metadata de la corrección
    correction_metadata = models.JSONField(
        default=dict, help_text="Metadata adicional de la corrección"
    )

    # Impacto de la corrección
    affected_downstream_data = models.PositiveIntegerField(
        default=0, help_text="Número de registros downstream afectados"
    )

    class Meta:
        verbose_name = "Log de Corrección de Datos"
        verbose_name_plural = "Logs de Corrección de Datos"
        indexes = [
            models.Index(fields=["original_record", "created"]),
            models.Index(fields=["corrected_by", "created"]),
            models.Index(fields=["correction_type"]),
        ]

    def __str__(self):
        return f"Correction: {self.original_record} ({self.correction_type})"


class ProviderDataSync(ModelApi):
    """
    Sincronización automática de datos con proveedores
    """

    provider = models.ForeignKey(
        "EquipmentProvider",
        on_delete=models.CASCADE,
        related_name="data_syncs",
        help_text="Proveedor con el que sincronizar",
    )

    # Configuración de sincronización
    SYNC_TYPES = [
        ("FULL_HISTORICAL", "Histórica Completa"),
        ("INCREMENTAL", "Incremental"),
        ("REALTIME", "Tiempo Real"),
        ("ON_DEMAND", "Bajo Demanda"),
    ]

    sync_type = models.CharField(
        max_length=15,
        choices=SYNC_TYPES,
        default="INCREMENTAL",
        help_text="Tipo de sincronización",
    )

    # Estado y scheduling
    is_active = models.BooleanField(default=True, help_text="Sincronización activa")

    sync_interval_minutes = models.PositiveIntegerField(
        default=60, help_text="Intervalo de sincronización en minutos"
    )

    last_sync_attempt = models.DateTimeField(
        null=True, blank=True, help_text="Último intento de sincronización"
    )

    last_successful_sync = models.DateTimeField(
        null=True, blank=True, help_text="Última sincronización exitosa"
    )

    # Estadísticas
    total_records_synced = models.PositiveIntegerField(
        default=0, help_text="Total de registros sincronizados"
    )

    last_sync_records = models.PositiveIntegerField(
        default=0, help_text="Registros en la última sincronización"
    )

    # Estado actual
    SYNC_STATUS = [
        ("IDLE", "Inactivo"),
        ("RUNNING", "Ejecutándose"),
        ("SUCCESS", "Éxito"),
        ("PARTIAL_SUCCESS", "Éxito Parcial"),
        ("FAILED", "Falló"),
        ("CANCELLED", "Cancelado"),
    ]

    current_status = models.CharField(
        max_length=15,
        choices=SYNC_STATUS,
        default="IDLE",
        help_text="Estado actual de sincronización",
    )

    # Configuración específica del proveedor
    sync_config = models.JSONField(
        default=dict, help_text="Configuración específica para este proveedor"
    )

    # Logs de errores
    last_error_message = models.TextField(
        blank=True, help_text="Último mensaje de error"
    )

    consecutive_failures = models.PositiveIntegerField(
        default=0, help_text="Fallos consecutivos"
    )

    class Meta:
        verbose_name = "Sincronización con Proveedor"
        verbose_name_plural = "Sincronizaciones con Proveedores"
        indexes = [
            models.Index(fields=["provider", "is_active"]),
            models.Index(fields=["current_status", "last_sync_attempt"]),
            models.Index(fields=["sync_type", "is_active"]),
        ]

    def __str__(self):
        return f"Sync {self.provider.name}: {self.sync_type} ({self.current_status})"

    def can_run_sync(self):
        """Verifica si se puede ejecutar una sincronización"""
        if not self.is_active:
            return False

        if self.current_status == "RUNNING":
            return False

        # Verificar intervalo mínimo
        if self.last_sync_attempt:
            min_interval = timedelta(minutes=self.sync_interval_minutes)
            return timezone.now() - self.last_sync_attempt >= min_interval

        return True

    def update_sync_status(self, status, records_synced=0, error_message=None):
        """Actualiza el estado de sincronización"""
        self.current_status = status
        self.last_sync_attempt = timezone.now()

        if status in ["SUCCESS", "PARTIAL_SUCCESS"]:
            self.last_successful_sync = timezone.now()
            self.last_sync_records = records_synced
            self.total_records_synced += records_synced
            self.consecutive_failures = 0
            self.last_error_message = ""
        elif status == "FAILED":
            self.consecutive_failures += 1
            if error_message:
                self.last_error_message = error_message[:1000]  # Limitar tamaño

        self.save()
