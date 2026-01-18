"""
Modelos Mejorados para Almacenamiento Granular de Datos
Solución completa para gestión de variables, tickets de soporte y timestamps detallados
"""

import uuid
from datetime import timedelta

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import JSONField
from django.utils import timezone

from .catchment_points import CatchmentPoint
from .management_super import IoTDevice
from .users import User
from .utils import ModelApi

# ============================================================================
# GESTIÓN GRANULAR DE VARIABLES Y DATOS
# ============================================================================


class DataStream(ModelApi):
    """
    Stream de datos - Define qué tipo de datos se esperan de cada dispositivo
    Reemplaza el sistema limitado de Variables
    """

    name = models.CharField(
        max_length=100, help_text="Nombre descriptivo del stream de datos"
    )

    code = models.CharField(
        max_length=50, unique=True, help_text="Código único del stream"
    )

    description = models.TextField(
        blank=True, help_text="Descripción detallada del stream"
    )

    # Asociación flexible
    device = models.ForeignKey(
        IoTDevice,
        on_delete=models.CASCADE,
        related_name="data_streams",
        help_text="Dispositivo que genera este stream",
    )

    # Tipo de stream
    STREAM_TYPES = [
        ("TELEMETRY", "Telemetría"),
        ("DIAGNOSTIC", "Diagnóstico"),
        ("EVENT", "Evento"),
        ("COMMAND_RESPONSE", "Respuesta a Comando"),
        ("CONFIGURATION", "Configuración"),
        ("MAINTENANCE", "Mantenimiento"),
    ]

    stream_type = models.CharField(
        max_length=20,
        choices=STREAM_TYPES,
        default="TELEMETRY",
        help_text="Tipo de stream de datos",
    )

    # Configuración del stream
    is_active = models.BooleanField(default=True, help_text="Stream activo")

    sampling_rate_seconds = models.PositiveIntegerField(
        default=60, help_text="Frecuencia de muestreo en segundos"
    )

    retention_days = models.PositiveIntegerField(
        default=90, help_text="Días de retención de datos"
    )

    # Validación de datos
    validation_rules = JSONField(
        default=dict, help_text="Reglas de validación para los datos"
    )

    # Transformaciones
    transformations = JSONField(
        default=dict, help_text="Transformaciones aplicadas a los datos"
    )

    class Meta:
        verbose_name = "Stream de Datos"
        verbose_name_plural = "Streams de Datos"
        indexes = [
            models.Index(fields=["device", "stream_type", "is_active"]),
            models.Index(fields=["code"]),
            models.Index(fields=["is_active", "sampling_rate_seconds"]),
        ]
        unique_together = ["device", "code"]

    def __str__(self):
        return f"{self.device.name} - {self.name}"


