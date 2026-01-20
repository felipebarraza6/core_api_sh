"""
Admin mejorado para sistema de Compliance dinámico.

Este admin proporciona una interfaz completa para gestionar:
- Proveedores de compliance (DGA, SMA, etc.)
- Configuraciones de compliance por punto
- Registros manuales de compliance
"""

from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.db.models import Count, Q, Avg
from django.utils import timezone

from api.telemetry.providers.compliance_models import (
    ComplianceProvider,
    PointComplianceConfig,
    ManualComplianceRecord
)


@admin.register(ComplianceProvider)
class ComplianceProviderAdmin(admin.ModelAdmin):
    """
    Admin para proveedores de compliance.

    Permite configurar DGA, SMA, y otros proveedores de forma dinámica.
    """

    list_display = [
        'display_name_colored',
        'name',
        'service_type',
        'submission_frequency',
        'auth_method',
        'points_count',
        'active_points_count',
        'is_active_badge',
        'actions_column',
    ]

    list_filter = [
        'service_type',
        'is_active',
        'submission_frequency',
        'auth_method',
    ]

    search_fields = [
        'name',
        'display_name',
        'description',
        'base_url',
    ]

    readonly_fields = [
        'created_at',
        'updated_at',
        'statistics_summary',
    ]

    fieldsets = (
        ('📋 Información Básica', {
            'fields': (
                'name',
                'display_name',
                'description',
                'service_type',
                'is_active',
            )
        }),
        ('🔗 Conexión', {
            'fields': (
                'base_url',
                'auth_endpoint',
                'data_endpoint_template',
                'timeout_seconds',
            ),
            'description': (
                'Configuración de conexión al API del proveedor. '
                'El data_endpoint_template puede usar variables como {uf_id}, {process_id}, etc.'
            )
        }),
        ('🔐 Autenticación', {
            'fields': (
                'auth_method',
                'auth_config',
            ),
            'classes': ('collapse',),
            'description': (
                'Configuración de autenticación. El formato del auth_config depende '
                'del auth_method seleccionado. Ver ejemplos en el help_text del campo.'
            )
        }),
        ('📦 Payload y Respuesta', {
            'fields': (
                'payload_template',
                'response_mapping',
            ),
            'classes': ('collapse',),
            'description': (
                'Templates para construir el payload y parsear la respuesta. '
                'Usar variables como {config.codigo_obra} y {record.data.flow}.'
            )
        }),
        ('⚙️ Configuración del Proveedor', {
            'fields': (
                'required_fields',
                'data_variables',
                'validation_rules',
            ),
            'classes': ('collapse',),
            'description': 'Definición de campos requeridos y variables de datos.'
        }),
        ('⏰ Frecuencia y Reintentos', {
            'fields': (
                'submission_frequency',
                'max_retries',
                'retry_delay_seconds',
            )
        }),
        ('📚 Documentación', {
            'fields': (
                'documentation_url',
            ),
            'classes': ('collapse',)
        }),
        ('📊 Estadísticas', {
            'fields': (
                'statistics_summary',
            ),
            'classes': ('collapse',)
        }),
        ('🕐 Auditoría', {
            'fields': (
                'created_at',
                'updated_at',
            ),
            'classes': ('collapse',)
        }),
    )

    def display_name_colored(self, obj):
        """Display name con color según servicio."""
        colors = {
            'water_rights': '#2196F3',  # Azul
            'environmental': '#4CAF50',  # Verde
            'energy': '#FF9800',  # Naranja
            'custom': '#9C27B0',  # Púrpura
        }
        color = colors.get(obj.service_type, '#757575')

        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.display_name
        )
    display_name_colored.short_description = 'Nombre'
    display_name_colored.admin_order_field = 'display_name'

    def points_count(self, obj):
        """Contar puntos usando este proveedor."""
        count = PointComplianceConfig.objects.filter(provider=obj).count()
        return format_html('<strong>{}</strong>', count)
    points_count.short_description = 'Puntos Total'

    def active_points_count(self, obj):
        """Contar puntos activos."""
        count = PointComplianceConfig.objects.filter(
            provider=obj,
            is_active=True,
            send_compliance=True
        ).count()

        color = '#4CAF50' if count > 0 else '#757575'

        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            count
        )
    active_points_count.short_description = 'Activos'

    def is_active_badge(self, obj):
        """Badge de estado activo."""
        if obj.is_active:
            return format_html(
                '<span style="background-color: #4CAF50; color: white; '
                'padding: 3px 10px; border-radius: 3px;">✓ Activo</span>'
            )
        else:
            return format_html(
                '<span style="background-color: #F44336; color: white; '
                'padding: 3px 10px; border-radius: 3px;">✗ Inactivo</span>'
            )
    is_active_badge.short_description = 'Estado'

    def actions_column(self, obj):
        """Columna de acciones."""
        change_url = reverse('admin:compliance_provider_change', args=[obj.pk])
        configs_url = reverse('admin:point_compliance_config_changelist') + f'?provider__id__exact={obj.pk}'

        return format_html(
            '<a class="button" href="{}">Editar</a> '
            '<a class="button" href="{}">Ver Configuraciones</a>',
            change_url,
            configs_url
        )
    actions_column.short_description = 'Acciones'

    def statistics_summary(self, obj):
        """Resumen de estadísticas del proveedor."""
        if not obj.pk:
            return "Guardar primero para ver estadísticas"

        configs = PointComplianceConfig.objects.filter(provider=obj)

        total = configs.count()
        active = configs.filter(is_active=True, send_compliance=True).count()

        total_submissions = sum(c.total_submissions for c in configs)
        successful = sum(c.successful_submissions for c in configs)

        success_rate = (successful / total_submissions * 100) if total_submissions > 0 else 0

        with_errors = configs.filter(error_count__gt=0).count()

        html = f"""
        <div style="background: #f5f5f5; padding: 15px; border-radius: 5px;">
            <h3 style="margin-top: 0;">📊 Estadísticas del Proveedor</h3>

            <table style="width: 100%;">
                <tr>
                    <td><strong>Total Configuraciones:</strong></td>
                    <td>{total}</td>
                </tr>
                <tr>
                    <td><strong>Activas y Enviando:</strong></td>
                    <td style="color: #4CAF50; font-weight: bold;">{active}</td>
                </tr>
                <tr>
                    <td><strong>Total Envíos:</strong></td>
                    <td>{total_submissions}</td>
                </tr>
                <tr>
                    <td><strong>Envíos Exitosos:</strong></td>
                    <td>{successful}</td>
                </tr>
                <tr>
                    <td><strong>Tasa de Éxito:</strong></td>
                    <td style="color: {'#4CAF50' if success_rate >= 90 else '#FF9800' if success_rate >= 70 else '#F44336'}; font-weight: bold;">
                        {success_rate:.1f}%
                    </td>
                </tr>
                <tr>
                    <td><strong>Configuraciones con Errores:</strong></td>
                    <td style="color: {'#F44336' if with_errors > 0 else '#4CAF50'};">
                        {with_errors}
                    </td>
                </tr>
            </table>
        </div>
        """

        return format_html(html)
    statistics_summary.short_description = 'Resumen Estadísticas'


