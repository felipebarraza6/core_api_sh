"""
Dynamic Registry Models
=======================
Modelos para la arquitectura de Server-Driven UI.
Permite definir módulos, vistas y acciones desde la base de datos.
"""

from django.db import models
from django.contrib.postgres.fields import ArrayField
from api.core.models.utils import ModelApi


class SystemModule(ModelApi):
    """
    Define un módulo funcional del sistema (ej: "Gestión de Pozos").
    Aparece en el menú principal.
    """
    name = models.CharField(max_length=100, verbose_name="Nombre")
    slug = models.SlugField(max_length=100, unique=True, verbose_name="Slug (URL)")
    description = models.TextField(blank=True, verbose_name="Descripción")
    
    icon = models.CharField(
        max_length=50, 
        default="extension",
        help_text="Nombre del icono (Material Design / FontAwesome)",
        verbose_name="Icono"
    )
    
    order = models.IntegerField(default=0, verbose_name="Orden de Menú")
    is_active = models.BooleanField(default=True, verbose_name="Activo")
    
    # Permisos requeridos para ver el módulo
    required_permissions = ArrayField(
        models.CharField(max_length=100),
        blank=True,
        default=list,
        help_text="Lista de codenames de permisos requeridos (OR logic)",
        verbose_name="Permisos Requeridos"
    )

    class Meta:
        verbose_name = "Módulo del Sistema"
        verbose_name_plural = "Módulos del Sistema"
        ordering = ['order', 'name']

    def __str__(self):
        return f"{self.name} ({self.slug})"


class ModuleView(ModelApi):
    """
    Define una vista/página dentro de un módulo.
    Puede ser una Tabla, Formulario, Dashboard, etc.
    """
    module = models.ForeignKey(
        SystemModule, 
        related_name='views', 
        on_delete=models.CASCADE,
        verbose_name="Módulo"
    )
    
    name = models.CharField(max_length=100, verbose_name="Nombre Vista")
    key = models.SlugField(
        max_length=100, 
        verbose_name="Clave Única (en módulo)",
        help_text="Identificador único dentro del módulo"
    )
    
    VIEW_TYPES = [
        ('TABLE', 'Tabla de Datos'),
        ('FORM', 'Formulario'),
        ('KANBAN', 'Tablero Kanban'),
        ('DASHBOARD', 'Dashboard / KPIs'),
        ('DETAIL', 'Detalle de Registro'),
    ]
    view_type = models.CharField(
        max_length=20, 
        choices=VIEW_TYPES, 
        default='TABLE',
        verbose_name="Tipo de Vista"
    )
    
    # Fuente de Datos
    data_source = models.CharField(
        max_length=200,
        blank=True,
        help_text="Endpoint API o QueryName para obtener datos",
        verbose_name="Fuente de Datos"
    )
    
    # Configuración de Layout (JSON Schema para frontend)
    layout_config = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Configuración Layout",
        help_text="Definición de columnas, filtros, campos, etc."
    )
    
    is_home = models.BooleanField(
        default=False, 
        verbose_name="Es Home",
        help_text="Si es la vista por defecto al entrar al módulo"
    )
    
    order = models.IntegerField(default=0, verbose_name="Orden tab/menú")

    class Meta:
        verbose_name = "Vista de Módulo"
        verbose_name_plural = "Vistas de Módulo"
        unique_together = ['module', 'key']
        ordering = ['module', 'order', 'name']

    def __str__(self):
        return f"{self.module.slug} -> {self.key}"


class DynamicAction(ModelApi):
    """
    Acción ejecutable en una vista (Botón, Menú contextual).
    """
    view = models.ForeignKey(
        ModuleView,
        related_name='actions',
        on_delete=models.CASCADE,
        verbose_name="Vista Asociada"
    )
    
    name = models.CharField(max_length=50, verbose_name="Nombre Acción")
    key = models.SlugField(max_length=50, verbose_name="Clave Acción")
    icon = models.CharField(max_length=50, blank=True, verbose_name="Icono")
    
    ACTION_TYPES = [
        ('API_CALL', 'Llamada API'),
        ('NAVIGATE', 'Navegar a URL'),
        ('OPEN_MODAL', 'Abrir Modal'),
        ('TRIGGER_JOB', 'Ejecutar Tarea Background'),
    ]
    action_type = models.CharField(
        max_length=20, 
        choices=ACTION_TYPES, 
        default='API_CALL',
        verbose_name="Tipo de Acción"
    )
    
    target = models.CharField(
        max_length=500,
        blank=True,
        help_text="URL destino, Endpoint API o ID de Job",
        verbose_name="Objetivo"
    )
    
    payload_schema = models.JSONField(
        default=dict,
        blank=True,
        help_text="Schema de datos requeridos (ej: confirmation message)",
        verbose_name="Schema Payload"
    )
    
    requires_confirmation = models.BooleanField(
        default=False,
        verbose_name="Requiere Confirmación"
    )
    
    class Meta:
        verbose_name = "Acción Dinámica"
        verbose_name_plural = "Acciones Dinámicas"
        ordering = ['view', 'name']

    def __str__(self):
        return f"{self.view} : {self.name}"


