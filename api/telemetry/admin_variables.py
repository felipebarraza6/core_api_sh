from django.contrib import admin
from .models.telemetry import TelemetryScheme, SchemeVariable, VirtualVariable, CoreVariable

class SchemeVariableInline(admin.TabularInline):
    model = SchemeVariable
    extra = 1
    fields = ('name', 'internal_code', 'type_variable', 'unit', 'is_active')

@admin.register(TelemetryScheme)
class TelemetrySchemeAdmin(admin.ModelAdmin):
    list_display = ('name', 'description')
    search_fields = ('name', 'description')
    inlines = [SchemeVariableInline]

@admin.register(CoreVariable)
class CoreVariableAdmin(admin.ModelAdmin):
    list_display = ('name', 'internal_code', 'point', 'type_definition', 'is_active')
    list_filter = ('is_active', 'type_definition')
    search_fields = ('name', 'internal_code', 'point__title', 'point__point_code')
    autocomplete_fields = ('point', 'type_definition')
    readonly_fields = ('created', 'modified')

@admin.register(VirtualVariable)
class VirtualVariableAdmin(admin.ModelAdmin):
    list_display = ('name', 'internal_code', 'scheme', 'is_active')
    list_filter = ('is_active', 'scheme')
    search_fields = ('name', 'internal_code', 'scheme__name')
    readonly_fields = ('created', 'modified')
