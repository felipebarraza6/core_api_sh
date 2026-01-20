"""
Admin interfaces for MQTT provider configuration.

Provides Django admin interfaces for configuring MQTT providers,
parsing rules, and point-specific MQTT settings.
"""

import json
import logging
from django.contrib import admin
from django.contrib import messages
from django.http import JsonResponse
from django.urls import path
from django.shortcuts import render
from django.utils.html import format_html
from django.core.exceptions import ValidationError

from .models import TelemetryProvider
from .mqtt_models import MQTTProviderConfig, PayloadParsingRule, CatchmentPointMQTT
from .mqtt_parser import MQTTPayloadParser

logger = logging.getLogger(__name__)


class MQTTProviderConfigInline(admin.StackedInline):
    """
    Inline admin for MQTT provider configuration.
    """
    model = MQTTProviderConfig
    can_delete = False
    verbose_name = "Configuración MQTT"
    verbose_name_plural = "Configuración MQTT"
    fk_name = 'provider'

    fieldsets = (
        ('Conexión al Broker', {
            'fields': ('broker_host', 'broker_port', 'use_tls'),
            'classes': ('collapse',),
        }),
        ('Autenticación', {
            'fields': ('username', 'password'),
            'classes': ('collapse',),
        }),
        ('Topics', {
            'fields': ('subscribe_topic_template', 'publish_topic_template'),
        }),
        ('Configuración Avanzada', {
            'fields': ('default_qos', 'retain_messages', 'keep_alive', 'reconnect_delay'),
            'classes': ('collapse',),
        }),
    )


class PayloadParsingRuleInline(admin.TabularInline):
    """
    Inline admin for payload parsing rules.
    """
    model = PayloadParsingRule
    extra = 0
    verbose_name = "Regla de Parsing"
    verbose_name_plural = "Reglas de Parsing"

    fields = ('name', 'rule_type', 'parsing_method', 'priority', 'is_active')
    readonly_fields = ('get_condition_display', 'get_mappings_count')

    def get_condition_display(self, obj):
        """Display human-readable condition."""
        if obj.rule_type == 'topic_match':
            return f"Topic: {obj.rule_condition.get('pattern', 'N/A')}"
        elif obj.rule_type == 'payload_field':
            field = obj.rule_condition.get('field', 'N/A')
            value = obj.rule_condition.get('value', 'N/A')
            return f"Campo '{field}' = '{value}'"
        elif obj.rule_type == 'device_type':
            return f"Dispositivo: {obj.rule_condition.get('type', 'N/A')}"
        return "Siempre"
    get_condition_display.short_description = "Condición"

    def get_mappings_count(self, obj):
        """Display number of field mappings."""
        return len(obj.field_mappings)
    get_mappings_count.short_description = "Mapeos"


@admin.register(MQTTProviderConfig)
class MQTTProviderConfigAdmin(admin.ModelAdmin):
    """
    Admin for MQTT provider configuration.
    """
    list_display = ('provider', 'broker_host', 'broker_port', 'use_tls', 'get_rules_count')
    list_filter = ('use_tls', 'provider__is_active')
    search_fields = ('provider__name', 'provider__display_name', 'broker_host')

    fieldsets = (
        ('Proveedor', {
            'fields': ('provider',),
        }),
        ('Conexión al Broker', {
            'fields': ('broker_host', 'broker_port', 'use_tls'),
        }),
        ('Autenticación', {
            'fields': ('username', 'password'),
            'classes': ('collapse',),
        }),
        ('Templates de Topics', {
            'fields': ('subscribe_topic_template', 'publish_topic_template'),
            'description': '''
                Variables disponibles:
                <ul>
                    <li><code>{provider}</code> - Nombre del proveedor</li>
                    <li><code>{device_id}</code> - ID del dispositivo</li>
                    <li><code>{point_code}</code> - Código del punto</li>
                </ul>
                Ejemplo: <code>{provider}/{device_id}/telemetry</code>
            ''',
        }),
        ('Configuración QoS', {
            'fields': ('default_qos', 'retain_messages'),
            'classes': ('collapse',),
        }),
        ('Configuración de Conexión', {
            'fields': ('keep_alive', 'reconnect_delay'),
            'classes': ('collapse',),
        }),
    )

    readonly_fields = ('get_rules_count',)

    def get_rules_count(self, obj):
        """Display number of parsing rules."""
        return obj.provider.parsing_rules.count()
    get_rules_count.short_description = "Reglas de Parsing"

    def get_urls(self):
        """Add custom URLs for testing connection."""
        urls = super().get_urls()
        custom_urls = [
            path(
                '<path:object_id>/test-connection/',
                self.admin_site.admin_view(self.test_connection_view),
                name='mqtt_provider_config_test_connection'
            ),
        ]
        return custom_urls + urls

    def test_connection_view(self, request, object_id):
        """View for testing MQTT connection."""
        try:
            config = self.get_object(request, object_id)
            from .mqtt_handler import DynamicMQTTHandler

            handler = DynamicMQTTHandler(config.provider)
            result = handler.test_connection()

            if result['success']:
                messages.success(request, f"Conexión exitosa: {result['message']}")
            else:
                messages.error(request, f"Error de conexión: {result['error']}")

        except Exception as e:
            messages.error(request, f"Error al probar conexión: {str(e)}")

        return self.response_post_save_change(request, config)


