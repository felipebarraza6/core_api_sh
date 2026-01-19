"""
CRM Models - Customer Relationship Management
Expanded for full project lifecycle management.
"""

from django.db import models
from django.conf import settings
from api.core.models.utils import ModelApi


class Client(ModelApi):
    """Client Model with expanded business profile."""

    STATUS_CHOICES = [
        ("ACTIVE", "Activo"),
        ("INACTIVE", "Inactivo"),
        ("PROSPECT", "Prospecto"),
        ("SUSPENDED", "Suspendido"),
    ]

    name = models.CharField(max_length=300, verbose_name="Nombre/Razón Social")
    rut = models.CharField(max_length=300, verbose_name="RUT")
    address = models.CharField(max_length=300, verbose_name="Dirección")
    phone = models.CharField(max_length=300, verbose_name="Teléfono")
    email = models.CharField(max_length=300, verbose_name="Correo Electrónico")
    
    business_type = models.CharField(max_length=200, blank=True, null=True, verbose_name="Giro/Rubro")
    legal_representative = models.CharField(max_length=300, blank=True, null=True, verbose_name="Representante Legal")
    website = models.URLField(blank=True, null=True, verbose_name="Sitio Web")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="PROSPECT", verbose_name="Estado")
    logo = models.ImageField(upload_to="client_logos/", blank=True, null=True, verbose_name="Logo")

    class Meta:
        db_table = "core_client"
        verbose_name = "Cliente"
        verbose_name_plural = "Clientes"

    def __str__(self):
        return f"{self.name}"


class Project(ModelApi):
    """Project Model - Managing the pre-installation and active phases."""

    STATUS_CHOICES = [
        ("PLANNING", "Planificación"),
        ("PROPOSAL", "Propuesta/Cotización"),
        ("APPROVED", "Aprobado (Preparando Instalación)"),
        ("IN_PROGRESS", "En Instalación"),
        ("ACTIVE", "Activo/Operativo"),
        ("MAINTENANCE", "En Mantenimiento"),
        ("CLOSED", "Cerrado"),
    ]

    name = models.CharField(max_length=300, verbose_name="Nombre del Proyecto")
    client = models.ForeignKey(
        Client, on_delete=models.CASCADE, related_name="projects", verbose_name="Cliente", null=True, blank=True
    )
    code_internal = models.CharField(
        max_length=300, blank=True, null=True, verbose_name="Código Interno"
    )
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="PLANNING", verbose_name="Estado")
    description = models.TextField(blank=True, null=True, verbose_name="Descripción del Proyecto")
    start_date = models.DateField(blank=True, null=True, verbose_name="Fecha Prevista Inicio")
    description = models.TextField(blank=True, null=True, verbose_name="Descripción del Proyecto")
    start_date = models.DateField(blank=True, null=True, verbose_name="Fecha Prevista Inicio")
    budget = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Presupuesto Estimado")
    
    class Meta:
        db_table = "core_projectcatchments"
        verbose_name = "Proyecto"
        verbose_name_plural = "Proyectos"

    def __str__(self):
        return f"{self.name} ({self.client.name})"


class CrmTask(ModelApi):
    """Tasks for commercial and technical field activities."""

    TASK_TYPES = [
        ("COMMERCIAL", "Gestión Comercial"),
        ("TECHNICAL_VISIT", "Visita Técnica Terreno"),
        ("INSTALLATION", "Instalación"),
        ("MAINTENANCE", "Mantenimiento"),
        ("ADMINISTRATIVE", "Administrativo"),
    ]

    PRIORITY_CHOICES = [
        ("LOW", "Baja"),
        ("MEDIUM", "Media"),
        ("HIGH", "Alta"),
        ("CRITICAL", "Crítica"),
    ]

    STATUS_CHOICES = [
        ("PENDING", "Pendiente"),
        ("IN_PROGRESS", "En Proceso"),
        ("COMPLETED", "Completada"),
        ("CANCELLED", "Cancelada"),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="tasks")
    title = models.CharField(max_length=300, verbose_name="Título de la Tarea")
    description = models.TextField(verbose_name="Descripción Detallada")
    
    # New Dynamic Task Type
    # Dynamic Hierarchy
    category = models.ForeignKey(
        'TaskCategory',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Categoría",
        related_name="tasks"
    )
    subcategory = models.ForeignKey(
        'TaskSubCategory',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Subcategoría",
        related_name="tasks"
    )
    
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default="MEDIUM")
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default="PENDING")
    
    due_date = models.DateTimeField(verbose_name="Fecha Límite")
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name="crm_tasks"
    )
    
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Tarea CRM"
        verbose_name_plural = "Tareas CRM"
        ordering = ["-priority", "due_date"]

    def __str__(self):
        return f"{self.title} - {self.project.name}"


class TaskCategory(ModelApi):
    """Main category for CRM tasks."""
    name = models.CharField(max_length=200, verbose_name="Nombre Categoría")
    color_code = models.CharField(max_length=20, default="#333333", verbose_name="Color Hex")

    class Meta:
        verbose_name = "Categoría de Tarea"
        verbose_name_plural = "Categorías de Tareas"

    def __str__(self):
        return self.name


class TaskSubCategory(ModelApi):
    """Sub-category belonging to a main task category."""
    category = models.ForeignKey(TaskCategory, on_delete=models.CASCADE, related_name="subcategories", verbose_name="Categoría Principal")
    name = models.CharField(max_length=200, verbose_name="Nombre Subcategoría")

    class Meta:
        verbose_name = "Subcategoría de Tarea"
        verbose_name_plural = "Subcategorías de Tareas"

    def __str__(self):
        return f"{self.name} ({self.category.name})"