class ComplianceConfigInline(admin.TabularInline):
    """Inline para agregar configuraciones de compliance en CatchmentPoint."""

    model = PointComplianceConfig
    extra = 0
    can_delete = True

    fields = [
        'provider',
        'data_source',
        'send_compliance',
        'is_active',
        'success_rate_display',
        'last_submission',
        'error_count',
    ]

    readonly_fields = [
        'success_rate_display',
        'last_submission',
        'error_count',
    ]

    def success_rate_display(self, obj):
        """Mostrar tasa de éxito."""
        if not obj.pk or obj.total_submissions == 0:
            return "N/A"

        rate = (obj.successful_submissions / obj.total_submissions) * 100
        color = '#4CAF50' if rate >= 90 else '#FF9800' if rate >= 70 else '#F44336'

        return format_html(
            '<span style="color: {}; font-weight: bold;">{:.1f}%</span>',
            color,
            rate
        )
    success_rate_display.short_description = 'Tasa Éxito'


@admin.register(PointComplianceConfig)
class PointComplianceConfigAdmin(admin.ModelAdmin):
    """
    Admin para configuraciones de compliance por punto.

    Aquí se configuran los datos específicos de cada punto para cada proveedor.
    """

    list_display = [
        'point_link',
        'provider_link',
        'data_source',
        'send_compliance_badge',
        'is_active_badge',
        'success_rate_colored',
        'last_submission_relative',
        'error_count_colored',
        'actions_column',
    ]

    list_filter = [
        'provider',
        'data_source',
        'send_compliance',
        'is_active',
        ('point__client', admin.RelatedOnlyFieldListFilter),
        ('last_submission', admin.DateFieldListFilter),
    ]

    search_fields = [
        'point__title',
        'point__point_code',
        'provider__name',
        'provider__display_name',
    ]

    readonly_fields = [
        'created_at',
        'updated_at',
        'last_submission',
        'last_success',
        'last_error',
        'error_count',
        'total_submissions',
        'successful_submissions',
        'success_rate_display',
        'submission_history',
    ]

    autocomplete_fields = ['point']

    fieldsets = (
        ('🔗 Relaciones', {
            'fields': (
                'point',
                'provider',
            )
        }),
        ('⚙️ Configuración del Punto', {
            'fields': (
                'config_data',
            ),
            'description': (
                'Datos específicos de este punto según los required_fields del proveedor. '
                'Ver documentación del proveedor para campos disponibles.'
            )
        }),
        ('🔐 Credenciales (Opcional)', {
            'fields': (
                'credentials_override',
            ),
            'classes': ('collapse',),
            'description': (
                'Si este punto usa credenciales diferentes a las del proveedor, '
                'especifícalas aquí. Si está vacío, usa las credenciales del proveedor.'
            )
        }),
        ('📡 Origen de Datos', {
            'fields': (
                'data_source',
                'is_active',
                'send_compliance',
            )
        }),
        ('📊 Estadísticas', {
            'fields': (
                'success_rate_display',
                'total_submissions',
                'successful_submissions',
                'error_count',
                'last_submission',
                'last_success',
                'last_error',
            ),
            'classes': ('collapse',)
        }),
        ('📜 Historial', {
            'fields': (
                'submission_history',
            ),
            'classes': ('collapse',)
        }),
        ('🕐 Auditoría', {
            'fields': (
                'created_at',
                'updated_at',
            ),
            'classes': ('collapse',)
        }),
    )

    def point_link(self, obj):
        """Link al punto."""
        url = reverse('admin:telemetry_catchmentpoint_change', args=[obj.point.pk])
        return format_html('<a href="{}">{}</a>', url, obj.point.title)
    point_link.short_description = 'Punto'
    point_link.admin_order_field = 'point__title'

    def provider_link(self, obj):
        """Link al proveedor."""
        url = reverse('admin:compliance_provider_change', args=[obj.provider.pk])
        return format_html('<a href="{}">{}</a>', url, obj.provider.display_name)
    provider_link.short_description = 'Proveedor'
    provider_link.admin_order_field = 'provider__display_name'

    def send_compliance_badge(self, obj):
        """Badge de envío."""
        if obj.send_compliance:
            return format_html(
                '<span style="background-color: #4CAF50; color: white; '
                'padding: 3px 8px; border-radius: 3px;">✓ Enviando</span>'
            )
        else:
            return format_html(
                '<span style="background-color: #757575; color: white; '
                'padding: 3px 8px; border-radius: 3px;">✗ Pausado</span>'
            )
    send_compliance_badge.short_description = 'Envío'

    def is_active_badge(self, obj):
        """Badge de activo."""
        if obj.is_active:
            return format_html('<span style="color: #4CAF50;">✓</span>')
        else:
            return format_html('<span style="color: #F44336;">✗</span>')
    is_active_badge.short_description = 'Activo'

    def success_rate_colored(self, obj):
        """Tasa de éxito con color."""
        if obj.total_submissions == 0:
            return format_html('<span style="color: #757575;">N/A</span>')

        rate = (obj.successful_submissions / obj.total_submissions) * 100
        color = '#4CAF50' if rate >= 90 else '#FF9800' if rate >= 70 else '#F44336'

        return format_html(
            '<span style="color: {}; font-weight: bold;">{:.1f}%</span>',
            color,
            rate
        )
    success_rate_colored.short_description = 'Tasa Éxito'

    def last_submission_relative(self, obj):
        """Última sumisión (relativa)."""
        if not obj.last_submission:
            return format_html('<span style="color: #757575;">Nunca</span>')

        from django.utils.timesince import timesince
        time_str = timesince(obj.last_submission)

        # Color según antigüedad
        delta = timezone.now() - obj.last_submission
        if delta.total_seconds() < 3600:  # < 1 hora
            color = '#4CAF50'
        elif delta.total_seconds() < 86400:  # < 1 día
            color = '#FF9800'
        else:
            color = '#F44336'

        return format_html(
            '<span style="color: {};">{} ago</span>',
            color,
            time_str
        )
    last_submission_relative.short_description = 'Último Envío'

    def error_count_colored(self, obj):
        """Count de errores con color."""
        if obj.error_count == 0:
            return format_html('<span style="color: #4CAF50;">0</span>')
        else:
            return format_html(
                '<span style="color: #F44336; font-weight: bold;">{}</span>',
                obj.error_count
            )
    error_count_colored.short_description = 'Errores'

    def actions_column(self, obj):
        """Columna de acciones."""
        change_url = reverse('admin:point_compliance_config_change', args=[obj.pk])

        return format_html(
            '<a class="button" href="{}">Editar</a>',
            change_url
        )
    actions_column.short_description = 'Acciones'

    def success_rate_display(self, obj):
        """Display de tasa de éxito."""
        return self.success_rate_colored(obj)
    success_rate_display.short_description = 'Tasa de Éxito'

    def submission_history(self, obj):
        """Historial de envíos."""
        if not obj.pk:
            return "Guardar primero para ver historial"

        # Aquí podrías mostrar un gráfico o tabla con historial
        # Por ahora, solo un resumen

        html = f"""
        <div style="background: #f5f5f5; padding: 15px; border-radius: 5px;">
            <h3 style="margin-top: 0;">📜 Historial de Envíos</h3>

            <table style="width: 100%;">
                <tr>
                    <td><strong>Total Envíos:</strong></td>
                    <td>{obj.total_submissions}</td>
                </tr>
                <tr>
                    <td><strong>Exitosos:</strong></td>
                    <td style="color: #4CAF50; font-weight: bold;">{obj.successful_submissions}</td>
                </tr>
                <tr>
                    <td><strong>Fallidos:</strong></td>
                    <td style="color: #F44336; font-weight: bold;">
                        {obj.total_submissions - obj.successful_submissions}
                    </td>
                </tr>
                <tr>
                    <td><strong>Último Exitoso:</strong></td>
                    <td>{obj.last_success or 'Nunca'}</td>
                </tr>
                <tr>
                    <td><strong>Último Envío:</strong></td>
                    <td>{obj.last_submission or 'Nunca'}</td>
                </tr>
            </table>

            {f'<div style="margin-top: 10px; padding: 10px; background: #ffebee; border-left: 4px solid #f44336;"><strong>Último Error:</strong><br>{obj.last_error}</div>' if obj.last_error else ''}
        </div>
        """

        return format_html(html)
    submission_history.short_description = 'Historial'


