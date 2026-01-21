"""
Infrastructure Admin - Gestión de Dispositivos IoT
"""

from django.contrib import admin
from django.utils.html import format_html
from .models import Manufacturer, DeviceModel, Device, Connection


@admin.register(Manufacturer)
class ManufacturerAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'integration_status', 'is_active', 'models_count')
    list_filter = ('integration_status', 'is_active', 'mqtt_use_tls')
    search_fields = ('name', 'code', 'website')
    ordering = ('name',)
    
    fieldsets = (
        ('Información General', {
            'fields': ('name', 'code', 'description', 'is_active')
        }),
        ('Contacto', {
            'fields': ('website', 'contact_email', 'contact_phone')
        }),
        ('Configuración MQTT', {
            'fields': (
                'mqtt_broker_host',
                'mqtt_broker_port',
                'mqtt_username',
                'mqtt_password',
                'mqtt_use_tls'
            ),
            'classes': ('collapse',)
        }),
        ('Estado', {
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
    fields = ('device_id', 'name', 'status', 'last_seen', 'battery_level')
    readonly_fields = ('last_seen',)


@admin.register(DeviceModel)
class DeviceModelAdmin(admin.ModelAdmin):
    list_display = ('model_name', 'manufacturer', 'model_code', 'devices_count', 'is_active')
    list_filter = ('manufacturer', 'is_active')
    search_fields = ('model_name', 'model_code', 'description')
    ordering = ('manufacturer', 'model_name')
    inlines = [DeviceInline]
    
    fieldsets = (
        (None, {
            'fields': ('manufacturer', 'model_name', 'model_code', 'description')
        }),
        ('Estado', {
            'fields': ('is_active',)
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
        'catchment_point',
        'status_display',
        'battery_display',
        'last_seen'
    )
    list_filter = ('status', 'device_model__manufacturer', 'device_model')
    search_fields = ('name', 'device_id', 'catchment_point__title')
    raw_id_fields = ('catchment_point',)
    ordering = ('-last_seen',)
    
    fieldsets = (
        ('Identificación', {
            'fields': ('device_id', 'name', 'device_model')
        }),
        ('Ubicación', {
            'fields': ('catchment_point',)
        }),
        ('Estado', {
            'fields': ('status', 'last_seen', 'battery_level')
        }),
    )
    
    readonly_fields = ('last_seen',)
    
    def status_display(self, obj):
        colors = {
            'ONLINE': 'green',
            'OFFLINE': 'gray',
            'ERROR': 'red',
            'MAINTENANCE': 'orange',
            'BATTERY_LOW': 'orange'
        }
        color = colors.get(obj.status, 'gray')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_display.short_description = "Estado"
    
    def battery_display(self, obj):
        if obj.battery_level is None:
            return '-'
        
        level = float(obj.battery_level)
        if level > 50:
            color = 'green'
        elif level > 20:
            color = 'orange'
        else:
            color = 'red'
        
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}%</span>',
            color,
            level
        )
    battery_display.short_description = "Batería"


@admin.register(Connection)
class ConnectionAdmin(admin.ModelAdmin):
    list_display = (
        'connection_name',
        'manufacturer',
        'broker_host',
        'broker_port',
        'status_display',
        'is_active'
    )
    list_filter = ('status', 'is_active', 'manufacturer')
    search_fields = ('connection_name', 'broker_host', 'client_id')
    ordering = ('manufacturer', 'connection_name')
    
    fieldsets = (
        ('Información General', {
            'fields': ('manufacturer', 'connection_name', 'is_active')
        }),
        ('Configuración MQTT', {
            'fields': (
                'broker_host',
                'broker_port',
                'username',
                'password',
                'client_id'
            )
        }),
        ('Estado', {
            'fields': ('status',),
            'classes': ('collapse',)
        }),
    )
    
    def status_display(self, obj):
        colors = {
            'CONNECTED': 'green',
            'CONNECTING': 'blue',
            'DISCONNECTED': 'gray',
            'ERROR': 'red'
        }
        color = colors.get(obj.status, 'gray')
        return format_html(
            '<span style="color: {}; font-weight: bold;">● {}</span>',
            color,
            obj.get_status_display()
        )
    status_display.short_description = "Estado"
