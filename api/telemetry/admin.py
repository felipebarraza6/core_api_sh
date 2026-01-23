"""
Admin principal del módulo Telemetry - Sistema Dinámico V3.

Este módulo registra todos los admins de telemetría incluyendo:
- Modelos de configuración dinámica (admin_configuration.py)
- Modelos de compliance regulatorio (admin_compliance.py)
- Modelos de V3 logic (admin_v3.py)
- Modelos de constantes (admin_constants.py)
- Modelos de datos granulares (admin_granular.py)
- Puntos de captación y telemetría (integrados aquí)
"""

from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse

# Importar modelos principales
from .models.catchment_points import CatchmentPoint
from .models.telemetry import TelemetryRecord
from .models.configuration import PointConfigurationValue
from .models.management_super import SystemConfiguration

# Importar inlines de otros módulos
from .admin_configuration import PointConfigurationValueInline

# Importar inline de compliance
from api.compliance.models import PointComplianceConfig
from api.compliance.admin import PointComplianceConfigInline

# =============================================================================
# INLINE PARA COMPLIANCE CONFIG (USANDO EL DE COMPLIANCE APP)
# =============================================================================
# Se usa directamente de api.compliance.admin para mantener coherencia


# =============================================================================
# INLINE PARA CATCHMENT POINT
# =============================================================================

class TelemetryRecordInline(admin.TabularInline):
    """Inline para registros de telemetría en CatchmentPoint."""
    model = TelemetryRecord
    extra = 0
    fields = ('timestamp', 'flow', 'nivel', 'total', 'is_error', 'is_partial')
    readonly_fields = fields
    can_delete = False
    max_num = 10
    ordering = ('-timestamp',)

    def has_add_permission(self, request, obj=None):
        return False


# =============================================================================
# ADMIN PARA CATCHMENT POINT
# =============================================================================

