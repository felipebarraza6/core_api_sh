"""
CRM Admin Configuration - V2.0
"""

from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse

from .models import (
    Client, JobPosition, Project, Person,
    CostCategory, CostSubCategory, CostType, CostSubType, ProjectCost,
    TaskCategory, TaskSubCategory, TaskType, TaskSubType, CrmTask, TaskResponse,
    SurveyFieldType, SurveyFieldDefinition, TechnicalSurvey
)


# =============================================================================
# INLINES
# =============================================================================

class JobPositionInline(admin.TabularInline):
    model = JobPosition
    extra = 0
    fields = ('name', 'department')


class PersonInline(admin.TabularInline):
    model = Person
    extra = 0
    fields = ('name', 'email', 'phone', 'job_position')


class ProjectCostInline(admin.TabularInline):
    model = ProjectCost
    extra = 0
    fields = ('description', 'category', 'cost_type', 'amount', 'is_estimated', 'date')
    show_change_link = True


class TechnicalSurveyInline(admin.TabularInline):
    model = TechnicalSurvey
    extra = 0
    can_delete = True
    verbose_name_plural = 'Levantamientos Técnicos'
    fields = ('name', 'survey_date', 'requires_telemetry', 'requires_dga', 'gps_coordinates')
    show_change_link = True


class TaskResponseInline(admin.StackedInline):
    model = TaskResponse
    extra = 0
    readonly_fields = ('response_date', 'responded_by')
    fields = ('content', 'documents', 'responded_by', 'response_date')
    filter_horizontal = ('documents',)


class CostSubTypeInline(admin.TabularInline):
    model = CostSubType
    extra = 1


class TaskSubTypeInline(admin.TabularInline):
    model = TaskSubType
    extra = 1


class CostSubCategoryInline(admin.TabularInline):
    model = CostSubCategory
    extra = 1


class TaskSubCategoryInline(admin.TabularInline):
    model = TaskSubCategory
    extra = 1


# =============================================================================
# CLIENTE Y CARGOS
# =============================================================================

@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ("name", "rut", "status", "email", "phone", "job_positions_count")
    list_filter = ("status", "business_type")
    search_fields = ("name", "rut", "email")
    inlines = [JobPositionInline]
    
    def job_positions_count(self, obj):
        count = obj.job_positions.count()
        return f"{count} cargos"
    job_positions_count.short_description = "Cargos"


@admin.register(JobPosition)
class JobPositionAdmin(admin.ModelAdmin):
    list_display = ("name", "client", "department")
    list_filter = ("client", "department")
    search_fields = ("name", "department", "client__name")


# =============================================================================
# PROYECTO Y CONTACTOS
# =============================================================================

@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "client", "status", "budget", "start_date", "surveys_count", "costs_count")
    list_filter = ("status", "client")
    search_fields = ("name", "code_internal", "client__name")
    inlines = [TechnicalSurveyInline, PersonInline, ProjectCostInline]
    date_hierarchy = 'start_date'
    
    def surveys_count(self, obj):
        return obj.technical_surveys.count()
    surveys_count.short_description = "Levantamientos"
    
    def costs_count(self, obj):
        return obj.costs.count()
    costs_count.short_description = "Costos"


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    list_display = ("name", "project", "job_position", "email", "phone")
    list_filter = ("project", "job_position")
    search_fields = ("name", "email", "job_position__name", "project__name")


# =============================================================================
# COSTOS - CATEGORÍAS Y TIPOS
# =============================================================================

@admin.register(CostCategory)
class CostCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "subcategories_count", "is_active")
    search_fields = ("name",)
    list_filter = ("is_active",)
    inlines = [CostSubCategoryInline]
    
    def subcategories_count(self, obj):
        return obj.subcategories.count()
    subcategories_count.short_description = "Subcategorías"


@admin.register(CostSubCategory)
class CostSubCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "category")
    list_filter = ("category",)
    search_fields = ("name", "category__name")


@admin.register(CostType)
class CostTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "flow", "color_display", "subtypes_count")
    list_filter = ("flow",)
    search_fields = ("name",)
    inlines = [CostSubTypeInline]
    
    def color_display(self, obj):
        return format_html(
            '<span style="background-color: {}; padding: 2px 10px; border-radius: 3px;">&nbsp;</span>',
            obj.color_code
        )
    color_display.short_description = "Color"
    
    def subtypes_count(self, obj):
        return obj.subtypes.count()
    subtypes_count.short_description = "Subtipos"


@admin.register(CostSubType)
class CostSubTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "cost_type")
    list_filter = ("cost_type",)
    search_fields = ("name", "cost_type__name")


@admin.register(ProjectCost)
class ProjectCostAdmin(admin.ModelAdmin):
    list_display = ("project", "description", "category", "cost_type", "amount", "is_estimated", "date")
    list_filter = ("category", "cost_type", "is_estimated", "project")
    search_fields = ("description", "project__name", "category__name")
    filter_horizontal = ('documents',)
    date_hierarchy = 'date'
    
    fieldsets = (
        (None, {
            'fields': ('project', 'description', 'amount', 'is_estimated', 'date')
        }),
        ('Clasificación', {
            'fields': ('category', 'subcategory', 'cost_type', 'cost_subtype')
        }),
        ('Documentos', {
            'fields': ('documents',)
        }),
    )


# =============================================================================
# TAREAS
# =============================================================================

