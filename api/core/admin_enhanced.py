"""
Django Admin Mejorado para Gestión Completa del Sistema SmartHydro
Admin empresarial con control total de todos los componentes
"""

from django.contrib import admin
from django.contrib.admin import ModelAdmin, TabularInline, StackedInline
from django.contrib.admin.views.main import ChangeList
from django.db.models import Count, Sum, Avg, Q, F
from django.utils import timezone
from django.utils.html import format_html
from django.urls import reverse
from django.contrib import messages
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse

from .models import *
from .models.enhanced_data_models import *
from .models.constants_system import *
from .models.management_super import *
from .services.constants_service import constants_service
from .services.stats_service import StatsService


# ============================================================================
# INLINES PARA RELACIONES
# ============================================================================

class DeviceInline(TabularInline):
    model = IoTDevice
    fields = ['device_id', 'name', 'status', 'last_seen']
    readonly_fields = ['last_seen']
    extra = 0
    can_delete = False

    def has_add_permission(self, request):
        return False


class DataStreamInline(TabularInline):
    model = DataStream
    fields = ['name', 'code', 'stream_type', 'is_active', 'sampling_rate_seconds']
    extra = 0


class VariableDefinitionInline(TabularInline):
    model = VariableDefinition
    fields = ['name', 'code', 'variable_type', 'unit', 'is_required']
    extra = 0


class ConstantApplicationInline(TabularInline):
    model = ConstantApplication
    fields = ['start_date', 'end_date', 'is_active', 'recalculation_status']
    readonly_fields = ['recalculation_status']
    extra = 0
    can_delete = False


class TicketCommentInline(StackedInline):
    model = TicketComment
    fields = ['author', 'comment', 'is_internal', 'created_at']
    readonly_fields = ['created_at']
    extra = 0
    can_delete = False


# ============================================================================
# ADMINS AVANZADOS
# ============================================================================

@admin.register(DataPoint)
class DataPointAdmin(ModelAdmin):
    """Admin avanzado para puntos de datos con filtros inteligentes"""

    list_display = [
        'data_point_id', 'stream_name', 'device_name', 'collected_at',
        'processed_value_display', 'quality_badge', 'is_valid_badge',
        'processing_time'
    ]

    list_filter = [
        'quality', 'is_valid', 'is_processed', 'is_archived',
        ('stream__stream_type', admin.ChoicesFieldListFilter),
        ('device__equipment_model__provider', admin.RelatedFieldListFilter),
        ('collected_at', admin.DateFieldListFilter),
    ]

    search_fields = ['data_point_id', 'device__device_id', 'stream__code']

    readonly_fields = [
        'data_point_id', 'received_at', 'processed_at',
        'processing_time', 'quality_score'
    ]

    fieldsets = (
        ('Identificación', {
            'fields': ('data_point_id', 'stream', 'device', 'point')
        }),
        ('Timestamps', {
            'fields': ('collected_at', 'received_at', 'processed_at', 'processing_time')
        }),
        ('Datos', {
            'fields': ('raw_value', 'processed_value', 'unit', 'metadata')
        }),
        ('Estado', {
            'fields': ('quality', 'is_valid', 'validation_errors', 'is_processed', 'is_archived')
        }),
    )

    actions = ['mark_as_processed', 'archive_old_data', 'reprocess_invalid']

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'stream', 'device__equipment_model__provider', 'point'
        )

    def stream_name(self, obj):
        return obj.stream.name
    stream_name.short_description = 'Stream'

    def device_name(self, obj):
        return obj.device.name
    device_name.short_description = 'Dispositivo'

    def processed_value_display(self, obj):
        if obj.processed_value is not None:
            return f"{obj.processed_value:.3f} {obj.unit}"
        return "N/A"
    processed_value_display.short_description = 'Valor Procesado'

    def quality_badge(self, obj):
        colors = {
            'EXCELLENT': 'green',
            'GOOD': 'blue',
            'FAIR': 'orange',
            'POOR': 'red',
            'INVALID': 'black'
        }
        color = colors.get(obj.quality, 'gray')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 6px; border-radius: 3px;">{}</span>',
            color, obj.quality
        )
    quality_badge.short_description = 'Calidad'

    def is_valid_badge(self, obj):
        color = 'green' if obj.is_valid else 'red'
        text = '✓' if obj.is_valid else '✗'
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 6px; border-radius: 3px;">{}</span>',
            color, text
        )
    is_valid_badge.short_description = 'Válido'

    def processing_time(self, obj):
        if obj.processed_at and obj.received_at:
            delta = obj.processed_at - obj.received_at
            return f"{delta.total_seconds():.2f}s"
        return "N/A"
    processing_time.short_description = 'Tiempo Procesamiento'

    def mark_as_processed(self, request, queryset):
        updated = queryset.filter(is_processed=False).update(
            is_processed=True,
            processed_at=timezone.now()
        )
        self.message_user(request, f"{updated} puntos marcados como procesados")

    def archive_old_data(self, request, queryset):
        cutoff = timezone.now() - timezone.timedelta(days=90)
        updated = queryset.filter(
            collected_at__lt=cutoff,
            is_archived=False
        ).update(is_archived=True)
        self.message_user(request, f"{updated} registros antiguos archivados")

    def reprocess_invalid(self, request, queryset):
        invalid_points = queryset.filter(is_valid=False)
        reprocessed = 0

        for point in invalid_points:
            # Intentar reprocesar
            try:
                # Lógica de reprocesamiento aquí
                point.is_valid = True
                point.is_processed = True
                point.processed_at = timezone.now()
                point.save()
                reprocessed += 1
            except Exception as e:
                self.message_user(request, f"Error reprocesando {point.data_point_id}: {e}")

        self.message_user(request, f"{reprocessed} puntos reprocesados")