class DataPoint(ModelApi):
    """
    Punto de dato granular - Almacena cada medición individual con metadata completa
    Reemplaza el sistema limitado de InteractionDetail para datos granulares
    """

    # ID único para trazabilidad
    data_point_id = models.UUIDField(
        default=uuid.uuid4, unique=True, help_text="ID único global del punto de dato"
    )

    # Asociación con stream
    stream = models.ForeignKey(
        DataStream,
        on_delete=models.CASCADE,
        related_name="data_points",
        help_text="Stream al que pertenece este punto de dato",
    )

    # Timestamps detallados
    collected_at = models.DateTimeField(
        help_text="Cuándo se recolectó el dato en el dispositivo"
    )

    received_at = models.DateTimeField(
        auto_now_add=True, help_text="Cuándo se recibió el dato en el servidor"
    )

    processed_at = models.DateTimeField(
        null=True, blank=True, help_text="Cuándo se procesó el dato"
    )

    # Calidad del dato
    DATA_QUALITY_CHOICES = [
        ("EXCELLENT", "Excelente"),
        ("GOOD", "Buena"),
        ("FAIR", "Regular"),
        ("POOR", "Mala"),
        ("INVALID", "Inválida"),
    ]

    quality = models.CharField(
        max_length=10,
        choices=DATA_QUALITY_CHOICES,
        default="GOOD",
        help_text="Calidad del dato recolectado",
    )

    # Valores - Flexibles y granulares
    raw_value = models.TextField(
        help_text="Valor raw sin procesar (como llega del dispositivo)"
    )

    processed_value = models.DecimalField(
        max_digits=20,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Valor procesado y convertido",
    )

    unit = models.CharField(
        max_length=20, blank=True, help_text="Unidad de medida del valor"
    )

    # Metadata del dato
    metadata = JSONField(default=dict, help_text="Metadata adicional del punto de dato")

    # Validación y procesamiento
    is_valid = models.BooleanField(
        default=True, help_text="Dato válido según reglas de validación"
    )

    validation_errors = models.JSONField(
        default=list,
        blank=True,
        help_text="Errores de validación encontrados",
    )

    # Procesamiento
    is_processed = models.BooleanField(default=False, help_text="Dato ya procesado")

    processing_attempts = models.PositiveIntegerField(
        default=0, help_text="Número de intentos de procesamiento"
    )

    # Flags de uso
    is_archived = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Dato archivado (para retención a largo plazo)",
    )

    # Relaciones para agregaciones rápidas
    device = models.ForeignKey(
        IoTDevice,
        on_delete=models.CASCADE,
        related_name="data_points",
        help_text="Dispositivo que generó el dato",
    )

    point = models.ForeignKey(
        CatchmentPoint,
        on_delete=models.CASCADE,
        related_name="granular_data_points",
        help_text="Punto de captación relacionado",
    )

    class Meta:
        verbose_name = "Punto de Dato"
        verbose_name_plural = "Puntos de Datos"
        indexes = [
            models.Index(fields=["stream", "collected_at"]),
            models.Index(fields=["device", "collected_at"]),
            models.Index(fields=["point", "collected_at"]),
            models.Index(fields=["is_valid", "is_processed"]),
            models.Index(fields=["quality", "collected_at"]),
            models.Index(fields=["is_archived", "collected_at"]),
            models.Index(fields=["received_at"]),
            models.Index(fields=["processed_at"]),
        ]
        unique_together = ["stream", "collected_at"]
        ordering = ["-collected_at"]

    def __str__(self):
        return f"{self.stream.name}: {self.raw_value} ({self.collected_at})"

    def save(self, *args, **kwargs):
        # Auto-set processed timestamp
        if self.is_processed and not self.processed_at:
            self.processed_at = timezone.now()

        super().save(*args, **kwargs)

    def get_value_for_unit(self, target_unit: str) -> float:
        """Convierte el valor a la unidad solicitada"""
        if not self.processed_value:
            return None

        # Implementar conversiones de unidades aquí
        # Por ejemplo: m3 -> L, C -> F, etc.
        return float(self.processed_value)


