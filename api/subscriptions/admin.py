"""
Subscriptions Admin
"""

from django.contrib import admin
from django.utils.html import format_html
from .models import IkoluModule, SubscriptionPlan, PointModuleAccess


@admin.register(IkoluModule)
class IkoluModuleAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'color_display', 'is_core', 'base_price_monthly', 'is_active', 'order')
    list_editable = ('order', 'is_active')
    list_filter = ('is_core', 'is_active')
    search_fields = ('name', 'code', 'description')
    ordering = ('order', 'name')
    
    fieldsets = (
        (None, {
            'fields': ('code', 'name', 'description')
        }),
        ('Presentación', {
            'fields': ('icon', 'color_code', 'order')
        }),
        ('Configuración de Acceso', {
            'fields': ('api_permission_codename', 'frontend_route')
        }),
        ('Comercial', {
            'fields': ('base_price_monthly', 'is_core')
        }),
        ('Estado', {
            'fields': ('is_active',)
        }),
    )
    
    def color_display(self, obj):
        return format_html(
            '<span style="background-color: {}; padding: 2px 10px; border-radius: 3px; color: white;">&nbsp;</span>',
            obj.color_code
        )
    color_display.short_description = "Color"


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'duration_months', 'discount_percent', 'is_active', 'order')
    list_editable = ('order', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name', 'code')
    ordering = ('order', 'duration_months')


@admin.register(PointModuleAccess)
class PointModuleAccessAdmin(admin.ModelAdmin):
    list_display = ('point', 'module', 'plan', 'start_date', 'end_date', 'is_active', 'is_valid_display')
    list_filter = ('module', 'plan', 'is_active')
    search_fields = ('point__title', 'module__name')
    date_hierarchy = 'start_date'
    raw_id_fields = ('point', 'granted_by')
    
    fieldsets = (
        (None, {
            'fields': ('point', 'module', 'plan')
        }),
        ('Vigencia', {
            'fields': ('start_date', 'end_date', 'is_active')
        }),
        ('Metadata', {
            'fields': ('granted_by', 'notes'),
            'classes': ('collapse',)
        }),
    )
    
    def is_valid_display(self, obj):
        if obj.is_valid():
            return format_html('<span style="color: green;">✓ Vigente</span>')
        return format_html('<span style="color: red;">✗ Vencido</span>')
    is_valid_display.short_description = "Estado"