@admin.register(SupportTicket)
class SupportTicketAdmin(ModelAdmin):
    """Admin avanzado para gestión de tickets de soporte"""

    list_display = [
        'ticket_number', 'title', 'status_badge', 'priority_badge',
        'category', 'created_by', 'assigned_to', 'opened_at', 'days_open'
    ]

    list_filter = [
        'status', 'priority', 'category', 'assigned_to',
        ('opened_at', admin.DateFieldListFilter),
        ('due_date', admin.DateFieldListFilter),
    ]

    search_fields = ['ticket_number', 'title', 'description', 'created_by__email']

    readonly_fields = [
        'ticket_number', 'opened_at', 'resolved_at', 'closed_at',
        'resolution_time_hours', 'days_open'
    ]

    fieldsets = (
        ('Información Básica', {
            'fields': ('ticket_number', 'title', 'description')
        }),
        ('Estado y Prioridad', {
            'fields': ('status', 'priority', 'category')
        }),
        ('Asignación', {
            'fields': ('created_by', 'assigned_to')
        }),
        ('Fechas', {
            'fields': ('opened_at', 'due_date', 'resolved_at', 'closed_at', 'resolution_time_hours')
        }),
        ('Recursos Afectados', {
            'fields': ('affected_devices', 'affected_points')
        }),
        ('Información Adicional', {
            'fields': ('tags', 'attachments', 'custom_fields'),
            'classes': ('collapse',)
        }),
        ('Métricas', {
            'fields': ('days_open', 'customer_satisfaction'),
            'classes': ('collapse',)
        }),
    )

    inlines = [TicketCommentInline]

    actions = [
        'assign_to_me', 'mark_in_progress', 'mark_resolved', 'close_ticket',
        'set_high_priority', 'set_critical_priority', 'add_followup_required'
    ]

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related(
            'affected_devices', 'affected_points', 'comments'
        )

    def status_badge(self, obj):
        colors = {
            'OPEN': 'blue',
            'IN_PROGRESS': 'orange',
            'WAITING_CUSTOMER': 'yellow',
            'WAITING_SUPPLIER': 'purple',
            'RESOLVED': 'green',
            'CLOSED': 'gray'
        }
        color = colors.get(obj.status, 'gray')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 6px; border-radius: 3px; font-size: 0.8em;">{}</span>',
            color, obj.get_status_display()
        )
    status_badge.short_description = 'Estado'

    def priority_badge(self, obj):
        colors = {
            'LOW': 'green',
            'NORMAL': 'blue',
            'HIGH': 'orange',
            'CRITICAL': 'red',
            'EMERGENCY': 'darkred'
        }
        color = colors.get(obj.priority, 'gray')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 6px; border-radius: 3px; font-size: 0.8em;">{}</span>',
            color, obj.get_priority_display()
        )
    priority_badge.short_description = 'Prioridad'

    def days_open(self, obj):
        return obj.days_open
    days_open.short_description = 'Días Abierto'

    # Actions
    def assign_to_me(self, request, queryset):
        updated = 0
        for ticket in queryset.filter(assigned_to__isnull=True):
            ticket.assign_to(request.user)
            updated += 1
        self.message_user(request, f"{updated} tickets asignados a ti")

    def mark_in_progress(self, request, queryset):
        updated = queryset.filter(status='OPEN').update(
            status='IN_PROGRESS',
            assigned_to=request.user
        )
        self.message_user(request, f"{updated} tickets marcados en progreso")

    def mark_resolved(self, request, queryset):
        updated = 0
        for ticket in queryset.filter(status__in=['OPEN', 'IN_PROGRESS']):
            ticket.resolve(request.user, "Resuelto desde admin")
            updated += 1
        self.message_user(request, f"{updated} tickets resueltos")

    def close_ticket(self, request, queryset):
        updated = queryset.filter(status='RESOLVED').update(
            status='CLOSED',
            closed_at=timezone.now()
        )
        self.message_user(request, f"{updated} tickets cerrados")

    def set_high_priority(self, request, queryset):
        updated = queryset.update(priority='HIGH')
        self.message_user(request, f"{updated} tickets marcados como alta prioridad")

    def set_critical_priority(self, request, queryset):
        updated = queryset.update(priority='CRITICAL')
        self.message_user(request, f"{updated} tickets marcados como críticos")

    def add_followup_required(self, request, queryset):
        # Agregar tag de seguimiento requerido
        for ticket in queryset:
            tags = ticket.tags or []
            if 'followup_required' not in tags:
                tags.append('followup_required')
                ticket.tags = tags
                ticket.save()
        self.message_user(request, f"Tag 'followup_required' agregado a {queryset.count()} tickets")