class VariableDefinition(ModelApi):
    """
    Definición granular de variables - Mucho más flexible que el modelo Variable actual
    """

    name = models.CharField(max_length=100, help_text="Nombre de la variable")

    code = models.CharField(
        max_length=50, unique=True, help_text="Código único de la variable"
    )

    description = models.TextField(blank=True, help_text="Descripción detallada")

    # Tipo de variable
    VARIABLE_TYPES = [
        ("NUMERIC", "Numérica"),
        ("TEXT", "Texto"),
        ("BOOLEAN", "Booleana"),
        ("JSON", "JSON"),
        ("BINARY", "Binaria"),
    ]

    variable_type = models.CharField(
        max_length=10,
        choices=VARIABLE_TYPES,
        default="NUMERIC",
        help_text="Tipo de dato de la variable",
    )

    # Unidad y conversión
    unit = models.CharField(
        max_length=20, blank=True, help_text="Unidad de medida estándar"
    )

    conversion_factor = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        default=1.0,
        help_text="Factor de conversión a unidad estándar",
    )

    conversion_offset = models.DecimalField(
        max_digits=10, decimal_places=6, default=0.0, help_text="Offset de conversión"
    )

    # Asociación con streams
    streams = models.ManyToManyField(
        DataStream,
        related_name="variables",
        help_text="Streams que incluyen esta variable",
    )

    # Validación
    min_value = models.DecimalField(
        max_digits=15,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Valor mínimo válido",
    )

    max_value = models.DecimalField(
        max_digits=15,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Valor máximo válido",
    )

    allowed_values = models.JSONField(
        default=list,
        blank=True,
        help_text="Valores permitidos (para variables categóricas)",
    )

    # Configuración
    is_required = models.BooleanField(
        default=False, help_text="Variable requerida en el stream"
    )

    default_value = models.TextField(blank=True, help_text="Valor por defecto")

    # Metadata
    tags = models.JSONField(
        default=list,
        blank=True,
        help_text="Tags para categorización",
    )

    custom_properties = JSONField(default=dict, help_text="Propiedades personalizadas")

    class Meta:
        verbose_name = "Definición de Variable"
        verbose_name_plural = "Definiciones de Variables"
        indexes = [
            models.Index(fields=["code"]),
            models.Index(fields=["variable_type"]),
            models.Index(fields=["is_required"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.code})"

    def validate_value(self, value) -> tuple[bool, list[str]]:
        """Valida si un valor cumple con las reglas de la variable"""
        errors = []

        if self.variable_type == "NUMERIC":
            try:
                num_value = float(value)
                if self.min_value is not None and num_value < self.min_value:
                    errors.append(
                        f"Valor {num_value} menor que mínimo {self.min_value}"
                    )
                if self.max_value is not None and num_value > self.max_value:
                    errors.append(
                        f"Valor {num_value} mayor que máximo {self.max_value}"
                    )
            except (ValueError, TypeError):
                errors.append("Valor no es numérico")

        if self.allowed_values and str(value) not in self.allowed_values:
            errors.append(
                f"Valor {value} no está en valores permitidos: {self.allowed_values}"
            )

        return len(errors) == 0, errors

    def convert_value(self, raw_value):
        """Convierte un valor raw usando las reglas de conversión"""
        if self.variable_type != "NUMERIC":
            return raw_value

        try:
            value = float(raw_value)
            converted = (value * float(self.conversion_factor)) + float(
                self.conversion_offset
            )
            return converted
        except (ValueError, TypeError):
            return raw_value


# ============================================================================
# GESTIÓN DE TICKETS DE SOPORTE
# ============================================================================


class SupportTicket(ModelApi):
    """
    Sistema completo de tickets de soporte
    """

    ticket_number = models.CharField(
        max_length=20, unique=True, help_text="Número único del ticket (auto-generado)"
    )

    title = models.CharField(max_length=200, help_text="Título descriptivo del ticket")

    description = models.TextField(help_text="Descripción detallada del problema")

    # Estado del ticket
    TICKET_STATUS = [
        ("OPEN", "Abierto"),
        ("IN_PROGRESS", "En Progreso"),
        ("WAITING_CUSTOMER", "Esperando Cliente"),
        ("WAITING_SUPPLIER", "Esperando Proveedor"),
        ("RESOLVED", "Resuelto"),
        ("CLOSED", "Cerrado"),
    ]

    status = models.CharField(
        max_length=20,
        choices=TICKET_STATUS,
        default="OPEN",
        help_text="Estado actual del ticket",
    )

    # Prioridad
    PRIORITY_LEVELS = [
        ("LOW", "Baja"),
        ("NORMAL", "Normal"),
        ("HIGH", "Alta"),
        ("CRITICAL", "Crítica"),
        ("EMERGENCY", "Emergencia"),
    ]

    priority = models.CharField(
        max_length=10,
        choices=PRIORITY_LEVELS,
        default="NORMAL",
        help_text="Prioridad del ticket",
    )

    # Categorización
    TICKET_CATEGORIES = [
        ("TECHNICAL", "Técnico"),
        ("FUNCTIONAL", "Funcional"),
        ("PERFORMANCE", "Performance"),
        ("SECURITY", "Seguridad"),
        ("DATA_QUALITY", "Calidad de Datos"),
        ("HARDWARE", "Hardware"),
        ("SOFTWARE", "Software"),
        ("NETWORK", "Red"),
        ("MAINTENANCE", "Mantenimiento"),
        ("OTHER", "Otro"),
    ]

    category = models.CharField(
        max_length=15,
        choices=TICKET_CATEGORIES,
        default="TECHNICAL",
        help_text="Categoría del ticket",
    )

    # Usuarios involucrados
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="created_tickets",
        help_text="Usuario que creó el ticket",
        null=True,
        blank=True,
    )

    assigned_to = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_tickets",
        help_text="Usuario asignado al ticket",
    )

    # Recursos afectados
    affected_devices = models.ManyToManyField(
        IoTDevice,
        related_name="support_tickets",
        blank=True,
        help_text="Dispositivos afectados",
    )

    affected_points = models.ManyToManyField(
        CatchmentPoint,
        related_name="support_tickets",
        blank=True,
        help_text="Puntos de captación afectados",
    )

    # Fechas importantes
    opened_at = models.DateTimeField(
        auto_now_add=True, help_text="Fecha de apertura del ticket"
    )

    due_date = models.DateTimeField(
        null=True, blank=True, help_text="Fecha límite para resolución"
    )

    resolved_at = models.DateTimeField(
        null=True, blank=True, help_text="Fecha de resolución"
    )

    closed_at = models.DateTimeField(null=True, blank=True, help_text="Fecha de cierre")

    # Métricas de resolución
    resolution_time_hours = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Tiempo de resolución en horas",
    )

    customer_satisfaction = models.PositiveIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text="Satisfacción del cliente (1-5)",
    )

    # Información adicional
    tags = models.JSONField(
        default=list,
        blank=True,
        help_text="Tags para categorización adicional",
    )

    attachments = JSONField(
        default=dict, help_text="Archivos adjuntos (URLs, paths, etc.)"
    )

    custom_fields = JSONField(
        default=dict, help_text="Campos personalizados según categoría"
    )

    class Meta:
        verbose_name = "Ticket de Soporte"
        verbose_name_plural = "Tickets de Soporte"
        indexes = [
            models.Index(fields=["ticket_number"]),
            models.Index(fields=["status", "priority"]),
            models.Index(fields=["category", "status"]),
            models.Index(fields=["created_by", "status"]),
            models.Index(fields=["assigned_to", "status"]),
            models.Index(fields=["opened_at"]),
            models.Index(fields=["due_date"]),
        ]
        ordering = ["-opened_at"]

    def __str__(self):
        return f"#{self.ticket_number} - {self.title}"

    def save(self, *args, **kwargs):
        # Auto-generate ticket number
        if not self.ticket_number:
            self.ticket_number = self._generate_ticket_number()

        # Calculate resolution time when resolved
        if self.status == "RESOLVED" and not self.resolved_at:
            self.resolved_at = timezone.now()
            if self.opened_at:
                delta = self.resolved_at - self.opened_at
                self.resolution_time_hours = delta.total_seconds() / 3600

        # Set closed timestamp
        if self.status == "CLOSED" and not self.closed_at:
            self.closed_at = timezone.now()

        super().save(*args, **kwargs)

    def _generate_ticket_number(self) -> str:
        """Genera número único de ticket"""
        import random
        import string

        # Formato: SUP-YYYY-NNNNN (ej: SUP-2024-00001)
        year = timezone.now().year
        random_part = "".join(random.choices(string.digits, k=5))
        return f"SUP-{year}-{random_part}"

    @property
    def is_overdue(self) -> bool:
        """Verifica si el ticket está vencido"""
        if not self.due_date:
            return False
        return timezone.now() > self.due_date

    @property
    def days_open(self) -> int:
        """Días que el ticket lleva abierto"""
        if self.status == "CLOSED" and self.closed_at:
            delta = self.closed_at - self.opened_at
        else:
            delta = timezone.now() - self.opened_at
        return delta.days

    def add_comment(self, user: User, comment: str, is_internal: bool = False):
        """Agrega un comentario al ticket"""
        return TicketComment.objects.create(
            ticket=self, author=user, comment=comment, is_internal=is_internal
        )

    def assign_to(self, user: User):
        """Asigna el ticket a un usuario"""
        self.assigned_to = user
        self.status = "IN_PROGRESS"
        self.save()

        # Crear comentario automático
        self.add_comment(
            user, f"Ticket asignado a {user.get_full_name()}", is_internal=True
        )

    def resolve(self, user: User, resolution_notes: str = ""):
        """Resuelve el ticket"""
        self.status = "RESOLVED"
        self.resolved_at = timezone.now()
        self.save()

        # Crear comentario de resolución
        if resolution_notes:
            self.add_comment(user, f"Ticket resuelto: {resolution_notes}")


