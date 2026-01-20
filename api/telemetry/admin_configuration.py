"""
Admin para modelos de configuración dinámica.
"""

from django.contrib import admin
from django.utils.html import format_html
from django.forms import TextInput, Textarea
from django.db import models

from .models.configuration import (
    ConfigurationScheme,
    ConfigurationSchemeField,
    PointConfigurationValue,
    SamplingFrequency,
    VariableType,
)


class ConfigurationSchemeFieldInline(admin.TabularInline):
    """Inline para campos de esquema."""
    model = ConfigurationSchemeField
    extra = 1
    fields = (
        'code', 'name', 'data_type', 'unit', 'default_value',
        'is_required', 'is_formula_accessible', 'display_order'
    )
    formfield_overrides = {
        models.CharField: {'widget': TextInput(attrs={'size': 20})},
        models.TextField: {'widget': Textarea(attrs={'rows': 2, 'cols': 40})},
    }


@admin.register(ConfigurationScheme)
class ConfigurationSchemeAdmin(admin.ModelAdmin):
    """Admin para esquemas de configuración."""
    list_display = ('name', 'code', 'category', 'fields_count', 'is_active')
    list_filter = ('category', 'is_active')
    search_fields = ('name', 'code', 'description')
    readonly_fields = ('created', 'modified')
    inlines = [ConfigurationSchemeFieldInline]
    
    fieldsets = (
        ('Información Básica', {
            'fields': ('name', 'code', 'description', 'category', 'is_active')
        }),
        ('Auditoría', {
            'fields': ('created', 'modified'),
            'classes': ('collapse',)
        }),
    )
    
    def fields_count(self, obj):
        """Mostrar cantidad de campos."""
        return obj.fields.count()
    fields_count.short_description = 'Campos'


@admin.register(ConfigurationSchemeField)
class ConfigurationSchemeFieldAdmin(admin.ModelAdmin):
    """Admin para campos de esquema."""
    list_display = ('scheme', 'code', 'name', 'data_type', 'unit', 'is_required', 'display_order')
    list_filter = ('scheme', 'data_type', 'is_required', 'is_formula_accessible')
    search_fields = ('code', 'name', 'scheme__name')
    readonly_fields = ('created', 'modified')
    
    fieldsets = (
        ('Información Básica', {
            'fields': ('scheme', 'code', 'name', 'description')
        }),
        ('Tipo y Validación', {
            'fields': (
                'data_type', 'unit', 'default_value',
                'min_value', 'max_value', 'is_required'
            )
        }),
        ('Fórmulas', {
            'fields': ('is_formula_accessible',),
            'description': 'Si está marcado, este campo puede usarse en fórmulas como {config.code}'
        }),
        ('Presentación', {
            'fields': ('display_order', 'help_text')
        }),
        ('Auditoría', {
            'fields': ('created', 'modified'),
            'classes': ('collapse',)
        }),
    )


class PointConfigurationValueInline(admin.TabularInline):
    """Inline para valores de configuración en CatchmentPoint."""
    model = PointConfigurationValue
    extra = 0
    fields = ('field', 'value')
    readonly_fields = ('field',)
    
    def has_add_permission(self, request, obj=None):
        """No permitir agregar directamente, se crean desde el esquema."""
        return False


@admin.register(PointConfigurationValue)
class PointConfigurationValueAdmin(admin.ModelAdmin):
    """Admin para valores de configuración."""
    list_display = ('point', 'field', 'value_display', 'modified')
    list_filter = ('field__scheme', 'field__data_type')
    search_fields = ('point__title', 'field__code', 'field__name')
    readonly_fields = ('created', 'modified')
    autocomplete_fields = ('point', 'field')
    
    def value_display(self, obj):
        """Mostrar valor formateado."""
        if isinstance(obj.value, (int, float)):
            return f"{obj.value} {obj.field.unit or ''}".strip()
        return str(obj.value)
    value_display.short_description = 'Valor'


@admin.register(SamplingFrequency)
class SamplingFrequencyAdmin(admin.ModelAdmin):
    """Admin para frecuencias de muestreo."""
    list_display = ('name', 'code', 'minutes', 'cron_expression', 'points_count', 'is_active', 'display_order')
    list_filter = ('is_active',)
    search_fields = ('name', 'code')
    readonly_fields = ('created', 'modified')
    
    fieldsets = (
        ('Información Básica', {
            'fields': ('code', 'name', 'minutes', 'cron_expression', 'is_active', 'display_order')
        }),
        ('Auditoría', {
            'fields': ('created', 'modified'),
            'classes': ('collapse',)
        }),
    )
    
    def points_count(self, obj):
        """Mostrar cantidad de puntos usando esta frecuencia."""
        return obj.points.count()
    points_count.short_description = 'Puntos'


@admin.register(VariableType)
class VariableTypeAdmin(admin.ModelAdmin):
    """Admin para tipos de variables."""
    list_display = ('name', 'code', 'default_unit', 'variables_count', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name', 'code', 'description')
    readonly_fields = ('created', 'modified')
    
    fieldsets = (
        ('Información Básica', {
            'fields': ('code', 'name', 'description', 'is_active')
        }),
        ('Procesamiento', {
            'fields': ('default_formula', 'required_inputs', 'default_unit'),
            'description': 'Configuración por defecto para este tipo de variable'
        }),
        ('Auditoría', {
            'fields': ('created', 'modified'),
            'classes': ('collapse',)
        }),
    )
    
    formfield_overrides = {
        models.CharField: {'widget': Textarea(attrs={'rows': 3, 'cols': 80})},
    }
    
    def variables_count(self, obj):
        """Mostrar cantidad de variables usando este tipo."""
        return obj.variables.count()
    variables_count.short_description = 'Variables'