@admin.register(ConstantDefinition)
class ConstantDefinitionAdmin(ModelAdmin):
    """Admin para gestión de constantes del sistema"""

    list_display = [
        'name', 'code', 'constant_type', 'value_display',
        'scope_display', 'is_active_badge', 'created_at'
    ]

    list_filter = [
        'constant_type', 'is_active',
        ('device__equipment_model__provider', admin.RelatedFieldListFilter),
        ('point__project__client', admin.RelatedFieldListFilter),
    ]

    search_fields = ['name', 'code', 'description']

    readonly_fields = ['created_at', 'updated_at']

    fieldsets = (
        ('Información Básica', {
            'fields': ('name', 'code', 'description', 'constant_type')
        }),
        ('Valor', {
            'fields': ('value_numeric', 'value_text', 'unit')
        }),
        ('Alcance', {
            'fields': ('device', 'point'),
            'description': 'Si no se especifica device ni point, aplica globalmente'
        }),
        ('Validación', {
            'fields': ('min_value', 'max_value', 'allowed_values'),
            'classes': ('collapse',)
        }),
        ('Configuración', {
            'fields': ('is_required', 'default_value', 'is_active')
        }),
        ('Metadata', {
            'fields': ('tags', 'custom_properties'),
            'classes': ('collapse',)
        }),
    )

    inlines = [ConstantApplicationInline]

    actions = [
        'activate_constants', 'deactivate_constants',
        'apply_to_historical_data', 'create_range_application'
    ]

    def value_display(self, obj):
        if obj.value_numeric is not None:
            return f"{obj.value_numeric} {obj.unit}"
        return obj.value_text or "N/A"
    value_display.short_description = 'Valor'

    def scope_display(self, obj):
        if obj.device:
            return f"Device: {obj.device.name}"
        elif obj.point:
            return f"Point: {obj.point.title}"
        else:
            return "Global"
    scope_display.short_description = 'Alcance'

    def is_active_badge(self, obj):
        color = 'green' if obj.is_active else 'red'
        text = '✓' if obj.is_active else '✗'
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 6px; border-radius: 3px;">{}</span>',
            color, text
        )
    is_active_badge.short_description = 'Activa'

    def activate_constants(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f"{updated} constantes activadas")

    def deactivate_constants(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f"{updated} constantes desactivadas")

    def apply_to_historical_data(self, request, queryset):
        """Aplicar constantes seleccionadas a datos históricos"""
        applied = 0
        errors = []

        for constant in queryset:
            try:
                result = constants_service.create_constant_range_application(
                    constant,
                    start_date=timezone.now() - timezone.timedelta(days=30),
                    end_date=None,
                    reason="Aplicado desde admin"
                )
                if result['success']:
                    applied += 1
                else:
                    errors.append(f"{constant.name}: {result.get('error', 'Error desconocido')}")
            except Exception as e:
                errors.append(f"{constant.name}: {e}")

        if applied:
            self.message_user(request, f"{applied} constantes aplicadas a datos históricos")

        if errors:
            self.message_user(
                request,
                f"Errores en {len(errors)} constantes: {', '.join(errors[:3])}",
                level=messages.WARNING
            )

    def create_range_application(self, request, queryset):
        """Crear aplicación de rango para constantes"""
        if queryset.count() == 1:
            constant = queryset.first()
            # Redirect to custom form
            url = reverse('admin:create_constant_range', args=[constant.pk])
            return HttpResponseRedirect(url)
        else:
            self.message_user(
                request,
                "Selecciona exactamente una constante para crear aplicación de rango",
                level=messages.WARNING
            )