class TicketComment(ModelApi):
    """
    Comentarios y actualizaciones en tickets de soporte
    """

    ticket = models.ForeignKey(
        SupportTicket,
        on_delete=models.CASCADE,
        related_name="comments",
        help_text="Ticket al que pertenece el comentario",
    )

    author = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="ticket_comments",
        help_text="Autor del comentario",
    )

    comment = models.TextField(help_text="Contenido del comentario")

    is_internal = models.BooleanField(
        default=False, help_text="Comentario interno (solo visible para staff)"
    )

    # Metadata
    attachments = JSONField(default=dict, help_text="Archivos adjuntos al comentario")

    mentioned_users = models.ManyToManyField(
        User,
        related_name="mentioned_in_comments",
        blank=True,
        help_text="Usuarios mencionados en el comentario",
    )

    class Meta:
        verbose_name = "Comentario de Ticket"
        verbose_name_plural = "Comentarios de Tickets"
        indexes = [
            models.Index(fields=["ticket", "created"]),
            models.Index(fields=["author", "created"]),
            models.Index(fields=["is_internal"]),
        ]
        ordering = ["created"]

    def __str__(self):
        return (
            f"Comment by {self.author.get_full_name()} on #{self.ticket.ticket_number}"
        )


class TicketSLA(ModelApi):
    """
    Definición de SLA (Service Level Agreement) para tickets
    """

    name = models.CharField(max_length=100, help_text="Nombre del SLA")

    category = models.CharField(
        max_length=15,
        choices=SupportTicket.TICKET_CATEGORIES,
        help_text="Categoría de tickets a la que aplica",
    )

    priority = models.CharField(
        max_length=10,
        choices=SupportTicket.PRIORITY_LEVELS,
        help_text="Prioridad de tickets a la que aplica",
    )

    # Tiempos de respuesta
    response_time_hours = models.PositiveIntegerField(
        help_text="Tiempo máximo de respuesta inicial en horas"
    )

    resolution_time_hours = models.PositiveIntegerField(
        help_text="Tiempo máximo de resolución en horas"
    )

    # Penalizaciones por incumplimiento
    penalty_per_hour = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=0,
        help_text="Penalización por hora de retraso",
    )

    # Configuración
    is_active = models.BooleanField(default=True, help_text="SLA activo")

    business_hours_only = models.BooleanField(
        default=True, help_text="Solo contar horas hábiles"
    )

    class Meta:
        verbose_name = "SLA de Tickets"
        verbose_name_plural = "SLAs de Tickets"
        indexes = [
            models.Index(fields=["category", "priority", "is_active"]),
        ]
        unique_together = ["category", "priority"]

    def __str__(self):
        return f"SLA {self.category} {self.priority}: {self.response_time_hours}h response, {self.resolution_time_hours}h resolution"