@admin.register(PayloadParsingRule)
class PayloadParsingRuleAdmin(admin.ModelAdmin):
    """
    Admin for payload parsing rules.
    """
    list_display = ('name', 'provider', 'rule_type', 'parsing_method', 'priority', 'is_active')
    list_filter = ('rule_type', 'parsing_method', 'is_active', 'provider__name')
    search_fields = ('name', 'provider__name', 'provider__display_name')
    ordering = ('-priority', 'provider__name', 'name')

    fieldsets = (
        ('Información General', {
            'fields': ('provider', 'name', 'description'),
        }),
        ('Condición de Aplicación', {
            'fields': ('rule_type', 'rule_condition'),
            'description': '''
                <strong>Condiciones disponibles:</strong>
                <ul>
                    <li><strong>topic_match:</strong> {"pattern": "novus/+/data"}</li>
                    <li><strong>payload_field:</strong> {"field": "device_type", "value": "nxperience"}</li>
                    <li><strong>device_type:</strong> {"type": "plc_siemens"}</li>
                    <li><strong>always:</strong> {} (vacío)</li>
                </ul>
            ''',
        }),
        ('Método de Parsing', {
            'fields': ('parsing_method',),
            'description': '''
                <strong>Métodos disponibles:</strong>
                <ul>
                    <li><strong>template:</strong> Variables simples en templates</li>
                    <li><strong>jsonpath:</strong> Consultas JMESPath avanzadas</li>
                    <li><strong>python:</strong> Código Python personalizado</li>
                    <li><strong>regex:</strong> Expresiones regulares</li>
                </ul>
            ''',
        }),
        ('Configuración de Mapeo', {
            'fields': ('field_mappings',),
            'description': '''
                <strong>Formatos por método:</strong>
                <div style="background: #f8f9fa; padding: 10px; border-left: 4px solid #007bff;">
                    <strong>template:</strong> {"field": "{payload.data.value}"}<br>
                    <strong>jsonpath:</strong> {"field": {"source": "$.data.value", "type": "jsonpath"}}<br>
                    <strong>python:</strong> {"field": "float(payload['data']['value'])"}<br>
                    <strong>regex:</strong> {"field": {"pattern": "value:(\\d+)", "group": 1}}
                </div>
            ''',
        }),
        ('Transformaciones', {
            'fields': ('transformations',),
            'classes': ('collapse',),
            'description': '''
                Lista de transformaciones: [
                    {"field": "timestamp", "type": "unix_to_datetime"},
                    {"field": "flow", "type": "unit_conversion", "from": "m3/h", "to": "L/s"}
                ]
            ''',
        }),
        ('Validación', {
            'fields': ('validation_rules',),
            'classes': ('collapse',),
            'description': '''
                Reglas de validación: {
                    "flow": {"min": 0, "max": 1000},
                    "timestamp": {"not_null": true}
                }
            ''',
        }),
        ('Configuración', {
            'fields': ('priority', 'is_active'),
        }),
    )

    def get_urls(self):
        """Add custom URLs for testing parsing rules."""
        urls = super().get_urls()
        custom_urls = [
            path(
                '<path:object_id>/test-parsing/',
                self.admin_site.admin_view(self.test_parsing_view),
                name='payload_parsing_rule_test_parsing'
            ),
            path(
                'test-parsing-preview/',
                self.admin_site.admin_view(self.test_parsing_preview),
                name='payload_parsing_rule_test_parsing_preview'
            ),
        ]
        return custom_urls + urls

    def test_parsing_view(self, request, object_id):
        """View for testing parsing rule."""
        return render(request, 'admin/mqtt_test_parsing.html', {
            'rule_id': object_id,
            'title': 'Probar Regla de Parsing'
        })

    def test_parsing_preview(self, request):
        """AJAX endpoint for testing parsing rules."""
        if request.method != 'POST':
            return JsonResponse({'error': 'Method not allowed'})

        try:
            rule_id = request.POST.get('rule_id')
            test_payload = request.POST.get('payload')
            test_topic = request.POST.get('topic', '')
            test_device_id = request.POST.get('device_id', '')

            if not rule_id or not test_payload:
                return JsonResponse({'error': 'Missing required parameters'})

            rule = PayloadParsingRule.objects.get(id=rule_id)
            parser = MQTTPayloadParser(rule.provider.mqtt_config)

            # Parse payload
            parsed_data = parser.parse(
                topic=test_topic,
                payload=test_payload.encode('utf-8'),
                device_id=test_device_id
            )

            # Validate
            validation_errors = rule.validate_parsed_data(parsed_data)

            return JsonResponse({
                'success': True,
                'parsed_data': parsed_data,
                'validation_errors': validation_errors,
                'has_errors': len(validation_errors) > 0
            })

        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            })

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        """Customize form fields."""
        field = super().formfield_for_dbfield(db_field, request, **kwargs)

        if db_field.name in ['rule_condition', 'field_mappings', 'transformations', 'validation_rules']:
            # Make JSON fields taller
            field.widget.attrs['rows'] = 5
            field.widget.attrs['cols'] = 80

        return field