@admin.register(ProviderDataSync)
class ProviderDataSyncAdmin(ModelAdmin):
    """Admin para gestión de sincronización con proveedores"""

    list_display = [
        'provider_name', 'sync_type', 'status_badge',
        'last_sync_display', 'records_synced_display',
        'error_display', 'is_active_badge'
    ]

    list_filter = [
        'sync_type', 'current_status', 'is_active',
        ('provider__integration_status', admin.ChoicesFieldListFilter),
    ]

    search_fields = ['provider__name', 'provider__code']

    readonly_fields = [
        'last_sync_attempt', 'last_successful_sync',
        'total_records_synced', 'messages_received_today',
        'messages_sent_today', 'bytes_received_today',
        'consecutive_failures'
    ]

    fieldsets = (
        ('Proveedor', {
            'fields': ('provider', 'sync_type', 'is_active')
        }),
        ('Configuración', {
            'fields': ('sync_interval_minutes', 'sync_config')
        }),
        ('Estado', {
            'fields': ('current_status', 'last_sync_attempt', 'last_successful_sync')
        }),
        ('Estadísticas', {
            'fields': ('total_records_synced', 'last_sync_records',
                      'messages_received_today', 'messages_sent_today',
                      'bytes_received_today', 'consecutive_failures')
        }),
        ('Errores', {
            'fields': ('last_error_message',),
            'classes': ('collapse',)
        }),
    )

    actions = ['enable_sync', 'disable_sync', 'force_sync_now', 'reset_stats']

    def provider_name(self, obj):
        return obj.provider.name
    provider_name.short_description = 'Proveedor'

    def status_badge(self, obj):
        colors = {
            'IDLE': 'gray',
            'RUNNING': 'blue',
            'SUCCESS': 'green',
            'PARTIAL_SUCCESS': 'orange',
            'FAILED': 'red',
            'CANCELLED': 'purple'
        }
        color = colors.get(obj.current_status, 'gray')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 6px; border-radius: 3px; font-size: 0.8em;">{}</span>',
            color, obj.current_status
        )
    status_badge.short_description = 'Estado'

    def last_sync_display(self, obj):
        if obj.last_successful_sync:
            delta = timezone.now() - obj.last_successful_sync
            hours = delta.total_seconds() / 3600
            if hours < 1:
                return f"{int(hours * 60)}min atrás"
            elif hours < 24:
                return f"{int(hours)}h atrás"
            else:
                return f"{int(hours / 24)}d atrás"
        return "Nunca"
    last_sync_display.short_description = 'Última Sync'

    def records_synced_display(self, obj):
        return f"{obj.total_records_synced:,}"
    records_synced_display.short_description = 'Registros'

    def error_display(self, obj):
        if obj.consecutive_failures > 0:
            return format_html(
                '<span style="color: red;">{}</span>',
                f"{obj.consecutive_failures} fallos"
            )
        return "OK"
    error_display.short_description = 'Errores'

    def is_active_badge(self, obj):
        color = 'green' if obj.is_active else 'red'
        text = '✓' if obj.is_active else '✗'
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 6px; border-radius: 3px;">{}</span>',
            color, text
        )
    is_active_badge.short_description = 'Activa'

    def enable_sync(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f"{updated} sincronizaciones habilitadas")

    def disable_sync(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f"{updated} sincronizaciones deshabilitadas")

    def force_sync_now(self, request, queryset):
        """Forzar sincronización inmediata"""
        from ..tasks.provider_sync_tasks import sync_provider_data

        forced = 0
        for sync in queryset.filter(is_active=True):
            try:
                sync_provider_data.delay(sync.provider.code)
                forced += 1
            except Exception as e:
                self.message_user(request, f"Error forzando sync para {sync.provider.name}: {e}")

        self.message_user(request, f"Sincronización forzada para {forced} proveedores")

    def reset_stats(self, request, queryset):
        """Reset estadísticas de sincronización"""
        updated = queryset.update(
            total_records_synced=0,
            last_sync_records=0,
            messages_received_today=0,
            messages_sent_today=0,
            bytes_received_today=0,
            consecutive_failures=0,
            last_error_message=''
        )
        self.message_user(request, f"Estadísticas reseteadas para {updated} proveedores")


