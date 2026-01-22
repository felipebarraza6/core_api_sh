"""
Infrastructure Admin - Gestión de Dispositivos IoT
"""

from django.contrib import admin
from django.utils.html import format_html
from .models import Manufacturer, DeviceModel, Device


@admin.register(Manufacturer)
class ManufacturerAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'integration_status', 'models_count')
    list_filter = ('integration_status',)
    search_fields = ('name', 'code', 'website')
    ordering = ('name',)

    fieldsets = (
        ('Información General', {
            'fields': ('name', 'code', 'description')
        }),
        ('Contacto', {
            'fields': ('website', 'contact_email', 'contact_phone')
        }),
        ('Estado de Integración', {
            'fields': ('integration_status',)
        }),
    )
    
    def models_count(self, obj):
        count = obj.models.count()
        return format_html('<strong>{}</strong> modelos', count)
    models_count.short_description = "Modelos"


class DeviceInline(admin.TabularInline):
    model = Device
    extra = 0
    fields = ('device_id', 'name', 'status', 'last_seen')
    readonly_fields = ('device_id', 'last_seen')


@admin.register(DeviceModel)
class DeviceModelAdmin(admin.ModelAdmin):
    list_display = ('model_name', 'manufacturer', 'model_code', 'devices_count')
    list_filter = ('manufacturer',)
    search_fields = ('model_name', 'model_code', 'description')
    ordering = ('manufacturer', 'model_name')
    inlines = [DeviceInline]

    fieldsets = (
        (None, {
            'fields': ('manufacturer', 'model_name', 'model_code', 'description')
        }),
    )
    
    def devices_count(self, obj):
        count = obj.devices.count()
        if count == 0:
            return format_html('<span style="color: gray;">0 dispositivos</span>')
        return format_html('<strong>{}</strong> dispositivos', count)
    devices_count.short_description = "Dispositivos"


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'device_id',
        'device_model',
        'status_display',
        'last_seen'
    )
    list_filter = ('status', 'device_model__manufacturer', 'device_model')
    search_fields = ('name', 'device_id', 'imei', 'token')
    ordering = ('-last_seen',)

    fieldsets = (
        ('Identificación', {
            'fields': ('device_id', 'name', 'device_model')
        }),
        ('Autenticación', {
            'fields': ('use_internal_mqtt', 'token', 'imei'),
            'description': 'Si usa MQTT interno, el token se genera automáticamente. Si usa proveedor externo, ingrese el token manualmente.'
        }),
        ('Estado', {
            'fields': ('status', 'last_seen')
        }),
    )

    readonly_fields = ('device_id', 'last_seen')

    def status_display(self, obj):
        colors = {
            'ONLINE': 'green',
            'OFFLINE': 'gray',
            'ERROR': 'red',
            'MAINTENANCE': 'orange',
        }
        color = colors.get(obj.status, 'gray')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_display.short_description = "Estado"



