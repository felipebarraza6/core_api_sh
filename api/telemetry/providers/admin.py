from django.contrib import admin
from django.utils.html import format_html
from django.contrib import messages
from django.urls import path, reverse
from django.shortcuts import redirect
import json

from .models import TelemetryProvider, CatchmentPointProvider
from .forms import TelemetryProviderForm
# Import Manager/Handler for testing connection
from .handlers import DynamicAPIHandler

class CatchmentPointProviderInline(admin.TabularInline):
    model = CatchmentPointProvider
    extra = 0
    fields = ('point', 'point_code', 'is_active')
    autocomplete_fields = ('point',)
    show_change_link = True

@admin.register(TelemetryProvider)
class TelemetryProviderAdmin(admin.ModelAdmin):
    form = TelemetryProviderForm
    list_display = ('name', 'display_name', 'provider_type_badge', 'base_url', 'auth_method_badge', 'is_active', 'test_connection_button')
    list_filter = ('provider_type', 'is_active', 'auth_method')
    search_fields = ('name', 'display_name', 'base_url')
    readonly_fields = ('created', 'modified')
    actions = ['duplicate_provider', 'test_auth_connection']
    inlines = [CatchmentPointProviderInline]

    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'display_name', 'is_active')
        }),
        ('Connection Details', {
            'fields': ('provider_type', 'base_url', 'timeout_seconds')
        }),
        ('Authentication', {
            'fields': ('auth_method', 'auth_config'),
            'classes': ('collapse',),
            'description': 'Configuration for authentication. See documentation for required keys per method.'
        }),
        ('Templates & Parsing', {
            'fields': ('endpoint_template', 'request_template', 'response_mapping'),
            'classes': ('collapse',),
            'description': 'Templates for constructing requests and parsing responses (JSON).'
        }),
        ('Metadata', {
            'fields': ('created', 'modified'),
            'classes': ('collapse',)
        }),
    )

    def provider_type_badge(self, obj):
        color = 'green' if obj.provider_type == 'http' else 'blue'
        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, obj.get_provider_type_display())
    provider_type_badge.short_description = 'Type'

    def auth_method_badge(self, obj):
        return format_html('<span style="background-color: #eee; padding: 2px 5px; border-radius: 3px;">{}</span>', obj.get_auth_method_display())
    auth_method_badge.short_description = 'Auth'

    def test_connection_button(self, obj):
        return format_html(
            '<a class="button" href="{}">Test Auth</a>',
            reverse('admin:test_provider_connection', args=[obj.pk])
        )
    test_connection_button.short_description = 'Actions'
    test_connection_button.allow_tags = True

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                '<int:pk>/test-connection/',
                self.admin_site.admin_view(self.test_connection_view),
                name='test_provider_connection',
            ),
        ]
        return custom_urls + urls

    def test_connection_view(self, request, pk):
        provider = self.get_object(request, pk)
        try:
            # Instantiate handler and attempt auth resolution (which triggers login if needed)
            handler = DynamicAPIHandler(provider)
            # Try to resolve token -> This forces login for Bearer, or prepares headers for others
            token = handler._resolve_auth_token(None, None)
            
            # If no exception, success!
            # For non-login auth (API Key), checking token might be trivial, 
            # so we might want to do a lightweight "ping" if possible, but we don't know the URL.
            # At minimum, this validates schema and Login credentials.
            
            messages.success(request, f"✅ Connection Test Passed for {provider.name}. Auth Token resolved successfully.")
        except Exception as e:
            messages.error(request, f"❌ Connection Failed: {str(e)}")
        
        return redirect('admin:providers_telemetryprovider_change', pk)

    @admin.action(description="Duplicate selected providers")
    def duplicate_provider(self, request, queryset):
        for provider in queryset:
            provider.pk = None
            provider.name = f"{provider.name}_copy"
            provider.display_name = f"{provider.display_name} (Copy)"
            provider.save()
        messages.success(request, f"Successfully duplicated {queryset.count()} providers.")

    @admin.action(description="Test Authentication (Bulk)")
    def test_auth_connection(self, request, queryset):
        success_count = 0
        for provider in queryset:
            try:
                handler = DynamicAPIHandler(provider)
                handler._resolve_auth_token(None, None)
                success_count += 1
            except Exception as e:
                messages.error(request, f"Failed {provider.name}: {e}")
        
        if success_count > 0:
            messages.success(request, f"{success_count} providers authenticated successfully.")



@admin.register(CatchmentPointProvider)
class CatchmentPointProviderAdmin(admin.ModelAdmin):
    list_display = ('point_title', 'provider_name', 'point_code', 'is_active', 'created')
    list_filter = ('provider__name', 'is_active')
    search_fields = ('point__title', 'point_code', 'provider__name')
    autocomplete_fields = ('point', 'provider')
    
    fieldsets = (
        ('Configuración de Conexión', {
            'fields': ('point', 'provider', 'is_active'),
            'description': 'Selecciona el punto y el proveedor a conectar.'
        }),
        ('Credenciales del Dispositivo', {
            'fields': ('point_code',),
            'description': '⚠️ IMPORTANTE: Aquí va el TOKEN o ID del dispositivo proporcionado por el proveedor de telemetría (ej: device_key, API token, etc.)'
        }),
        ('Configuración Adicional (Opcional)', {
            'fields': ('config_override',),
            'classes': ('collapse',),
            'description': 'Sobrescribir configuración del proveedor con JSON personalizado.'
        }),
    )
    
    def point_title(self, obj):
        return obj.point.title
    point_title.short_description = 'Punto de Captación'
    point_title.admin_order_field = 'point__title'

    def provider_name(self, obj):
        return obj.provider.display_name
    provider_name.short_description = 'Proveedor'
    provider_name.admin_order_field = 'provider__display_name'
