"""
CRM Admin Configuration
"""

from django.contrib import admin
from .models import Client, Project, CrmTask, TechnicalSurvey, ProjectCost, Person, JobPosition, CostCategory, CostSubCategory, TaskCategory, TaskSubCategory


class PersonInline(admin.TabularInline):
    model = Person
    extra = 1


class ProjectCostInline(admin.TabularInline):
    model = ProjectCost
    extra = 1


class TechnicalSurveyInline(admin.StackedInline):
    model = TechnicalSurvey
    can_delete = False
    verbose_name_plural = 'Levantamiento Técnico'


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ("name", "rut", "status", "email", "phone")
    list_filter = ("status", "business_type")
    search_fields = ("name", "rut", "email")
    search_fields = ("name", "rut", "email")
    # inlines = [PersonInline]  # Removed as Person now links to Project


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "client", "status", "budget", "start_date")
    list_filter = ("status", "client")
    search_fields = ("name", "code_internal")
    inlines = [TechnicalSurveyInline, ProjectCostInline]
    date_hierarchy = 'start_date'
    inlines = [TechnicalSurveyInline, ProjectCostInline]
    date_hierarchy = 'start_date'


@admin.register(CrmTask)
class CrmTaskAdmin(admin.ModelAdmin):
    list_display = ("title", "project", "category", "subcategory", "priority", "status", "due_date", "assigned_to")
    list_editable = ("status", "priority")
    date_hierarchy = 'due_date'
    list_filter = ("status", "priority", "category", "subcategory", "due_date")
    search_fields = ("title", "description", "project__name", "category__name", "subcategory__name")
    
    fieldsets = (
        (None, {
            'fields': ('project', 'title', 'description', 'category', 'subcategory', 'priority', 'status')
        }),
        ('Asignación y Fechas', {
            'fields': ('assigned_to', 'due_date', 'completed_at')
        }),
    )


@admin.register(TechnicalSurvey)
class TechnicalSurveyAdmin(admin.ModelAdmin):
    list_display = ("project", "requires_telemetry", "requires_dga", "power_source")
    list_filter = ("power_source", "requires_telemetry", "requires_dga")
    fieldsets = (
        (None, {
            'fields': ('project', 'recommendations')
        }),
        ('Pre-Configuración', {
            'fields': ('requires_telemetry', 'requires_dga', 'proposed_start_date', 'dga_water_rights_code')
        }),
        ('Hidráulica', {
            'fields': ('pipe_diameter_inches', 'expected_max_flow', 'sensor_type_suggested')
        }),
        ('Eléctrica', {
            'fields': ('power_source', 'electrical_distance_meters')
        }),
        ('Logística', {
            'fields': ('signal_strength_dbm', 'access_complexity', 'gps_coordinates')
        }),
    )


@admin.register(ProjectCost)
class ProjectCostAdmin(admin.ModelAdmin):
    list_display = ("project", "category", "subcategory", "description", "amount", "is_estimated")
    list_filter = ("category", "subcategory", "is_estimated", "project")
    search_fields = ("description", "project__name", "category__name", "subcategory__name")
    filter_horizontal = ('documents',)


@admin.register(CostCategory)
class CostCategoryAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(CostSubCategory)
class CostSubCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "category")
    list_filter = ("category",)
    search_fields = ("name", "category__name")


@admin.register(TaskCategory)
class TaskCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "color_code")
    search_fields = ("name",)


@admin.register(TaskSubCategory)
class TaskSubCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "category")
    list_filter = ("category",)
    search_fields = ("name", "category__name")


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    list_display = ("name", "project", "job_position", "email", "phone")
    list_filter = ("project", "job_position")
    search_fields = ("name", "email", "job_position__name", "project__name")


@admin.register(JobPosition)
class JobPositionAdmin(admin.ModelAdmin):
    list_display = ("name", "department")
    list_filter = ("department",)
    search_fields = ("name", "department")
