"""
Documents Models
Generalizado para soportar Clientes, Proyectos y Puntos.
"""

from django.db import models
from django.conf import settings
from api.core.models.utils import ModelApi


class DocumentType(ModelApi):
    """Document Type (renamed from TypeFileCatchment)."""

    name = models.CharField(max_length=300, verbose_name="Nombre")
    internal = models.BooleanField(default=False, verbose_name="Interno")

    class Meta:
        db_table = "core_typefilecatchment"
        verbose_name = "Tipo de archivo"
        verbose_name_plural = "Tipos de archivos"

    def __str__(self):
        return f"{self.name}"


class Document(ModelApi):
    """General Purpose Document Model."""

    document_type = models.ForeignKey(
        DocumentType,
        related_name="documents",
        on_delete=models.CASCADE,
        verbose_name="Tipo de archivo",
    )
    name = models.CharField(max_length=300, verbose_name="Nombre")
    file = models.FileField(upload_to="system_documents/", verbose_name="Archivo")
    description = models.CharField(
        max_length=300, verbose_name="Descripción", blank=True, null=True
    )
    is_active = models.BooleanField(default=True, verbose_name="Activo")

    # Polimorfismo simplificado vía FKs opcionales
    point_catchment = models.ForeignKey(
        "telemetry.CatchmentPoint",
        related_name="documents",
        on_delete=models.CASCADE,
        verbose_name="Punto de captacion",
        null=True,
        blank=True
    )
    client = models.ForeignKey(
        "crm.Client",
        related_name="documents",
        on_delete=models.CASCADE,
        verbose_name="Cliente",
        null=True,
        blank=True
    )
    project = models.ForeignKey(
        "crm.Project",
        related_name="documents",
        on_delete=models.CASCADE,
        verbose_name="Proyecto",
        null=True,
        blank=True
    )
    
    # New relationships for CRM flow
    technical_survey = models.ForeignKey(
        "crm.TechnicalSurvey",
        related_name="documents",
        on_delete=models.CASCADE,
        verbose_name="Levantamiento Técnico",
        null=True,
        blank=True
    )
    crm_task = models.ForeignKey(
        "crm.CrmTask",
        related_name="documents",
        on_delete=models.CASCADE,
        verbose_name="Tarea CRM",
        null=True,
        blank=True
    )

    # Professional Metadata
    valid_until = models.DateField(
        null=True, 
        blank=True, 
        verbose_name="Fecha de Vencimiento",
        help_text="Opcional. Para documentos con vigencia limitada."
    )
    internal_only = models.BooleanField(
        default=False, 
        verbose_name="Solo Interno",
        help_text="Si está marcado, solo será visible para personal administrativo."
    )
    tags = models.CharField(
        max_length=500, 
        blank=True, 
        verbose_name="Etiquetas",
        help_text="Separadas por comas. Ejemplo: factura, certificado, dga"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Subido por",
        related_name="uploaded_documents"
    )


    class Meta:
        db_table = "core_filecatchment"
        verbose_name = "Archivo/Documento"
        verbose_name_plural = "Archivos/Documentos"

    def __str__(self):
        target = self.point_catchment or self.project or self.client or "General"
        return f"{self.name} ({target})"