@admin.register(CatchmentPoint)
class CatchmentPointAdmin(admin.ModelAdmin):
    """
    Admin para Puntos de Captación con sistema dinámico.

    Incluye inlines para:
    - Configuración de valores (PointConfigurationValueInline)
    - Configuración de compliance (ComplianceConfigInline)
    - Registros de telemetría recientes (TelemetryRecordInline)
    """

    list_display = (
        'point_code',
        'title',
        'project',
        'client_link',
        'configuration_scheme_display',
        'compliance_providers_display',
        'telemetry_status',
        'is_active'
    )

    list_filter = (
        'is_active',
        'project',
        'configuration_scheme',
        'frequency',
    )

    search_fields = (
        'point_code',
        'title',
        'owner_user__username',
    )

    readonly_fields = (
        'created',
        'modified',
        'last_telemetry_display',
        'configuration_preview',
    )

    autocomplete_fields = ('owner_user', 'project', 'configuration_scheme', 'frequency')

    inlines = [
        PointConfigurationValueInline,
        PointComplianceConfigInline,
        TelemetryRecordInline,
    ]

    fieldsets = (
        ('Identificación', {
            'fields': ('point_code', 'title', 'project', 'owner_user', 'is_active')
        }),
        ('Configuración Dinámica', {
            'fields': ('configuration_scheme', 'configuration_preview', 'frequency'),
            'description': 'Sistema dinámico de configuración V3'
        }),
        ('Ubicación', {
            'fields': ('lat', 'lon'),
        }),
        ('Telemetría', {
            'fields': ('last_telemetry_display',),
            'description': 'Últimos registros de telemetría'
        }),
        ('Auditoría', {
            'fields': ('created', 'modified'),
            'classes': ('collapse',)
        }),
    )

    def client_link(self, obj):
        """Link al cliente."""
        if obj.client:
            url = reverse('admin:core_user_change', args=[obj.client.id])
            return format_html('<a href="{}">{}</a>', url, obj.client.get_full_name())
        return '-'
    client_link.short_description = 'Cliente'

    def configuration_scheme_display(self, obj):
        """Mostrar esquema de configuración con badge."""
        if obj.configuration_scheme:
            color = '#28a745' if obj.configuration_scheme.is_active else '#dc3545'
            return format_html(
                '<span style="background: {}; color: white; padding: 3px 8px; '
                'border-radius: 3px; font-size: 11px;">{}</span>',
                color,
                obj.configuration_scheme.name
            )
        return format_html('<span style="color: #999;">Sin esquema</span>')
    configuration_scheme_display.short_description = 'Esquema Config'

    def compliance_providers_display(self, obj):
        """Mostrar proveedores de compliance activos."""
        from api.compliance.models import PointComplianceConfig

        configs = PointComplianceConfig.objects.filter(
            point=obj,
            is_active=True
        ).select_related('provider')

        if not configs.exists():
            return format_html('<span style="color: #999;">-</span>')

        badges = []
        for config in configs:
            color = '#17a2b8' if config.send_compliance else '#6c757d'
            icon = '📤' if config.send_compliance else '⏸️'
            badges.append(
                f'<span style="background: {color}; color: white; padding: 2px 6px; '
                f'border-radius: 3px; font-size: 10px; margin-right: 4px;">'
                f'{icon} {config.provider.display_name}</span>'
            )

        return format_html(''.join(badges))
    compliance_providers_display.short_description = 'Compliance'

    def telemetry_status(self, obj):
        """Estado de telemetría."""
        latest = TelemetryRecord.objects.filter(point=obj).order_by('-timestamp').first()

        if not latest:
            return format_html(
                '<span style="color: #999; font-style: italic;">Sin registros</span>'
            )

        # Calcular tiempo desde último registro
        from django.utils import timezone
        from datetime import timedelta

        now = timezone.now()
        delta = now - latest.timestamp

        if delta < timedelta(hours=1):
            color = '#28a745'
            status = '✓ Reciente'
        elif delta < timedelta(days=1):
            color = '#ffc107'
            status = '⚠ Hace horas'
        else:
            color = '#dc3545'
            status = '✗ Antiguo'

        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            status
        )
    telemetry_status.short_description = 'Estado Telemetría'

    def last_telemetry_display(self, obj):
        """Mostrar últimos registros de telemetría."""
        records = TelemetryRecord.objects.filter(
            point=obj
        ).order_by('-timestamp')[:5]

        if not records:
            return format_html('<p style="color: #999;">No hay registros de telemetría</p>')

        html = '<table style="width: 100%; border-collapse: collapse;">'
        html += '<tr style="background: #f8f9fa;">'
        html += '<th style="padding: 8px; text-align: left;">Fecha</th>'
        html += '<th style="padding: 8px; text-align: right;">Caudal (L/s)</th>'
        html += '<th style="padding: 8px; text-align: right;">Nivel (m)</th>'
        html += '<th style="padding: 8px; text-align: right;">Total (m³)</th>'
        html += '<th style="padding: 8px; text-align: center;">Estado</th>'
        html += '</tr>'

        for record in records:
            status_icon = '❌' if record.is_error else ('⚠️' if record.is_partial else '✅')

            html += '<tr style="border-bottom: 1px solid #dee2e6;">'
            html += f'<td style="padding: 8px;">{record.timestamp.strftime("%Y-%m-%d %H:%M")}</td>'
            html += f'<td style="padding: 8px; text-align: right;">{record.flow or "-"}</td>'
            html += f'<td style="padding: 8px; text-align: right;">{record.nivel or "-"}</td>'
            html += f'<td style="padding: 8px; text-align: right;">{record.total or "-"}</td>'
            html += f'<td style="padding: 8px; text-align: center;">{status_icon}</td>'
            html += '</tr>'

        html += '</table>'
        return format_html(html)
    last_telemetry_display.short_description = 'Últimos Registros'

    def configuration_preview(self, obj):
        """Vista previa de la configuración del punto."""
        if not obj.configuration_scheme:
            return format_html('<p style="color: #999;">No hay esquema de configuración asignado</p>')

        values = PointConfigurationValue.objects.filter(
            point=obj
        ).select_related('field')

        if not values.exists():
            return format_html('<p style="color: #ffc107;">⚠️ Esquema asignado pero sin valores configurados</p>')

        html = '<table style="width: 100%; border-collapse: collapse;">'
        html += '<tr style="background: #f8f9fa;">'
        html += '<th style="padding: 8px; text-align: left;">Campo</th>'
        html += '<th style="padding: 8px; text-align: left;">Valor</th>'
        html += '<th style="padding: 8px; text-align: left;">Unidad</th>'
        html += '</tr>'

        for value in values:
            html += '<tr style="border-bottom: 1px solid #dee2e6;">'
            html += f'<td style="padding: 8px;"><strong>{value.field.name}</strong></td>'
            html += f'<td style="padding: 8px;"><code>{value.value}</code></td>'
            html += f'<td style="padding: 8px;">{value.field.unit or "-"}</td>'
            html += '</tr>'

        html += '</table>'
        return format_html(html)
    configuration_preview.short_description = 'Configuración'


# =============================================================================
# ADMIN PARA TELEMETRY RECORD
# =============================================================================
# NOTA: TelemetryRecord ya está registrado en api/core/admin.py
# Este código está comentado para evitar duplicación.