class AuditLog(ModelApi):
    """
    Registro de auditoría para operaciones realizadas vía Dynamic Proxy.
    Garantiza trazabilidad completa de cambios.
    """
    user = models.ForeignKey(
        'core.User', # Assuming core.User is the swappable user model or strict reference
        on_delete=models.SET_NULL,
        null=True,
        verbose_name="Usuario"
    )
    
    ACTION_CHOICES = [
        ('CREATE', 'Crear'),
        ('READ', 'Leer'),
        ('UPDATE', 'Actualizar'),
        ('DELETE', 'Eliminar'),
    ]
    action = models.CharField(max_length=10, choices=ACTION_CHOICES, verbose_name="Acción")
    
    # Resource Identifier (app.model)
    resource = models.CharField(max_length=100, verbose_name="Recurso")
    resource_id = models.CharField(max_length=100, verbose_name="ID Recurso")
    
    # Change Data
    payload = models.JSONField(
        default=dict, 
        blank=True, 
        verbose_name="Payload / Cambios"
    )
    
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name="IP Origen")
    user_agent = models.TextField(blank=True, verbose_name="User Agent")

    class Meta:
        verbose_name = "Registro de Auditoría"
        verbose_name_plural = "Registros de Auditoría"
        ordering = ['-created']

    def __str__(self):
        return f"[{self.created}] {self.user} - {self.action} {self.resource} ({self.resource_id})"


class DashboardWidget(ModelApi):
    """
    Componente visual dentro de un Dashboard (KPI Card, Gráfico, Lista).
    Permite construir paneles de control 100% configurables desde backend.
    """
    dashboard = models.ForeignKey(
        ModuleView,
        related_name='widgets',
        limit_choices_to={'view_type': 'DASHBOARD'},
        on_delete=models.CASCADE,
        verbose_name="Dashboard Padre"
    )
    
    WIDGET_TYPES = [
        ('KPI_CARD', 'Tarjeta KPI (Número Único)'),
        ('LINE_CHART', 'Gráfico de Línea'),
        ('BAR_CHART', 'Gráfico de Barras'),
        ('PIE_CHART', 'Gráfico de Torta'),
        ('GAUGE', 'Medidor / Gauge'),
        ('LIST_PREVIEW', 'Lista Resumida'),
    ]
    widget_type = models.CharField(max_length=20, choices=WIDGET_TYPES, default='KPI_CARD')
    
    title = models.CharField(max_length=100, verbose_name="Título Widget")
    description = models.CharField(max_length=200, blank=True, verbose_name="Subtítulo/Descripción")
    
    # URL del Data Proxy que alimenta este widget
    # Ej: /api/registry/proxy/telemetry/catchmentpoint/?aggregate=sum&field=flow
    data_source = models.CharField(max_length=500, verbose_name="Endpoint Fuente de Datos")
    
    refresh_interval = models.IntegerField(
        default=60, 
        help_text="Segundos para auto-refresco (0 = desactivado)",
        verbose_name="Intervalo Refresco (s)"
    )
    
    # Grid layout config (x, y, w, h) for frontend grid systems
    grid_config = models.JSONField(
        default=dict,
        blank=True,
        help_text="Posición en grilla: {x: 0, y: 0, w: 4, h: 2}",
        verbose_name="Configuración Grilla"
    )
    
    # Visual config (colors, icons, thresholds)
    visual_config = models.JSONField(
        default=dict,
        blank=True,
        help_text="Colores, iconos, umbrales de alerta",
        verbose_name="Configuración Visual"
    )
    
    order = models.IntegerField(default=0, verbose_name="Orden Sequencial")

    class Meta:
        verbose_name = "Widget de Dashboard"
        verbose_name_plural = "Widgets de Dashboard"
        ordering = ['dashboard', 'order']

    def __str__(self):
        return f"[{self.dashboard}] {self.title} ({self.widget_type})"
