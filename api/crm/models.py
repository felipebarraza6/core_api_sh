"""
CRM Models - Customer Relationship Management
Expanded for full project lifecycle management.

V2.0 - Mejoras:
- JobPosition vinculado a Client
- CostType (Ingreso/Egreso) con SubTypes
- TaskType/TaskSubType adicionales
- TaskResponse con archivos adjuntos
- TechnicalSurvey dinámico con campos configurables
"""

from django.db import models
from django.conf import settings
from api.core.models.utils import ModelApi


# =============================================================================
# CLIENTE Y CARGOS
# =============================================================================

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
    address = models.CharField(max_length=300, verbose_name="Dirección", blank=True)
    phone = models.CharField(max_length=300, verbose_name="Teléfono", blank=True)
    email = models.CharField(max_length=300, verbose_name="Correo Electrónico", blank=True)
    
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


class JobPosition(ModelApi):
    """
    Job Position Model - Cargos definidos por cada cliente.
    Cada cliente puede tener sus propios cargos personalizados.
    """
    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name="job_positions",
        verbose_name="Cliente",
        null=True,
        blank=True,
        help_text="Cliente al que pertenece este cargo. Dejar vacío para cargos globales."
    )
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
        ordering = ['client', 'name']

    def __str__(self):
        if self.client:
            return f"{self.name} ({self.client.name})"
        return f"{self.name} (Global)"


# =============================================================================
# PROYECTO
# =============================================================================

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
    budget = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Presupuesto Estimado")
    
    # Documentos adjuntos al proyecto (Contratos, propuestas, etc)
    documents = models.ManyToManyField(
        "documents.Document",
        blank=True,
        related_name="projects_attached",
        verbose_name="Archivos Adjuntos"
    )
    
    class Meta:
        db_table = "core_projectcatchments"
        verbose_name = "Proyecto"
        verbose_name_plural = "Proyectos"

    def __str__(self):
        client_name = self.client.name if self.client else "Sin Cliente"
        return f"{self.name} ({client_name})"


# =============================================================================
# CONTACTOS / PERSONAS
# =============================================================================

class Person(ModelApi):
    """Person Model for contact management within projects."""

    project = models.ForeignKey(
        Project, 
        on_delete=models.CASCADE, 
        related_name="contacts", 
        verbose_name="Proyecto Asociado",
        null=True,
        blank=True
    )
    name = models.CharField(max_length=300, blank=True, null=True, verbose_name="Nombre Completo")
    email = models.EmailField(max_length=300, blank=True, null=True, verbose_name="Correo")
    phone = models.CharField(max_length=300, blank=True, null=True, verbose_name="Teléfono")
    
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
        project_name = self.project.name if self.project else "Sin Proyecto"
        return f"{self.name} ({project_name})"


# =============================================================================
# COSTOS - CATEGORÍAS Y TIPOS (INGRESO/EGRESO)
# =============================================================================

class CostCategory(ModelApi):
    """Categoría interna de costos (ej: Hardware, Mano de Obra, Transporte)."""
    name = models.CharField(max_length=200, verbose_name="Nombre Categoría")
    description = models.TextField(blank=True, verbose_name="Descripción")
    is_active = models.BooleanField(default=True, verbose_name="Activo")
    
    class Meta:
        verbose_name = "Categoría de Costo"
        verbose_name_plural = "Categorías de Costos"

    def __str__(self):
        return self.name


class CostSubCategory(ModelApi):
    """Subcategoría de costo."""
    category = models.ForeignKey(
        CostCategory, 
        on_delete=models.CASCADE, 
        related_name="subcategories", 
        verbose_name="Categoría Principal"
    )
    name = models.CharField(max_length=200, verbose_name="Nombre Subcategoría")

    class Meta:
        verbose_name = "Subcategoría de Costo"
        verbose_name_plural = "Subcategorías de Costos"

    def __str__(self):
        return f"{self.name} ({self.category.name})"


class CostType(ModelApi):
    """
    Tipo de movimiento financiero: Ingreso o Egreso.
    Define la naturaleza del flujo de dinero.
    """
    FLOW_CHOICES = [
        ("INCOME", "Ingreso"),
        ("EXPENSE", "Egreso"),
    ]
    
    name = models.CharField(max_length=200, verbose_name="Nombre del Tipo")
    flow = models.CharField(
        max_length=20, 
        choices=FLOW_CHOICES, 
        default="EXPENSE",
        verbose_name="Flujo"
    )
    description = models.TextField(blank=True, verbose_name="Descripción")
    color_code = models.CharField(max_length=20, default="#333333", verbose_name="Color Hex")

    class Meta:
        verbose_name = "Tipo de Costo (Ingreso/Egreso)"
        verbose_name_plural = "Tipos de Costos"

    def __str__(self):
        flow_label = "📈" if self.flow == "INCOME" else "📉"
        return f"{flow_label} {self.name}"