@admin.register(TelemetryRecord)
class TelemetryRecordAdmin(admin.ModelAdmin):
    """Admin para registros de telemetría."""

    list_display = (
        'id',
        'point_link',
        'timestamp',
        'flow_display',
        'nivel_display',
        'total_display',
        'status_display',
        'compliance_status',
        'get_device_id',
    )

    list_filter = (
        'is_error',
        'is_partial',
        'timestamp',
        'point__owner_user',
    )

    search_fields = (
        'point__title',
        'point__point_code',
        # 'device_id', # No existe columna device_id
    )

    readonly_fields = (
        'timestamp',
        'date_time_last_logger',
        'variable_details',
        'flow', 'nivel', 'water_table', 'total', 'pulses',
        'get_device_id',
    )

    autocomplete_fields = ('point',)

    date_hierarchy = 'timestamp'

    fieldsets = (
        ('Punto', {
            'fields': ('point',)
        }),
        ('Timestamp', {
            'fields': ('timestamp', 'date_time_last_logger')
        }),
        ('Datos', {
            'fields': ('flow', 'nivel', 'water_table', 'total', 'pulses')
        }),
        ('Estado', {
            'fields': ('is_error', 'is_partial', 'get_device_id')
        }),
        ('Metadatos', {
            'fields': ('variable_details',),
            'classes': ('collapse',)
        }),
    )

    def get_device_id(self, obj):
        """Obtener ID del dispositivo desde metadata o data."""
        return obj.metadata.get('device_id') or obj.data.get('device_id') or '-'
    get_device_id.short_description = 'Device ID'

    def point_link(self, obj):
        """Link al punto."""
        url = reverse('admin:telemetry_catchmentpoint_change', args=[obj.point.id])
        return format_html('<a href="{}">{}</a>', url, obj.point.title)
    point_link.short_description = 'Punto'

    def flow_display(self, obj):
        """Mostrar caudal formateado."""
        if obj.flow is not None:
            return f"{obj.flow:.2f} L/s"
        return '-'
    flow_display.short_description = 'Caudal'

    def nivel_display(self, obj):
        """Mostrar nivel formateado."""
        if obj.nivel is not None:
            return f"{obj.nivel:.2f} m"
        return '-'
    nivel_display.short_description = 'Nivel'

    def total_display(self, obj):
        """Mostrar total formateado."""
        if obj.total is not None:
            return f"{obj.total:.2f} m³"
        return '-'
    total_display.short_description = 'Total'

    def status_display(self, obj):
        """Estado del registro."""
        if obj.is_error:
            return format_html(
                '<span style="background: #dc3545; color: white; padding: 3px 8px; '
                'border-radius: 3px; font-size: 11px;">❌ ERROR</span>'
            )
        elif obj.is_partial:
            return format_html(
                '<span style="background: #ffc107; color: black; padding: 3px 8px; '
                'border-radius: 3px; font-size: 11px;">⚠️ PARCIAL</span>'
            )
        else:
            return format_html(
                '<span style="background: #28a745; color: white; padding: 3px 8px; '
                'border-radius: 3px; font-size: 11px;">✅ OK</span>'
            )
    status_display.short_description = 'Estado'

    def compliance_status(self, obj):
        """Estado de envío a compliance."""
        from api.compliance.models import ComplianceSubmissionLog

        submissions = ComplianceSubmissionLog.objects.filter(
            telemetry_record=obj
        ).select_related('compliance_config__provider')

        if not submissions.exists():
            return format_html('<span style="color: #999;">-</span>')

        badges = []
        for submission in submissions:
            if submission.submission_status == 'SUCCESS':
                color = '#28a745'
                icon = '✅'
            elif submission.submission_status == 'FAILED':
                color = '#dc3545'
                icon = '❌'
            elif submission.submission_status == 'PENDING':
                color = '#ffc107'
                icon = '⏳'
            else:
                color = '#6c757d'
                icon = '⏸️'

            badges.append(
                f'<span style="background: {color}; color: white; padding: 2px 6px; '
                f'border-radius: 3px; font-size: 10px; margin-right: 4px;">'
                f'{icon} {submission.compliance_config.provider.name.upper()}</span>'
            )

        return format_html(''.join(badges))
    compliance_status.short_description = 'Compliance'


@admin.register(SystemConfiguration)
class SystemConfigurationAdmin(admin.ModelAdmin):
    """Admin para configuración global del sistema."""
    list_display = ('key', 'category', 'is_encrypted', 'modified')
    list_filter = ('category', 'is_encrypted')
    search_fields = ('key', 'description')
    readonly_fields = ('created', 'modified')


# =============================================================================
# IMPORTAR OTROS ADMINS PARA REGISTRO
# =============================================================================
from . import admin_v3
from . import admin_constants