@admin.register(ManualComplianceRecord)
class ManualComplianceRecordAdmin(admin.ModelAdmin):
    """Admin para registros manuales de compliance."""

    list_display = [
        'config_link',
        'measurement_timestamp',
        'status_badge',
        'voucher_display',
        'created_by',
        'submitted_at',
    ]

    list_filter = [
        'status',
        'config__provider',
        ('measurement_timestamp', admin.DateFieldListFilter),
        ('submitted_at', admin.DateFieldListFilter),
    ]

    search_fields = [
        'config__point__title',
        'config__point__point_code',
        'voucher',
    ]

    readonly_fields = [
        'created_at',
        'updated_at',
        'submitted_at',
        'response_data',
    ]

    fieldsets = (
        ('🔗 Configuración', {
            'fields': ('config',)
        }),
        ('📊 Datos de Medición', {
            'fields': (
                'measurement_timestamp',
                'data',
            )
        }),
        ('📤 Estado de Envío', {
            'fields': (
                'status',
                'voucher',
                'response_data',
                'error_message',
                'submitted_at',
            )
        }),
        ('👤 Auditoría', {
            'fields': (
                'created_by',
                'created_at',
                'updated_at',
            ),
            'classes': ('collapse',)
        }),
    )

    def config_link(self, obj):
        """Link a la configuración."""
        url = reverse('admin:point_compliance_config_change', args=[obj.config.pk])
        return format_html(
            '<a href="{}">{} → {}</a>',
            url,
            obj.config.point.point_code,
            obj.config.provider.display_name
        )
    config_link.short_description = 'Configuración'

    def status_badge(self, obj):
        """Badge de estado."""
        colors = {
            'pending': '#757575',
            'queued': '#2196F3',
            'sent': '#4CAF50',
            'error': '#F44336',
            'cancelled': '#FF9800',
        }
        color = colors.get(obj.status, '#757575')

        return format_html(
            '<span style="background-color: {}; color: white; '
            'padding: 3px 10px; border-radius: 3px;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_badge.short_description = 'Estado'

    def voucher_display(self, obj):
        """Display de voucher."""
        if obj.voucher:
            return format_html(
                '<code style="background: #f5f5f5; padding: 2px 6px; '
                'border-radius: 3px;">{}</code>',
                obj.voucher
            )
        return '-'
    voucher_display.short_description = 'Comprobante'