class CostSubType(ModelApi):
    """Subtipo de ingreso o egreso."""
    cost_type = models.ForeignKey(
        CostType, 
        on_delete=models.CASCADE, 
        related_name="subtypes", 
        verbose_name="Tipo Principal"
    )
    name = models.CharField(max_length=200, verbose_name="Nombre Subtipo")

    class Meta:
        verbose_name = "Subtipo de Costo"
        verbose_name_plural = "Subtipos de Costos"

    def __str__(self):
        return f"{self.name} ({self.cost_type.name})"


class ProjectCost(ModelApi):
    """Breakdown of costs for project budget planning."""

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="costs")
    
    # Categoría interna (qué es: hardware, mano de obra, etc.)
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
    
    # Tipo de flujo (ingreso o egreso)
    cost_type = models.ForeignKey(
        CostType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Tipo (Ingreso/Egreso)",
        related_name="costs"
    )
    cost_subtype = models.ForeignKey(
        CostSubType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Subtipo",
        related_name="costs"
    )
    
    description = models.CharField(max_length=300, verbose_name="Descripción")
    amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Monto")
    is_estimated = models.BooleanField(default=True, verbose_name="Es Estimado")
    date = models.DateField(blank=True, null=True, verbose_name="Fecha del Movimiento")
    
    documents = models.ManyToManyField(
        "documents.Document", 
        blank=True, 
        related_name="project_costs", 
        verbose_name="Documentos de Respaldo"
    )

    class Meta:
        verbose_name = "Costo de Proyecto"
        verbose_name_plural = "Costos de Proyecto"
        ordering = ['-date', '-created']

    def __str__(self):
        return f"{self.description} - ${self.amount}"


# =============================================================================
# TAREAS - CATEGORÍAS, TIPOS Y RESPUESTAS
# =============================================================================

class TaskCategory(ModelApi):
    """Categoría principal de tareas (ej: Comercial, Técnica, Administrativa)."""
    name = models.CharField(max_length=200, verbose_name="Nombre Categoría")
    color_code = models.CharField(max_length=20, default="#333333", verbose_name="Color Hex")
    description = models.TextField(blank=True, verbose_name="Descripción")
    is_active = models.BooleanField(default=True, verbose_name="Activo")

    class Meta:
        verbose_name = "Categoría de Tarea"
        verbose_name_plural = "Categorías de Tareas"

    def __str__(self):
        return self.name


class TaskSubCategory(ModelApi):
    """Subcategoría de tarea."""
    category = models.ForeignKey(
        TaskCategory, 
        on_delete=models.CASCADE, 
        related_name="subcategories", 
        verbose_name="Categoría Principal"
    )
    name = models.CharField(max_length=200, verbose_name="Nombre Subcategoría")

    class Meta:
        verbose_name = "Subcategoría de Tarea"
        verbose_name_plural = "Subcategorías de Tareas"

    def __str__(self):
        return f"{self.name} ({self.category.name})"


class TaskType(ModelApi):
    """
    Tipo de tarea (ej: Visita, Llamada, Instalación, Mantenimiento).
    Define la naturaleza de la actividad.
    """
    name = models.CharField(max_length=200, verbose_name="Nombre del Tipo")
    icon = models.CharField(max_length=50, blank=True, verbose_name="Icono (FontAwesome)")
    color_code = models.CharField(max_length=20, default="#007bff", verbose_name="Color Hex")
    description = models.TextField(blank=True, verbose_name="Descripción")
    
    # Indica si este tipo de tarea requiere respuesta
    requires_response = models.BooleanField(
        default=False, 
        verbose_name="Requiere Respuesta",
        help_text="Si está marcado, la tarea debe tener una respuesta para completarse."
    )

    class Meta:
        verbose_name = "Tipo de Tarea"
        verbose_name_plural = "Tipos de Tareas"

    def __str__(self):
        return self.name


class TaskSubType(ModelApi):
    """Subtipo de tarea."""
    task_type = models.ForeignKey(
        TaskType, 
        on_delete=models.CASCADE, 
        related_name="subtypes", 
        verbose_name="Tipo Principal"
    )
    name = models.CharField(max_length=200, verbose_name="Nombre Subtipo")

    class Meta:
        verbose_name = "Subtipo de Tarea"
        verbose_name_plural = "Subtipos de Tareas"

    def __str__(self):
        return f"{self.name} ({self.task_type.name})"