class DataQualityMetric(ModelApi):
    """
    Métricas de calidad de datos para monitoreo continuo
    """

    data_point = models.ForeignKey(
        DataPoint,
        on_delete=models.CASCADE,
        related_name="quality_metrics",
        help_text="Punto de dato evaluado",
    )

    # Métricas de calidad
    completeness_score = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
        help_text="Puntuación de completitud (0-1)",
    )

    accuracy_score = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
        help_text="Puntuación de precisión (0-1)",
    )

    timeliness_score = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
        help_text="Puntuación de oportunidad (0-1)",
    )

    consistency_score = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
        help_text="Puntuación de consistencia (0-1)",
    )

    # Puntuación general
    overall_score = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
        help_text="Puntuación general de calidad (0-1)",
    )

    # Problemas detectados
    issues_detected = JSONField(
        default=dict, help_text="Problemas de calidad detectados"
    )

    # Recomendaciones
    recommendations = models.JSONField(
        default=list,
        blank=True,
        help_text="Recomendaciones para mejorar calidad",
    )

    # Período evaluado
    evaluation_period_start = models.DateTimeField(
        help_text="Inicio del período evaluado"
    )

    evaluation_period_end = models.DateTimeField(help_text="Fin del período evaluado")

    class Meta:
        verbose_name = "Métrica de Calidad de Datos"
        verbose_name_plural = "Métricas de Calidad de Datos"
        indexes = [
            models.Index(fields=["data_point", "evaluation_period_start"]),
            models.Index(fields=["overall_score", "evaluation_period_end"]),
            models.Index(fields=["evaluation_period_start", "evaluation_period_end"]),
        ]

    def __str__(self):
        return f"Quality {self.data_point.stream.name}: {self.overall_score}"


