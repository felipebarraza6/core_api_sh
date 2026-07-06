"""Point models for void."""
from django.db import models

from .base import VoidModel


class Point(VoidModel):
    """Punto de captación en la nueva arquitectura void."""

    MIGRATION_STATUS_CHOICES = [
        ("not_started", "No iniciado"),
        ("shadow", "Shadow mode"),
        ("migrated", "Migrado"),
        ("rolled_back", "Rollback"),
    ]

    name = models.CharField(
        max_length=300,
        verbose_name="Nombre",
    )
    code_internal = models.CharField(
        max_length=300,
        blank=True,
        default="",
        verbose_name="Código interno",
    )
    description = models.TextField(
        blank=True,
        default="",
        verbose_name="Descripción",
    )
    lat = models.CharField(
        max_length=120,
        blank=True,
        default="",
        verbose_name="Latitud",
    )
    lon = models.CharField(
        max_length=120,
        blank=True,
        default="",
        verbose_name="Longitud",
    )
    frequency_minutes = models.PositiveIntegerField(
        default=60,
        verbose_name="Frecuencia (minutos)",
        help_text="Frecuencia de telemetría: 1, 5, 10, 15, 30, 60, etc.",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Activo",
        db_index=True,
    )
    installed_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name="Fecha de instalación",
    )
    decommissioned_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name="Fecha de baja",
    )
    project = models.CharField(
        max_length=300,
        blank=True,
        default="",
        verbose_name="Proyecto (legacy texto)",
        help_text="Campo texto legacy. Se migrará a project_fk.",
    )
    project_fk = models.ForeignKey(
        "void.Project",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="points",
        verbose_name="Proyecto",
    )
    client = models.CharField(
        max_length=300,
        blank=True,
        default="",
        verbose_name="Cliente",
    )
    client_fk = models.ForeignKey(
        "Client",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="points",
        verbose_name="Cliente (FK)",
        help_text="Entidad Cliente real. Reemplazará el campo 'client' texto en la migración.",
    )
    legacy_point = models.ForeignKey(
        "core.CatchmentPoint",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="void_points",
        verbose_name="Punto legacy",
        help_text="Vínculo opcional con CatchmentPoint. Null = punto nativo void.",
    )
    migration_status = models.CharField(
        max_length=20,
        choices=MIGRATION_STATUS_CHOICES,
        default="not_started",
        verbose_name="Estado de migración",
        db_index=True,
    )
    constants = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Constantes del punto",
        help_text="Constantes físicas del punto: d1, d2, d3, d4, d5, d6, etc.",
    )
    replicate_on_missing = models.BooleanField(
        default=False,
        verbose_name="Replicar último dato si no hay lecturas",
        help_text="Si no llegan datos del proveedor, replica el último ProcessedReading válido en los slots de tiempo esperados (similar a legacy Nettra).",
    )
    max_replication_hours = models.PositiveIntegerField(
        default=24,
        verbose_name="Máximas horas de replicación",
        help_text="Ventana máxima hacia atrás para buscar el último dato válido a replicar.",
    )
    extra_data = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Metadatos extra",
    )

    class Meta:
        verbose_name = "Punto de captación (void)"
        verbose_name_plural = "Puntos de captación (void)"
        indexes = [
            models.Index(fields=["client_fk", "project_fk", "is_active"]),
            models.Index(fields=["is_active", "frequency_minutes"]),
            models.Index(fields=["legacy_point", "migration_status"]),
        ]
        ordering = ["-created"]

    def __str__(self):
        return f"{self.name} ({self.code_internal or self.id})"


class PointGroup(VoidModel):
    """Agrupación de puntos para permisos y SLA masivos."""

    name = models.CharField(
        max_length=300,
        verbose_name="Nombre",
    )
    description = models.TextField(
        blank=True,
        default="",
        verbose_name="Descripción",
    )
    points = models.ManyToManyField(
        Point,
        related_name="groups",
        verbose_name="Puntos",
        blank=True,
    )

    class Meta:
        verbose_name = "Grupo de puntos"
        verbose_name_plural = "Grupos de puntos"

    def __str__(self):
        return self.name


class PointPermission(VoidModel):
    """Permiso de un usuario sobre un grupo de puntos."""

    PERMISSION_CHOICES = [
        ("view", "Ver"),
        ("change", "Editar"),
        ("admin", "Administrar"),
    ]

    user = models.ForeignKey(
        "VoidUserProfile",
        on_delete=models.CASCADE,
        related_name="point_permissions",
        verbose_name="Usuario",
    )
    group = models.ForeignKey(
        PointGroup,
        on_delete=models.CASCADE,
        related_name="permissions",
        verbose_name="Grupo",
    )
    permission = models.CharField(
        max_length=20,
        choices=PERMISSION_CHOICES,
        default="view",
        verbose_name="Permiso",
    )

    class Meta:
        verbose_name = "Permiso sobre grupo"
        verbose_name_plural = "Permisos sobre grupos"
        unique_together = ("user", "group", "permission")

    def __str__(self):
        return f"{self.user} → {self.group}: {self.permission}"