class CrmTask(ModelApi):
    """Tasks for commercial and technical field activities."""

    PRIORITY_CHOICES = [
        ("LOW", "Baja"),
        ("MEDIUM", "Media"),
        ("HIGH", "Alta"),
        ("CRITICAL", "Crítica"),
    ]

    STATUS_CHOICES = [
        ("PENDING", "Pendiente"),
        ("IN_PROGRESS", "En Proceso"),
        ("AWAITING_RESPONSE", "Esperando Respuesta"),
        ("COMPLETED", "Completada"),
        ("CANCELLED", "Cancelada"),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="tasks")
    title = models.CharField(max_length=300, verbose_name="Título de la Tarea")
    description = models.TextField(verbose_name="Descripción Detallada", blank=True)
    
    # Clasificación por Categoría (área)
    category = models.ForeignKey(
        TaskCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Categoría",
        related_name="tasks"
    )
    subcategory = models.ForeignKey(
        TaskSubCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Subcategoría",
        related_name="tasks"
    )
    
    # Clasificación por Tipo (naturaleza de la actividad)
    task_type = models.ForeignKey(
        TaskType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Tipo de Tarea",
        related_name="tasks"
    )
    task_subtype = models.ForeignKey(
        TaskSubType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Subtipo",
        related_name="tasks"
    )
    
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default="MEDIUM", verbose_name="Prioridad")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="PENDING", verbose_name="Estado")
    
    due_date = models.DateTimeField(verbose_name="Fecha Límite", blank=True, null=True)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name="crm_tasks",
        verbose_name="Asignado a"
    )
    
    # Contactos del cliente asociados a la tarea
    contacts = models.ManyToManyField(
        Person,
        blank=True,
        related_name="tasks",
        verbose_name="Contactos Asociados",
        help_text="Personas del cliente involucradas en esta tarea."
    )
    
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name="Completada en")
    
    # Archivos adjuntos a la tarea
    documents = models.ManyToManyField(
        "documents.Document",
        blank=True,
        related_name="crm_tasks",
        verbose_name="Archivos Adjuntos"
    )

    class Meta:
        verbose_name = "Tarea CRM"
        verbose_name_plural = "Tareas CRM"
        ordering = ["-priority", "due_date"]

    def __str__(self):
        return f"{self.title} - {self.project.name}"



class TaskResponse(ModelApi):
    """
    Respuesta a una tarea CRM.
    Permite registrar el resultado de una actividad con archivos adjuntos.
    """
    task = models.ForeignKey(
        CrmTask,
        on_delete=models.CASCADE,
        related_name="responses",
        verbose_name="Tarea"
    )
    
    responded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="task_responses",
        verbose_name="Respondido por"
    )
    
    content = models.TextField(verbose_name="Contenido de la Respuesta")
    
    # Archivos adjuntos a la respuesta
    documents = models.ManyToManyField(
        "documents.Document",
        blank=True,
        related_name="task_responses",
        verbose_name="Archivos Adjuntos"
    )
    
    # Metadata
    response_date = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Respuesta")

    class Meta:
        verbose_name = "Respuesta de Tarea"
        verbose_name_plural = "Respuestas de Tareas"
        ordering = ['-response_date']

    def __str__(self):
        return f"Respuesta a: {self.task.title}"


# =============================================================================
# LEVANTAMIENTO TÉCNICO - DINÁMICO
# =============================================================================

class SurveyFieldType(ModelApi):
    """
    Tipo de dato para campos dinámicos de levantamiento.
    Define si el campo es texto, número entero, decimal, fecha, etc.
    """
    DATA_TYPES = [
        ("TEXT", "Texto"),
        ("INTEGER", "Número Entero"),
        ("DECIMAL", "Número Decimal"),
        ("BOOLEAN", "Sí/No"),
        ("DATE", "Fecha"),
        ("DATETIME", "Fecha y Hora"),
        ("SELECT", "Lista de Opciones"),
        ("FILE", "Archivo"),
    ]
    
    name = models.CharField(max_length=100, verbose_name="Nombre del Tipo")
    data_type = models.CharField(
        max_length=20, 
        choices=DATA_TYPES, 
        default="TEXT",
        verbose_name="Tipo de Dato"
    )
    
    # Para tipo SELECT: opciones disponibles
    options = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Opciones",
        help_text="Para tipo SELECT: ['Opción 1', 'Opción 2', ...]"
    )
    
    # Validaciones opcionales
    min_value = models.FloatField(null=True, blank=True, verbose_name="Valor Mínimo")
    max_value = models.FloatField(null=True, blank=True, verbose_name="Valor Máximo")
    regex_pattern = models.CharField(
        max_length=500, 
        blank=True, 
        verbose_name="Patrón Regex",
        help_text="Expresión regular para validar texto"
    )

    class Meta:
        verbose_name = "Tipo de Campo de Levantamiento"
        verbose_name_plural = "Tipos de Campos de Levantamiento"

    def __str__(self):
        return f"{self.name} ({self.get_data_type_display()})"