@admin.register(CatchmentPointMQTT)
class CatchmentPointMQTTAdmin(admin.ModelAdmin):
    """
    Admin for point-specific MQTT configuration.
    """
    list_display = ('point', 'provider', 'get_device_id', 'is_active', 'last_seen')
    list_filter = ('is_active', 'provider__name', 'last_seen')
    search_fields = ('point__title', 'point__point_code', 'custom_device_id', 'provider__name')

    fieldsets = (
        ('Punto y Proveedor', {
            'fields': ('point', 'provider'),
        }),
        ('Configuración de Dispositivo', {
            'fields': ('custom_device_id', 'device_config'),
            'description': '''
                Configuración específica del dispositivo físico.
                Ejemplo: {"calibration_factor": 1.23, "sensor_offset": 0.5}
            ''',
        }),
        ('Topics Personalizados', {
            'fields': ('custom_topics',),
            'classes': ('collapse',),
            'description': '''
                Override de topics para este punto específico.
                Ejemplo: {"subscribe": "custom/{device_id}/data"}
            ''',
        }),
        ('Estado', {
            'fields': ('is_active', 'last_seen'),
        }),
    )

    readonly_fields = ('last_seen',)

    def get_device_id(self, obj):
        """Display effective device ID."""
        return obj.get_effective_device_id()
    get_device_id.short_description = "Device ID"

    def get_queryset(self, request):
        """Optimize queryset."""
        return super().get_queryset(request).select_related('point', 'provider')


# Monkey patch para agregar MQTT config al TelemetryProvider admin
def get_telemetry_provider_admin():
    """Get or create TelemetryProvider admin with MQTT inline."""
    from django.apps import apps
    from .admin import TelemetryProviderAdmin

    # Add MQTT inline if not already present
    if not any(isinstance(inline, MQTTProviderConfigInline)
               for inline in TelemetryProviderAdmin.inlines):
        TelemetryProviderAdmin.inlines = list(TelemetryProviderAdmin.inlines) + [MQTTProviderConfigInline]

    return TelemetryProviderAdmin

# Ensure the inline is added
get_telemetry_provider_admin()