# ============================================================================
# INTEGRACIÓN CON MODELOS EXISTENTES
# ============================================================================


class DataAggregation(ModelApi):
    """
    Agregaciones pre-calculadas para consultas rápidas
    """

    point = models.ForeignKey(
        CatchmentPoint,
        on_delete=models.CASCADE,
        related_name="data_aggregations",
        help_text="Punto de captación",
    )

    variable_definition = models.ForeignKey(
        VariableDefinition,
        on_delete=models.CASCADE,
        related_name="aggregations",
        help_text="Variable agregada",
    )

    # Período de agregación
    AGGREGATION_PERIODS = [
        ("HOURLY", "Por hora"),
        ("DAILY", "Diario"),
        ("WEEKLY", "Semanal"),
        ("MONTHLY", "Mensual"),
    ]

    period = models.CharField(
        max_length=10, choices=AGGREGATION_PERIODS, help_text="Período de agregación"
    )

    period_start = models.DateTimeField(help_text="Inicio del período")

    period_end = models.DateTimeField(help_text="Fin del período")

    # Valores agregados
    count = models.PositiveIntegerField(help_text="Número de mediciones")

    avg_value = models.DecimalField(
        max_digits=15,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Valor promedio",
    )

    min_value = models.DecimalField(
        max_digits=15, decimal_places=6, null=True, blank=True, help_text="Valor mínimo"
    )

    max_value = models.DecimalField(
        max_digits=15, decimal_places=6, null=True, blank=True, help_text="Valor máximo"
    )

    sum_value = models.DecimalField(
        max_digits=20, decimal_places=6, null=True, blank=True, help_text="Suma total"
    )

    # Calidad de la agregación
    data_quality = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
        help_text="Calidad de los datos agregados (0-1)",
    )

    class Meta:
        verbose_name = "Agregación de Datos"
        verbose_name_plural = "Agregaciones de Datos"
        indexes = [
            models.Index(
                fields=["point", "variable_definition", "period", "period_start"]
            ),
            models.Index(fields=["period_start", "period_end"]),
            models.Index(fields=["data_quality"]),
        ]
        unique_together = ["point", "variable_definition", "period", "period_start"]

    def __str__(self):
        return f"{self.point.title} {self.variable_definition.name} {self.period} {self.period_start.date()}"