class SurveyFieldDefinition(ModelApi):
    """
    Definición de un campo para levantamientos técnicos.
    Define qué datos se deben capturar en terreno.
    """
    name = models.CharField(max_length=200, verbose_name="Nombre del Campo")
    code = models.CharField(
        max_length=100, 
        unique=True, 
        verbose_name="Código",
        help_text="Identificador único (ej: pipe_diameter, signal_strength)"
    )
    field_type = models.ForeignKey(
        SurveyFieldType,
        on_delete=models.PROTECT,
        related_name="field_definitions",
        verbose_name="Tipo de Dato"
    )
    
    # Agrupación
    group = models.CharField(
        max_length=100, 
        blank=True, 
        verbose_name="Grupo",
        help_text="Agrupa campos relacionados (ej: Hidráulica, Eléctrica, Logística)"
    )
    
    # Configuración
    is_required = models.BooleanField(default=False, verbose_name="Es Obligatorio")
    default_value = models.CharField(max_length=500, blank=True, verbose_name="Valor por Defecto")
    help_text = models.TextField(blank=True, verbose_name="Texto de Ayuda")
    order = models.IntegerField(default=0, verbose_name="Orden de Presentación")
    
    is_active = models.BooleanField(default=True, verbose_name="Activo")

    class Meta:
        verbose_name = "Definición de Campo de Levantamiento"
        verbose_name_plural = "Definiciones de Campos de Levantamiento"
        ordering = ['group', 'order', 'name']

    def __str__(self):
        return f"{self.name} ({self.code})"


class TechnicalSurvey(ModelApi):
    """
    Levantamiento Técnico - Dinámico.
    
    Los campos fijos son mínimos. Los datos específicos se almacenan
    en 'dynamic_data' usando SurveyFieldDefinition como plantilla.
    """

    project = models.ForeignKey(
        Project, 
        on_delete=models.CASCADE, 
        related_name="technical_surveys",
        verbose_name="Proyecto"
    )
    
    # Identificación del levantamiento
    name = models.CharField(
        max_length=200, 
        verbose_name="Nombre del Levantamiento",
        blank=True,
        help_text="Ej: Pozo Norte, Sector A, etc."
    )
    
    # Campos esenciales que siempre se necesitan
    gps_coordinates = models.CharField(
        max_length=100, 
        verbose_name="Coordenadas GPS", 
        blank=True
    )
    survey_date = models.DateField(
        blank=True, 
        null=True, 
        verbose_name="Fecha del Levantamiento"
    )
    surveyed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="surveys_conducted",
        verbose_name="Realizado por"
    )
    
    # Datos dinámicos basados en SurveyFieldDefinition
    dynamic_data = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Datos del Levantamiento",
        help_text="Formato: {'field_code': value, ...}"
    )
    
    # Pre-Configuración y Factibilidad
    requires_dga = models.BooleanField(default=False, verbose_name="¿Requiere Reporte DGA?")
    requires_telemetry = models.BooleanField(default=True, verbose_name="¿Requiere Telemetría?")
    
    # Notas y recomendaciones
    recommendations = models.TextField(verbose_name="Recomendaciones Técnicas", blank=True)
    notes = models.TextField(verbose_name="Notas Adicionales", blank=True)
    
    # Archivos adjuntos (fotos, documentos de terreno)
    documents = models.ManyToManyField(
        "documents.Document",
        blank=True,
        related_name="technical_surveys",
        verbose_name="Archivos Adjuntos"
    )
    
    # Estado del levantamiento
    STATUS_CHOICES = [
        ("DRAFT", "Borrador"),
        ("IN_PROGRESS", "En Progreso"),
        ("COMPLETED", "Completado"),
        ("APPROVED", "Aprobado"),
        ("REJECTED", "Rechazado"),
    ]
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="DRAFT",
        verbose_name="Estado"
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Activo",
        help_text="Desmarcar para desactivar este levantamiento sin eliminarlo."
    )

    class Meta:
        verbose_name = "Levantamiento Técnico"
        verbose_name_plural = "Levantamientos Técnicos"
        ordering = ['-survey_date', '-created']


    def __str__(self):
        return f"{self.name or 'Levantamiento'} - {self.project.name}"
    
    def get_field_value(self, field_code, default=None):
        """Obtiene el valor de un campo dinámico."""
        return self.dynamic_data.get(field_code, default)
    
    def set_field_value(self, field_code, value):
        """Establece el valor de un campo dinámico."""
        self.dynamic_data[field_code] = value
