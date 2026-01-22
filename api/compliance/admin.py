"""
Compliance Admin
================
Administración de modelos de cumplimiento normativo.
"""

from django.contrib import admin
from django.utils.html import format_html

from api.compliance.models import (
    ComplianceProvider,
    PointComplianceConfig,
    ManualComplianceRecord,
    ComplianceStandard,
)


class PointComplianceConfigInline(admin.TabularInline):
    """Inline for viewing point configurations in provider admin."""
    model = PointComplianceConfig
    extra = 0
    fields = ('point', 'send_compliance', 'data_source', 'is_active', 'last_success')
    readonly_fields = ('last_success',)
    autocomplete_fields = ('point',)
    show_change_link = True


@admin.register(ComplianceProvider)
class ComplianceProviderAdmin(admin.ModelAdmin):
    """Admin for Compliance Providers (DGA, SMA, etc.)"""
    
    list_display = (
        'name', 'display_name', 'service_type_badge', 
        'auth_method_badge', 'submission_frequency', 'is_active'
    )
    list_filter = ('service_type', 'auth_method', 'submission_frequency', 'is_active')
    search_fields = ('name', 'display_name', 'base_url')
    readonly_fields = ('created', 'modified')
    inlines = [PointComplianceConfigInline]
    
    fieldsets = (
        ('Información Básica', {
            'fields': ('name', 'display_name', 'description', 'service_type', 'is_active')
        }),
        ('Conexión', {
            'fields': ('base_url', 'auth_endpoint', 'data_endpoint_template', 'timeout_seconds')
        }),
        ('Autenticación', {
            'fields': ('auth_method', 'auth_config'),
            'classes': ('collapse',),
            'description': 'Credenciales por defecto. Se pueden sobrescribir por punto.'
        }),
        ('Templates', {
            'fields': ('payload_template', 'response_mapping'),
            'classes': ('collapse',),
            'description': 'Templates JSON para construir payloads y parsear respuestas.'
        }),
        ('Campos Requeridos', {
            'fields': ('required_fields', 'data_variables'),
            'classes': ('collapse',),
            'description': 'Define los campos que cada punto debe configurar.'
        }),
        ('Envío', {
            'fields': ('submission_frequency', 'max_retries', 'retry_delay_seconds')
        }),
        ('Metadatos', {
            'fields': ('documentation_url', 'created', 'modified'),
            'classes': ('collapse',)
        }),
    )

    def service_type_badge(self, obj):
        colors = {
            'water_rights': '#3498db',
            'environmental': '#27ae60',
            'energy': '#f39c12',
            'custom': '#9b59b6',
        }
        color = colors.get(obj.service_type, '#95a5a6')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; '
            'border-radius: 3px; font-size: 11px;">{}</span>',
            color, obj.get_service_type_display()
        )
    service_type_badge.short_description = 'Tipo'

    def auth_method_badge(self, obj):
        return format_html(
            '<span style="background-color: #eee; padding: 2px 5px; border-radius: 3px;">{}</span>',
            obj.get_auth_method_display()
        )
    auth_method_badge.short_description = 'Auth'


@admin.register(ComplianceStandard)
class ComplianceStandardAdmin(admin.ModelAdmin):
    """Admin para estándares de cumplimiento (DGA/SMA)."""
    list_display = ('code', 'name', 'frequency_type', 'records_per_period', 'is_active')
    list_filter = ('frequency_type', 'is_active')
    search_fields = ('code', 'name', 'description')
    
    fieldsets = (
        ('Información Básica', {
            'fields': ('code', 'name', 'description', 'is_active')
        }),
        ('Configuración de Frecuencia', {
            'fields': ('frequency_type', 'hour', 'minute', 'day_of_month', 'months', 'records_per_period')
        }),
    )

class ManualComplianceRecordInline(admin.TabularInline):
    """Inline for viewing manual records in point config."""
    model = ManualComplianceRecord
    extra = 0
    fields = ('measurement_timestamp', 'status', 'voucher', 'created')
    readonly_fields = ('measurement_timestamp', 'status', 'voucher', 'created')
    show_change_link = True


