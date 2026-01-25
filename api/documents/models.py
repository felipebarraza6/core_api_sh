"""
Documents Models
Generalizado para soportar Clientes, Proyectos y Puntos.
Incorpora Generación de Documentos (Templates).
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


class DocumentTemplate(ModelApi):
    """
    Template for generating dynamic documents.
    Supported: .docx (Word), .xlsx (Excel).
    """
    code = models.CharField(max_length=50, unique=True, verbose_name="Código Único", help_text="Ej: CERT_CAUDAL_V1")
    name = models.CharField(max_length=200, verbose_name="Nombre Template")
    file = models.FileField(upload_to="templates/", verbose_name="Archivo Plantilla (.docx/.xlsx)")
    description = models.TextField(blank=True, null=True, verbose_name="Descripción")
    
    # Metadata for the engine
    engine_type = models.CharField(
        max_length=20, 
        choices=[('docx', 'Word (Jinja2)'), ('xlsx', 'Excel (OpenPyXL)'), ('pdf', 'PDF (HTML Template)')],
        default='docx'
    )
    html_content = models.TextField(
        blank=True, 
        null=True, 
        verbose_name="Contenido HTML",
        help_text="Solo para motor PDF. Puede usar variables {{ variable }} de Django Templates."
    )
    required_context = models.JSONField(
        default=dict, 
        help_text="Esquema JSON de variables requeridas. Ej: ['cliente', 'caudal']",
        blank=True
    )

    class Meta:
        verbose_name = "Plantilla de Documento"
        verbose_name_plural = "Plantillas de Documentos"

    def __str__(self):
        return f"[{self.code}] {self.name}"


class ScheduledGeneration(ModelApi):
    """
    Configuration for auto-generating documents.
    """
    template = models.ForeignKey(DocumentTemplate, on_delete=models.CASCADE, verbose_name="Plantilla")
    name = models.CharField(max_length=200, verbose_name="Nombre Tarea")
    
    # Scheduling
    cron_expression = models.CharField(max_length=100, help_text="Formato Cron (Ej: 0 8 * * 1 para Lunes 8am)")
    is_active = models.BooleanField(default=True, verbose_name="Activo")
    last_run = models.DateTimeField(null=True, blank=True)
    next_run = models.DateTimeField(null=True, blank=True)
    
    # Context & Delivery
    static_context = models.JSONField(default=dict, blank=True, help_text="Datos fijos para el reporte")
    recipients = models.TextField(help_text="Emails separados por coma")
    
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)

    class Meta:
        verbose_name = "Generación Programada"
        verbose_name_plural = "Generaciones Programadas"


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
        related_name="sourced_documents",
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
        related_name="sourced_documents",
        on_delete=models.CASCADE,
        verbose_name="Proyecto",
        null=True,
        blank=True
    )

    
    # New relationships for CRM flow
    technical_survey = models.ForeignKey(
        "crm.TechnicalSurvey",
        related_name="sourced_documents",
        on_delete=models.CASCADE,
        verbose_name="Levantamiento Técnico",
        null=True,
        blank=True
    )
    crm_task = models.ForeignKey(
        "crm.CrmTask",
        related_name="sourced_documents",
        on_delete=models.CASCADE,
        verbose_name="Tarea CRM",
        null=True,
        blank=True
    )

    # Infrastructure relationships (guías, datasheets, informes)
    manufacturer = models.ForeignKey(
        "infrastructure.Manufacturer",
        related_name="documents",
        on_delete=models.CASCADE,
        verbose_name="Fabricante",
        null=True,
        blank=True,
        help_text="Documentos del fabricante (catálogos, guías)"
    )
    device_model = models.ForeignKey(
        "infrastructure.DeviceModel",
        related_name="documents",
        on_delete=models.CASCADE,
        verbose_name="Modelo de Equipo",
        null=True,
        blank=True,
        help_text="Documentos del modelo (datasheets, manuales)"
    )
    device = models.ForeignKey(
        "infrastructure.Device",
        related_name="documents",
        on_delete=models.CASCADE,
        verbose_name="Dispositivo",
        null=True,
        blank=True,
        help_text="Documentos del dispositivo (calibraciones, informes)"
    )
    
    # Link to Generator
    generated_from = models.ForeignKey(
        DocumentTemplate, 
        on_delete=models.SET_NULL, 
        null=True, blank=True,
        related_name="generated_documents",
        help_text="Si se creó automáticamente desde un template"
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
        target = (
            self.point_catchment or self.project or self.client or
            self.device or self.device_model or self.manufacturer or
            "General"
        )
        return f"{self.name} ({target})"