@admin.register(TaskCategory)
class TaskCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "color_display", "subcategories_count", "is_active")
    search_fields = ("name",)
    list_filter = ("is_active",)
    inlines = [TaskSubCategoryInline]
    
    def color_display(self, obj):
        return format_html(
            '<span style="background-color: {}; padding: 2px 10px; border-radius: 3px;">&nbsp;</span>',
            obj.color_code
        )
    color_display.short_description = "Color"
    
    def subcategories_count(self, obj):
        return obj.subcategories.count()
    subcategories_count.short_description = "Subcategorías"


@admin.register(TaskSubCategory)
class TaskSubCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "category")
    list_filter = ("category",)
    search_fields = ("name", "category__name")


@admin.register(TaskType)
class TaskTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "color_display", "requires_response", "subtypes_count")
    list_filter = ("requires_response",)
    search_fields = ("name",)
    inlines = [TaskSubTypeInline]
    
    def color_display(self, obj):
        return format_html(
            '<span style="background-color: {}; padding: 2px 10px; border-radius: 3px;">&nbsp;</span>',
            obj.color_code
        )
    color_display.short_description = "Color"
    
    def subtypes_count(self, obj):
        return obj.subtypes.count()
    subtypes_count.short_description = "Subtipos"


@admin.register(TaskSubType)
class TaskSubTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "task_type")
    list_filter = ("task_type",)
    search_fields = ("name", "task_type__name")


@admin.register(CrmTask)
class CrmTaskAdmin(admin.ModelAdmin):
    list_display = ("title", "project", "category", "task_type", "priority", "status", "due_date", "assigned_to", "responses_count")
    list_editable = ("status", "priority")
    list_filter = ("status", "priority", "category", "task_type", "assigned_to")
    search_fields = ("title", "description", "project__name")
    date_hierarchy = 'due_date'
    filter_horizontal = ('documents', 'contacts')
    inlines = [TaskResponseInline]
    
    fieldsets = (
        (None, {
            'fields': ('project', 'title', 'description')
        }),
        ('Clasificación', {
            'fields': (('category', 'subcategory'), ('task_type', 'task_subtype'))
        }),
        ('Participantes y Fechas', {
            'fields': (('priority', 'status'), ('assigned_to', 'due_date'), 'contacts', 'completed_at')
        }),
        ('Archivos', {
            'fields': ('documents',),
            'classes': ('collapse',)
        }),
    )

    
    def responses_count(self, obj):
        count = obj.responses.count()
        if count > 0:
            return format_html('<span style="color: green;">✓ {} respuestas</span>', count)
        return "—"
    responses_count.short_description = "Respuestas"


@admin.register(TaskResponse)
class TaskResponseAdmin(admin.ModelAdmin):
    list_display = ("task", "responded_by", "response_date", "content_preview")
    list_filter = ("responded_by", "response_date")
    search_fields = ("content", "task__title")
    filter_horizontal = ('documents',)
    readonly_fields = ('response_date',)
    
    def content_preview(self, obj):
        return obj.content[:100] + "..." if len(obj.content) > 100 else obj.content
    content_preview.short_description = "Contenido"


# =============================================================================
# LEVANTAMIENTO TÉCNICO DINÁMICO
# =============================================================================

@admin.register(SurveyFieldType)
class SurveyFieldTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "data_type", "min_value", "max_value")
    list_filter = ("data_type",)
    search_fields = ("name",)


@admin.register(SurveyFieldDefinition)
class SurveyFieldDefinitionAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "field_type", "group", "is_required", "is_active", "order")
    list_filter = ("field_type", "group", "is_required", "is_active")
    list_editable = ("order", "is_active")
    search_fields = ("name", "code", "group")
    ordering = ('group', 'order', 'name')


@admin.register(TechnicalSurvey)
class TechnicalSurveyAdmin(admin.ModelAdmin):
    list_display = ("name", "project", "survey_date", "surveyed_by", "requires_telemetry", "requires_dga", "get_generated_point")
    list_filter = ("requires_telemetry", "requires_dga", "survey_date", "project")
    search_fields = ("name", "project__name", "gps_coordinates")
    filter_horizontal = ('documents',)
    date_hierarchy = 'survey_date'
    readonly_fields = ("get_generated_point_link",)
    
    fieldsets = (
        (None, {
            'fields': ('project', 'name', 'survey_date', 'surveyed_by', 'gps_coordinates')
        }),
        ('Punto de Captación Generado', {
            'fields': ('get_generated_point_link',),
            'description': 'El punto de captación creado a partir de este levantamiento técnico.'
        }),
        ('Configuración', {
            'fields': ('requires_telemetry', 'requires_dga')
        }),
        ('Datos Dinámicos', {
            'fields': ('dynamic_data',),
            'description': 'Datos capturados según las definiciones de campos configuradas.'
        }),
        ('Notas', {
            'fields': ('recommendations', 'notes')
        }),
        ('Archivos', {
            'fields': ('documents',),
            'classes': ('collapse',)
        }),
    )

    def get_generated_point(self, obj):
        """Return the generated point name or indicator."""
        if hasattr(obj, 'generated_point') and obj.generated_point:
            return obj.generated_point.title or f"Punto #{obj.generated_point.id}"
        return "—"
    get_generated_point.short_description = "Punto Generado"

    def get_generated_point_link(self, obj):
        """Return a link to the generated CatchmentPoint."""
        if hasattr(obj, 'generated_point') and obj.generated_point:
            url = reverse('admin:telemetry_catchmentpoint_change', args=[obj.generated_point.id])
            return format_html('<a href="{}">{}</a>', url, obj.generated_point.title or f"Punto #{obj.generated_point.id}")
        return "Sin punto generado aún. Cree un Punto de Captación y vincúlelo a este levantamiento."
    get_generated_point_link.short_description = "Punto de Captación"