@admin.register(PointComplianceConfig)
class PointComplianceConfigAdmin(admin.ModelAdmin):
    """Admin for Point Compliance Configurations."""
    
    list_display = (
        'point_title', 'provider_name', 'compliance_standard', 'send_compliance', 
        'data_source', 'is_active', 'success_rate', 'last_success_display'
    )
    list_filter = (
        'provider__name', 'compliance_standard__code', 
        'send_compliance', 'data_source', 'is_active'
    )
    search_fields = ('point__title', 'provider__name', 'compliance_standard__name')
    autocomplete_fields = ('point', 'provider', 'compliance_standard')
    readonly_fields = (
        'last_submission', 'last_success', 'last_error', 
        'error_count', 'total_submissions', 'successful_submissions'
    )
    inlines = [ManualComplianceRecordInline]
    
    fieldsets = (
        ('Configuración Principal', {
            'fields': ('point', 'provider', 'compliance_standard', 'is_active', 'send_compliance', 'data_source')
        }),
        ('Datos del Punto', {
            'fields': ('config_data',),
            'description': 'Configuración específica del punto (código obra, RUT, etc.)'
        }),
        ('Credenciales (Opcional)', {
            'fields': ('credentials_override',),
            'classes': ('collapse',),
            'description': 'Si vacío, usa las credenciales del proveedor.'
        }),
        ('Estadísticas', {
            'fields': (
                'total_submissions', 'successful_submissions', 
                'last_submission', 'last_success', 'error_count', 'last_error'
            ),
            'classes': ('collapse',)
        }),
    )

    def point_title(self, obj):
        return obj.point.title
    point_title.short_description = 'Punto'
    point_title.admin_order_field = 'point__title'

    def provider_name(self, obj):
        return obj.provider.display_name
    provider_name.short_description = 'Proveedor'
    provider_name.admin_order_field = 'provider__name'

    def success_rate(self, obj):
        if obj.total_submissions == 0:
            return '-'
        rate = (obj.successful_submissions / obj.total_submissions) * 100
        color = '#27ae60' if rate >= 90 else '#f39c12' if rate >= 70 else '#e74c3c'
        return format_html(
            '<span style="color: {}; font-weight: bold;">{:.0f}%</span>',
            color, rate
        )
    success_rate.short_description = 'Éxito'

    def last_success_display(self, obj):
        if obj.last_success:
            return obj.last_success.strftime('%Y-%m-%d %H:%M')
        return '-'
    last_success_display.short_description = 'Último Éxito'


@admin.register(ManualComplianceRecord)
class ManualComplianceRecordAdmin(admin.ModelAdmin):
    """Admin for Manual Compliance Records."""
    
    list_display = (
        'point_name', 'provider_name', 'measurement_timestamp',
        'status_badge', 'voucher', 'created_by'
    )
    list_filter = ('config__provider__name', 'status', 'measurement_timestamp')
    search_fields = ('config__point__title', 'voucher')
    readonly_fields = ('response_data', 'submitted_at', 'created', 'modified')
    autocomplete_fields = ('config', 'created_by')
    
    fieldsets = (
        ('Registro', {
            'fields': ('config', 'measurement_timestamp', 'data', 'created_by')
        }),
        ('Estado de Envío', {
            'fields': ('status', 'voucher', 'error_message', 'submitted_at')
        }),
        ('Respuesta del Servicio', {
            'fields': ('response_data',),
            'classes': ('collapse',)
        }),
    )

    def point_name(self, obj):
        return obj.config.point.title
    point_name.short_description = 'Punto'

    def provider_name(self, obj):
        return obj.config.provider.name.upper()
    provider_name.short_description = 'Proveedor'

    def status_badge(self, obj):
        colors = {
            'pending': '#f39c12',
            'queued': '#3498db',
            'sent': '#27ae60',
            'error': '#e74c3c',
            'cancelled': '#95a5a6',
        }
        color = colors.get(obj.status, '#95a5a6')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; '
            'border-radius: 3px; font-size: 11px;">{}</span>',
            color, obj.get_status_display()
        )
    status_badge.short_description = 'Estado'