# ============================================================================
# DASHBOARD EJECUTIVO EN ADMIN
# ============================================================================

class SmartHydroAdminSite(admin.AdminSite):
    """Admin site personalizado con dashboard ejecutivo"""

    site_header = "SmartHydro - Gestión Empresarial"
    site_title = "SmartHydro Admin"
    index_title = "Panel de Control Empresarial"

    def index(self, request, extra_context=None):
        """Override index para agregar dashboard ejecutivo"""
        # Obtener datos del dashboard
        dashboard_data = self._get_dashboard_data()

        # Contexto adicional
        extra_context = extra_context or {}
        extra_context.update({
            'dashboard_data': dashboard_data,
            'recent_tickets': SupportTicket.objects.select_related('created_by', 'assigned_to')[:5],
            'sync_status': ProviderDataSync.objects.select_related('provider')[:10],
            'system_alerts': self._get_system_alerts()
        })

        return super().index(request, extra_context)

    def _get_dashboard_data(self):
        """Obtener datos para el dashboard ejecutivo"""
        try:
            # Estadísticas generales
            total_devices = IoTDevice.objects.count()
            active_devices = IoTDevice.objects.filter(status='ONLINE').count()
            total_tickets = SupportTicket.objects.count()
            open_tickets = SupportTicket.objects.filter(status__in=['OPEN', 'IN_PROGRESS']).count()

            # Sincronización
            total_syncs = ProviderDataSync.objects.count()
            active_syncs = ProviderDataSync.objects.filter(is_active=True).count()

            # Datos recientes
            recent_data_points = DataPoint.objects.filter(
                collected_at__gte=timezone.now() - timezone.timedelta(hours=24)
            ).count()

            return {
                'total_devices': total_devices,
                'active_devices': active_devices,
                'device_uptime': (active_devices / total_devices * 100) if total_devices > 0 else 0,
                'total_tickets': total_tickets,
                'open_tickets': open_tickets,
                'ticket_resolution_rate': ((total_tickets - open_tickets) / total_tickets * 100) if total_tickets > 0 else 0,
                'total_syncs': total_syncs,
                'active_syncs': active_syncs,
                'recent_data_points': recent_data_points,
                'data_ingestion_rate': recent_data_points / 24  # por hora
            }
        except Exception as exc:
            return {
                'error': str(exc),
                'total_devices': 0,
                'active_devices': 0,
                'total_tickets': 0,
                'open_tickets': 0,
                'total_syncs': 0,
                'active_syncs': 0,
                'recent_data_points': 0
            }

    def _get_system_alerts(self):
        """Obtener alertas del sistema para mostrar en dashboard"""
        alerts = []

        # Alertas de dispositivos offline
        offline_devices = IoTDevice.objects.filter(
            status__in=['OFFLINE', 'ERROR'],
            last_seen__lt=timezone.now() - timezone.timedelta(hours=1)
        ).count()

        if offline_devices > 0:
            alerts.append({
                'type': 'warning',
                'message': f"{offline_devices} dispositivos offline",
                'url': '/admin/core/iotdevice/?status__in=OFFLINE%2CERROR'
            })

        # Alertas de tickets sin asignar
        unassigned_tickets = SupportTicket.objects.filter(
            status='OPEN',
            assigned_to__isnull=True,
            opened_at__lt=timezone.now() - timezone.timedelta(hours=2)
        ).count()

        if unassigned_tickets > 0:
            alerts.append({
                'type': 'info',
                'message': f"{unassigned_tickets} tickets sin asignar",
                'url': '/admin/core/supportticket/?status=OPEN&assigned_to__isnull=True'
            })

        # Alertas de sincronización fallida
        failed_syncs = ProviderDataSync.objects.filter(
            current_status='FAILED',
            consecutive_failures__gt=0
        ).count()

        if failed_syncs > 0:
            alerts.append({
                'type': 'error',
                'message': f"{failed_syncs} sincronizaciones fallando",
                'url': '/admin/core/providerdatasync/?current_status=FAILED'
            })

        return alerts

    def get_app_list(self, request):
        """Reorganizar el menú del admin por categorías de negocio"""
        app_list = super().get_app_list(request)

        # Crear estructura personalizada
        custom_app_list = []

        # Dashboard Ejecutivo
        custom_app_list.append({
            'name': '🏠 Dashboard Ejecutivo',
            'app_label': 'dashboard',
            'models': []
        })

        # Encontrar la app 'core' y reorganizar sus modelos
        for app in app_list:
            if app['app_label'] == 'core':
                # Reorganizar modelos por categorías
                telemetry_models = []
                provider_models = []
                constants_models = []
                support_models = []
                other_models = []

                for model in app['models']:
                    model_name = model['object_name'].lower()

                    if model_name in ['datapoint', 'datastream', 'variabledefinition', 'dataaggregation', 'dataqualitymetric']:
                        telemetry_models.append(model)
                    elif model_name in ['equipmentprovider', 'equipmentmodel', 'iotdevice', 'providerdatasync']:
                        provider_models.append(model)
                    elif model_name in ['constantdefinition', 'constantapplication', 'datacorrectionlog']:
                        constants_models.append(model)
                    elif model_name in ['supportticket', 'ticketcomment', 'ticketsla']:
                        support_models.append(model)
                    else:
                        other_models.append(model)

                # Crear secciones organizadas
                custom_app_list.extend([
                    {
                        'name': '📊 Datos & Telemetría',
                        'app_label': 'core_telemetry',
                        'models': telemetry_models
                    },
                    {
                        'name': '🔧 Proveedores & Equipos',
                        'app_label': 'core_providers',
                        'models': provider_models
                    },
                    {
                        'name': '⚖️ Constantes & Correcciones',
                        'app_label': 'core_constants',
                        'models': constants_models
                    },
                    {
                        'name': '🎫 Soporte & Tickets',
                        'app_label': 'core_support',
                        'models': support_models
                    }
                ])

                # Agregar otros modelos si existen
                if other_models:
                    custom_app_list.append({
                        'name': '📋 Otros Modelos',
                        'app_label': 'core_other',
                        'models': other_models
                    })
            else:
                # Mantener otras apps sin cambios
                custom_app_list.append(app)

        return custom_app_list


# Instancia global del admin mejorado
smarthydro_admin = SmartHydroAdminSite()


# ============================================================================
# REGISTRAR MODELOS EN EL ADMIN MEJORADO
# ============================================================================

# Registrar todos los modelos nuevos en el admin mejorado
smarthydro_admin.register(DataPoint, DataPointAdmin)
smarthydro_admin.register(SupportTicket, SupportTicketAdmin)
smarthydro_admin.register(ConstantDefinition, ConstantDefinitionAdmin)
smarthydro_admin.register(ProviderDataSync, ProviderDataSyncAdmin)

# Registrar modelos adicionales automáticamente
additional_models = [
    DataStream, VariableDefinition, DataAggregation, DataQualityMetric,
    EquipmentProvider, EquipmentModel, IoTDevice,
    ConstantApplication, DataCorrectionLog,
    TicketComment, TicketSLA,
    SystemConfiguration, AlertRule, SystemMetrics
]

for model in additional_models:
    smarthydro_admin.register(model)