class TechnicalSurvey(ModelApi):
    """Technical surveying before sensor installation."""

    project = models.OneToOneField(Project, on_delete=models.CASCADE, related_name="technical_survey")
    
    # Hidráulica
    pipe_diameter_inches = models.FloatField(verbose_name="Diámetro Tubería (Pulgadas)", default=0)
    expected_max_flow = models.FloatField(verbose_name="Caudal Máximo Esperado (L/s)", default=0)
    sensor_type_suggested = models.CharField(max_length=200, verbose_name="Tipo Sensor Sugerido", blank=True)
    
    # Eléctrica
    POWER_SOURCES = [
        ("SOLAR", "Panel Solar"),
        ("GRID", "Red Eléctrica 220V"),
        ("BATTERY", "Solo Batería (Recargable)"),
        ("OTHER", "Otro"),
    ]
    power_source = models.CharField(max_length=20, choices=POWER_SOURCES, default="SOLAR")
    electrical_distance_meters = models.FloatField(verbose_name="Distancia a Fuente Eléctrica (m)", default=0)
    
    # Eléctrica
    POWER_SOURCES = [
        ("SOLAR", "Panel Solar"),
        ("GRID", "Red Eléctrica 220V"),
        ("BATTERY", "Solo Batería (Recargable)"),
        ("OTHER", "Otro"),
    ]
    power_source = models.CharField(max_length=20, choices=POWER_SOURCES, default="SOLAR")
    electrical_distance_meters = models.FloatField(verbose_name="Distancia a Fuente Eléctrica (m)", default=0)
    
    # Pre-Configuración y Factibilidad
    requires_dga = models.BooleanField(default=False, verbose_name="¿Requiere Reporte DGA?")
    requires_telemetry = models.BooleanField(default=True, verbose_name="¿Requiere Telemetría?")
    proposed_start_date = models.DateField(blank=True, null=True, verbose_name="Fecha Propuesta Inicio")
    dga_water_rights_code = models.CharField(max_length=200, blank=True, null=True, verbose_name="Código Expediente DGA")

    # Logística y Terreno
    signal_strength_dbm = models.IntegerField(verbose_name="Fuerza de Señal en Terreno (dBm)", default=0)
    access_complexity = models.TextField(verbose_name="Complejidad de Acceso", blank=True)
    gps_coordinates = models.CharField(max_length=100, verbose_name="Coordenadas GPS Sugeridas", blank=True)
    
    recommendations = models.TextField(verbose_name="Recomendaciones Técnicas", blank=True)

    class Meta:
        verbose_name = "Levantamiento Técnico"
        verbose_name_plural = "Levantamientos Técnicos"


class CostCategory(ModelApi):
    """Main category for project costs."""
    name = models.CharField(max_length=200, verbose_name="Nombre Categoría")
    
    class Meta:
        verbose_name = "Categoría de Costo"
        verbose_name_plural = "Categorías de Costos"

    def __str__(self):
        return self.name


class CostSubCategory(ModelApi):
    """Sub-category belonging to a main category."""
    category = models.ForeignKey(CostCategory, on_delete=models.CASCADE, related_name="subcategories", verbose_name="Categoría Principal")
    name = models.CharField(max_length=200, verbose_name="Nombre Subcategoría")

    class Meta:
        verbose_name = "Subcategoría de Costo"
        verbose_name_plural = "Subcategorías de Costos"

    def __str__(self):
        return f"{self.name} ({self.category.name})"


class ProjectCost(ModelApi):
    """Breakdown of costs for project budget planning."""

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="costs")
    
    # Hierarchy: Category is mandatory, Subcategory is optional
    category = models.ForeignKey(
        CostCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Categoría",
        related_name="costs"
    )
    subcategory = models.ForeignKey(
        CostSubCategory, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        verbose_name="Subcategoría",
        related_name="costs"
    )
    
    description = models.CharField(max_length=300)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    is_estimated = models.BooleanField(default=True, verbose_name="Es Estimado")
    
    documents = models.ManyToManyField(
        "documents.Document", 
        blank=True, 
        related_name="project_costs", 
        verbose_name="Documentos de Respaldo"
    )

    class Meta:
        verbose_name = "Costo de Proyecto"
        verbose_name_plural = "Costos de Proyecto"


class JobPosition(ModelApi):
    """Job Position Model for dynamic role management."""
    name = models.CharField(max_length=200, verbose_name="Nombre del Cargo")
    department = models.CharField(
        max_length=200, 
        blank=True, 
        null=True, 
        verbose_name="Departamento/Área",
        help_text="Ej: Comercial, Técnico, Operaciones"
    )

    class Meta:
        verbose_name = "Cargo / Puesto"
        verbose_name_plural = "Cargos / Puestos"

    def __str__(self):
        return self.name


class Person(ModelApi):
    """Person Model for contact management within clients."""

    project = models.ForeignKey(
        Project, 
        on_delete=models.CASCADE, 
        related_name="contacts", 
        verbose_name="Proyecto Asociado",
        null=True,  # Initially nullable to ease migration, can be strict later
        blank=True
    )
    name = models.CharField(max_length=300, blank=True, null=True, verbose_name="Nombre Completo")
    email = models.EmailField(max_length=300, blank=True, null=True, verbose_name="Correo")
    phone = models.CharField(max_length=300, blank=True, null=True, verbose_name="Teléfono")
    phone = models.CharField(max_length=300, blank=True, null=True, verbose_name="Teléfono")
    
    # New dynamic relationship
    job_position = models.ForeignKey(
        JobPosition, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name="persons",
        verbose_name="Cargo"
    )

    class Meta:
        db_table = "core_registerpersons"
        verbose_name = "Contacto / Persona"
        verbose_name_plural = "Contactos / Personas"

    def __str__(self):
        return f"{self.name} ({self.client.name if self.client else 'Sin Cliente'})"
