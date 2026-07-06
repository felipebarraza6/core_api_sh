"""SLA models for void."""
from django.db import models

from void.models.base import VoidModel


class SLAPolicy(VoidModel):
    """Política de SLA operacional para dispositivos/puntos."""

    METRIC_CHOICES = [
        ("uptime", "Disponibilidad (%)"),
        ("data_latency_minutes", "Latencia de datos (minutos)"),
        ("last_connection_hours", "Horas desde última conexión"),
        ("battery_level", "Nivel de batería"),
        ("signal_level", "Nivel de señal"),
        ("missing_variables", "Variables faltantes"),
    ]

    OPERATOR_CHOICES = [
        ("<", "Menor que"),
        ("<=", "Menor o igual que"),
        (">", "Mayor que"),
        (">=", "Mayor o igual que"),
        ("==", "Igual a"),
        ("!=", "Distinto de"),
    ]

    SEVERITY_CHOICES = [
        ("info", "Info"),
        ("warning", "Advertencia"),
        ("critical", "Crítico"),
    ]

    name = models.CharField(
        max_length=200,
        verbose_name="Nombre",
    )
    description = models.TextField(
        blank=True,
        default="",
        verbose_name="Descripción",
    )
    point_group = models.ForeignKey(
        "void.PointGroup",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="sla_policies",
        verbose_name="Grupo de puntos",
    )
    metric = models.CharField(
        max_length=40,
        choices=METRIC_CHOICES,
        verbose_name="Métrica",
    )
    operator = models.CharField(
        max_length=4,
        choices=OPERATOR_CHOICES,
        default=">",
        verbose_name="Operador",
    )
    threshold = models.DecimalField(
        max_digits=15,
        decimal_places=4,
        verbose_name="Umbral",
    )
    severity = models.CharField(
        max_length=20,
        choices=SEVERITY_CHOICES,
        default="warning",
        verbose_name="Severidad",
    )
    escalation_minutes = models.PositiveIntegerField(
        default=0,
        verbose_name="Minutos para escalamiento",
        help_text="0 = sin escalamiento automático.",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Activo",
        db_index=True,
    )

    class Meta:
        verbose_name = "Política SLA"
        verbose_name_plural = "Políticas SLA"

    def __str__(self):
        return f"{self.name}: {self.metric} {self.operator} {self.threshold}"


class SLAEvent(VoidModel):
    """Evento de incumplimiento de SLA."""

    STATUS_CHOICES = [
        ("open", "Abierto"),
        ("acknowledged", "Reconocido"),
        ("resolved", "Resuelto"),
    ]

    policy = models.ForeignKey(
        SLAPolicy,
        on_delete=models.CASCADE,
        related_name="events",
        verbose_name="Política",
    )
    device = models.ForeignKey(
        "void.Device",
        on_delete=models.CASCADE,
        related_name="sla_events",
        verbose_name="Dispositivo",
    )
    started_at = models.DateTimeField(
        verbose_name="Iniciado el",
    )
    resolved_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name="Resuelto el",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="open",
        verbose_name="Estado",
        db_index=True,
    )
    observed_value = models.DecimalField(
        max_digits=15,
        decimal_places=4,
        blank=True,
        null=True,
        verbose_name="Valor observado",
    )
    message = models.CharField(
        max_length=500,
        blank=True,
        default="",
        verbose_name="Mensaje",
    )

    class Meta:
        verbose_name = "Evento SLA"
        verbose_name_plural = "Eventos SLA"
        indexes = [
            models.Index(fields=["device", "status", "started_at"]),
            models.Index(fields=["policy", "status"]),
        ]

    def __str__(self):
        return f"{self.device} | {self.policy} | {self.status}"
