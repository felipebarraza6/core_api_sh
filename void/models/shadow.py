"""Shadow mode models for comparing legacy vs void telemetry outputs."""
from django.db import models

from void.models.base import VoidModel


class ShadowRun(VoidModel):
    """Ejecución de shadow mode para un dispositivo/variable.

    Cada run representa una ventana de tiempo en la que se intentó replicar
    la lectura legacy usando void, y se compararon salidas.
    """

    STATUS_CHOICES = [
        ("pending", "Pendiente"),
        ("running", "Ejecutando"),
        ("completed", "Completado"),
        ("failed", "Fallido"),
        ("skipped", "Omitido"),
    ]

    device = models.ForeignKey(
        "void.Device",
        on_delete=models.CASCADE,
        related_name="shadow_runs",
        verbose_name="Dispositivo",
    )
    variable = models.CharField(
        max_length=80,
        verbose_name="Variable",
    )
    output_field = models.CharField(
        max_length=40,
        blank=True,
        default="",
        verbose_name="Campo procesado",
        help_text="Campo de ProcessedReading comparado (total, flow, nivel, water_table). Vacío = comparación cruda.",
    )
    window_start = models.DateTimeField(
        verbose_name="Inicio ventana",
    )
    window_end = models.DateTimeField(
        verbose_name="Fin ventana",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
        verbose_name="Estado",
        db_index=True,
    )
    error_message = models.TextField(
        blank=True,
        default="",
        verbose_name="Mensaje de error",
    )
    legacy_count = models.PositiveIntegerField(
        default=0,
        verbose_name="Registros legacy",
    )
    void_count = models.PositiveIntegerField(
        default=0,
        verbose_name="Registros void",
    )
    matched_count = models.PositiveIntegerField(
        default=0,
        verbose_name="Coincidencias",
    )
    mismatched_count = models.PositiveIntegerField(
        default=0,
        verbose_name="Diferencias",
    )
    legacy_only_count = models.PositiveIntegerField(
        default=0,
        verbose_name="Solo en legacy",
    )
    void_only_count = models.PositiveIntegerField(
        default=0,
        verbose_name="Solo en void",
    )

    class Meta:
        verbose_name = "Shadow run"
        verbose_name_plural = "Shadow runs"
        ordering = ["-created"]
        indexes = [
            models.Index(fields=["device", "variable", "-created"]),
            models.Index(fields=["status", "-created"]),
        ]

    def __str__(self):
        return f"{self.device} | {self.variable} | {self.window_start} → {self.status}"


class ShadowComparison(VoidModel):
    """Comparación punto a punto entre legacy y void."""

    RESULT_CHOICES = [
        ("match", "Coincide"),
        ("mismatch", "Difiere"),
        ("legacy_only", "Solo legacy"),
        ("void_only", "Solo void"),
    ]

    run = models.ForeignKey(
        ShadowRun,
        on_delete=models.CASCADE,
        related_name="comparisons",
        verbose_name="Shadow run",
    )
    timestamp = models.DateTimeField(
        verbose_name="Timestamp",
        db_index=True,
    )
    result = models.CharField(
        max_length=20,
        choices=RESULT_CHOICES,
        verbose_name="Resultado",
        db_index=True,
    )
    legacy_value = models.CharField(
        max_length=400,
        blank=True,
        default="",
        verbose_name="Valor legacy",
    )
    void_value = models.CharField(
        max_length=400,
        blank=True,
        default="",
        verbose_name="Valor void",
    )
    legacy_record_id = models.CharField(
        max_length=80,
        blank=True,
        default="",
        verbose_name="ID registro legacy",
    )
    void_record_id = models.CharField(
        max_length=80,
        blank=True,
        default="",
        verbose_name="ID registro void",
    )
    diff = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Diferencias detalladas",
    )

    class Meta:
        verbose_name = "Comparación shadow"
        verbose_name_plural = "Comparaciones shadow"
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["run", "result"]),
            models.Index(fields=["run", "timestamp"]),
        ]

    def __str__(self):
        return f"{self.timestamp} | {self.result}"
