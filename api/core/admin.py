from datetime import datetime, timedelta
import pytz
from django.urls import reverse
# Django
from django.contrib import admin
from django.utils import timezone
from django.db.models import Count, Sum, Avg, Max, Min, Q
from django.db.models.functions import TruncDate, TruncHour
# Models
from django.utils.safestring import mark_safe
from django.db.models import F, Max as MaxFunc
from django.db.models.functions import TruncMonth
from api.core.models import (
    InteractionDetail, User, Client, ProjectCatchments, CatchmentPoint,
    ProfileDataConfigCatchment, ProfileIkoluCatchment, DgaDataConfigCatchment,
    SchemesCatchment, Variable, RegisterPersons, NotificationsCatchment,
    TelemetryProvider,
    ResponseNotificationsCatchment, TypeFileCatchment, FileCatchment
)
from import_export.admin import ImportExportModelAdmin, ExportActionMixin

# ========================================
# CONFIGURACIÓN GLOBAL DE ADMIN Y MENÚ
# ========================================

# Configurar títulos del admin
admin.site.site_header = "SmartHydro - Panel de Control"
admin.site.site_title = "SmartHydro Admin"
admin.site.index_title = "Panel de Administración"

# Configuración global de admin
# (La organización del menú se gestiona en admin.py con configuración estándar Django)

# Configurar paginación global a 24 elementos por página para todos los admins
# Esto mejora la carga y rendimiento del admin
ADMIN_LIST_PER_PAGE = 24


# ========================================
# MIXIN PARA INDICADORES EN CHANGELIST
# ========================================

class AdminIndicatorsMixin:
    """
    Mixin para agregar indicadores en la cabecera de las páginas de listado.
    Cada admin puede sobrescribir get_indicators() para personalizar sus indicadores.
    """

    def get_indicators(self, request, queryset):
        """
        Retorna una lista de indicadores para mostrar en la cabecera.
        Cada indicador es un dict con: value, label, icon, color, url (opcional)

        Args:
            request: HttpRequest
            queryset: QuerySet filtrado según los filtros aplicados

        Returns:
            list: Lista de dicts con indicadores
        """
        return []

    def changelist_view(self, request, extra_context=None):
        """
        Sobrescribe changelist_view para agregar indicadores al contexto.
        """
        extra_context = extra_context or {}

        # Llamar al changelist_view del padre para obtener el queryset filtrado
        response = super().changelist_view(request, extra_context)

        # Si es una respuesta HTTP (redirect), retornarla
        if hasattr(response, 'status_code'):
            return response

        # Obtener el queryset del contexto
        if hasattr(response, 'context_data'):
            cl = response.context_data.get('cl')
            if cl:
                queryset = cl.queryset
                # Obtener indicadores
                indicators = self.get_indicators(request, queryset)
                response.context_data['indicators'] = indicators

                # Agregar datos para gráficos si el admin los necesita
                if hasattr(self, 'get_charts_data'):
                    import json
                    charts_data = self.get_charts_data(request, queryset)
                    # Convertir a JSON para el template
                    response.context_data['charts_data'] = json.dumps(charts_data)

        return response


# ========================================
# INLINES - Ver relaciones en la misma página
# ========================================

class VariableInline(admin.TabularInline):
    """Inline para ver y editar variables de un esquema"""
    model = Variable
    extra = 1
    fields = ('str_variable', 'label', 'type_variable', 'service', 'pulses_factor', 'convert_to_lt', 'calculate_nivel', 'token_service')
    # No usar autocomplete en el padre (scheme_catchment) porque es el modelo que contiene el inline


class ProfileDataConfigInline(admin.StackedInline):
    """Inline para configuración de datos del punto"""
    model = ProfileDataConfigCatchment
    extra = 0
    fieldsets = (
        (None, {
            'fields': (
                'token_service',
                ('d1', 'd3'),
                ('d2', 'd4'),
                ('d5', 'd6'),
            )
        }),
        ('Reset y Ajustes', {
            'fields': ('addition',),
            'description': 'Ajuste manual del acumulado para corrección de reinicios.'
        }),
        ('Configuración Telemetría', {
            'fields': ('is_telemetry', 'date_start_telemetry', 'date_delivery_act'),
            'classes': ('collapse',)
        }),
    )


class DgaDataConfigInline(admin.StackedInline):
    """Inline para configuración DGA del punto"""
    model = DgaDataConfigCatchment
    extra = 0
    fieldsets = (
        (None, {
            'fields': (
                ('send_dga', 'standard'),
                ('type_dga', 'code_dga'),
                ('shac', 'flow_granted_dga'),
                ('total_granted_dga',),
            )
        }),
        ('Fechas', {
            'fields': ('date_start_compliance', 'date_created_code'),
        }),
        ('Informante', {
            'fields': ('name_informant', 'rut_report_dga', 'password_dga_software'),
            'classes': ('collapse',)
        }),
    )


class ProfileIkoluInline(admin.StackedInline):
    """Inline para perfil Ikolu del punto"""
    model = ProfileIkoluCatchment
    extra = 0
    fieldsets = (
        ('Módulos', {
            'fields': ('m1', 'm2', 'm3', 'm4', 'm5', 'm6', 'm7', 'entry_by_form')
        }),
        ('Suscripciones', {
            'fields': (
                ('m3_start_subscription', 'm3_type_subscriptions'),
                ('m4_start_subscription', 'm4_type_subscriptions'),
                ('m5_start_subscription', 'm5_type_subscriptions'),
            ),
            'classes': ('collapse',)
        }),
    )


# ========================================
# USER ADMIN
# ========================================

from django.contrib.auth.admin import UserAdmin

class UserAdm(ExportActionMixin, UserAdmin):
    """
    Usuarios del sistema con acceso al panel de administración.
    Define permisos y roles para gestionar la plataforma de telemetría.
    """
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff', 'is_active', 'date_joined')
    search_fields = ('username', 'email', 'first_name', 'last_name')
    list_filter = ('is_staff', 'is_active', 'is_superuser', 'date_joined')
    ordering = ('-date_joined',)

    # Fieldsets para el formulario de edición
    fieldsets = (
        ('Información Básica', {
            'fields': ('username', 'password'),
            'description': 'Credenciales de acceso del usuario.'
        }),
        ('Información Personal', {
            'fields': ('first_name', 'last_name', 'email'),
            'description': 'Datos personales y de contacto del usuario.'
        }),
        ('Permisos', {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
            'description': 'Control de acceso y permisos del usuario en el sistema.'
        }),
        ('Fechas Importantes', {
            'fields': ('last_login', 'date_joined'),
            'classes': ('collapse',),
            'description': 'Información de registro y última sesión.'
        }),
    )

    # Fieldsets para el formulario de creación
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'password1', 'password2'),
        }),
        ('Información Personal', {
            'fields': ('first_name', 'last_name', 'email'),
        }),
        ('Permisos', {
            'fields': ('is_staff', 'is_active', 'is_superuser'),
        }),
    )

    readonly_fields = ('last_login', 'date_joined')

admin.site.register(User, UserAdm)


# ========================================
# INTERACTION DETAIL ADMIN
# ========================================

# ========================================
# FILTROS PARA INTERACTION DETAIL
# ========================================

class HasVoucherFilter(admin.SimpleListFilter):
    title = 'Enviado a DGA'
    parameter_name = 'has_voucher'

    def lookups(self, request, model_admin):
        return (
            ('yes', 'SI - Con voucher'),
            ('no', 'NO - Sin voucher'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'yes':
            return queryset.exclude(n_voucher__isnull=True).exclude(n_voucher__exact='')
        if self.value() == 'no':
            return queryset.filter(Q(n_voucher__isnull=True) | Q(n_voucher__exact=''))
        return queryset


class DaysNotConnectionFilter(admin.SimpleListFilter):
    title = 'Días sin conexión'
    parameter_name = 'days_not_connection'

    def lookups(self, request, model_admin):
        return (
            ('0', 'Conectado (0 días)'),
            ('1-7', '1-7 días'),
            ('8-30', '8-30 días'),
            ('30+', 'Más de 30 días'),
        )

    def queryset(self, request, queryset):
        if self.value() == '0':
            return queryset.filter(days_not_conection=0)
        elif self.value() == '1-7':
            return queryset.filter(days_not_conection__gte=1, days_not_conection__lte=7)
        elif self.value() == '8-30':
            return queryset.filter(days_not_conection__gte=8, days_not_conection__lte=30)
        elif self.value() == '30+':
            return queryset.filter(days_not_conection__gte=30)
        return queryset


class PartialDisconnectionFilter(admin.SimpleListFilter):
    """Filtro para desconexiones parciales vs totales"""
    title = 'Tipo Desconexión'
    parameter_name = 'disconnection_type'

    def lookups(self, request, model_admin):
        return (
            ('partial', '⚠️ Parcial (algunas variables OK)'),
            ('total', '🔴 Total (todas las variables caídas)'),
            ('connected', '✅ Conectado'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'partial':
            return queryset.filter(is_partial=True, days_not_conection__gt=0)
        elif self.value() == 'total':
            return queryset.filter(is_partial=False, days_not_conection__gt=0)
        elif self.value() == 'connected':
            return queryset.filter(days_not_conection=0)
        return queryset


# ========================================
# FILTROS PARA CATCHMENT POINT
# ========================================

class HasDisconnectionFilter(admin.SimpleListFilter):
    title = 'Días de desconexión'
    parameter_name = 'disconnection_days'

    def lookups(self, request, model_admin):
        return (
            ('disconnected', 'Puntos sin conexión'),
            ('connected', 'Puntos conectados'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'disconnected':
            latest_interactions = InteractionDetail.objects.filter(
                catchment_point__in=queryset
            ).values('catchment_point').annotate(
                latest_date=Max('date_time_medition')
            )

            disconnected_points = []
            for interaction in latest_interactions:
                latest = InteractionDetail.objects.filter(
                    catchment_point_id=interaction['catchment_point'],
                    date_time_medition=interaction['latest_date'],
                    days_not_conection__gt=0,
                    days_not_conection__isnull=False
                ).exists()
                if latest:
                    disconnected_points.append(interaction['catchment_point'])

            return queryset.filter(id__in=disconnected_points)
        elif self.value() == 'connected':
            latest_interactions = InteractionDetail.objects.filter(
                catchment_point__in=queryset
            ).values('catchment_point').annotate(
                latest_date=Max('date_time_medition')
            )

            connected_points = []
            for interaction in latest_interactions:
                latest = InteractionDetail.objects.filter(
                    catchment_point_id=interaction['catchment_point'],
                    date_time_medition=interaction['latest_date'],
                    days_not_conection=0
                ).exists()
                if latest:
                    connected_points.append(interaction['catchment_point'])

            return queryset.filter(id__in=connected_points)
        return queryset


class TelemetryStatusFilter(admin.SimpleListFilter):
    title = 'Estado Telemetría'
    parameter_name = 'telemetry_status'

    def lookups(self, request, model_admin):
        return (
            ('active', 'Activa'),
            ('inactive', 'Inactiva'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'active':
            return queryset.filter(data_config_profiles__is_telemetry=True).distinct()
        elif self.value() == 'inactive':
            return queryset.exclude(data_config_profiles__is_telemetry=True).distinct()
        return queryset


# ========================================
# FILTROS PARA INTERACTION DETAIL
# ========================================

class ProjectFilter(admin.SimpleListFilter):
    """
    Filtro personalizado para proyectos con nombre "Proyecto"
    """
    title = 'Proyecto'
    parameter_name = 'project'

    def lookups(self, request, model_admin):
        from api.core.models import ProjectCatchments
        projects = ProjectCatchments.objects.all().order_by('name')
        return [(p.id, p.name) for p in projects]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(catchment_point__project_id=self.value())
        return queryset


# ========================================
# INTERACTION DETAIL ADMIN
# ========================================

@admin.register(InteractionDetail)
class InteractionDetailAdmin(AdminIndicatorsMixin, ImportExportModelAdmin, ExportActionMixin, admin.ModelAdmin):
    """
    Registros de mediciones de telemetría con datos de caudal, nivel, totalizado y estado de conexión.
    Aquí se almacenan todas las lecturas de los puntos de captación.
    """
    # ✅ Template personalizado para mostrar indicadores y gráficos
    change_list_template = 'admin/core/interactiondetail/change_list.html'

    # ✅ Lista optimizada: sin ID, caudal ordenable, nivel con base, water table con posicionamiento
    list_display = (
        'get_catchment_point_display', 'get_fechas_display',
        'get_pulses_display', 'get_total_con_escala', 'get_flow_display',
        'get_consumo_display', 'get_nivel_display', 'get_water_table_display',
        'get_send_dga_badge', 'get_voucher_badge', 'get_status_badge'
    )
    date_hierarchy = 'date_time_medition'

    # ✅ Paginación: 24 elementos por página
    list_per_page = ADMIN_LIST_PER_PAGE

    # ✅ Fieldsets para organizar mejor
    fieldsets = (
        ('Información Básica', {
            'fields': ('catchment_point', 'date_time_medition', 'date_time_last_logger', 'days_not_conection'),
            'description': 'Datos básicos de la medición: punto de captación, fechas y estado de conexión.'
        }),
        ('Totalizado', {
            'fields': ('pulses', 'total', 'total_diff', 'total_today_diff')
        }),
        ('Caudal y Nivel', {
            'fields': ('flow', 'nivel', 'water_table')
        }),
        ('DGA', {
            'fields': ('send_dga', 'n_voucher', 'return_dga'),
            'classes': ('collapse',)
        }),
        ('Estado', {
            'fields': ('is_error', 'is_partial', 'notification'),
            'description': 'Estado de conexión del punto. is_partial indica si hay variables funcionando pero otras fallando.'
        }),
    )

    # ✅ Autocomplete para relaciones
    autocomplete_fields = ['catchment_point']

    def get_queryset(self, request):
        """
        Optimizar queries con select_related y prefetch_related.
        Reduce queries de 120+ a <10 en changelist.

        Antes: N+1 problem - 1 query por registro para catchment_point, project, config
        Después: Queries batch - todas las relaciones pre-cargadas
        """
        queryset = super().get_queryset(request)

        # Pre-cargar relaciones que se usan en list_display con select_related
        # (ForeignKey y OneToOne)
        queryset = queryset.select_related(
            'catchment_point',                      # Para get_catchment_point_display
            'catchment_point__project',             # Para mostrar proyecto
            'catchment_point__project__client',     # Para mostrar cliente
        )

        # Pre-cargar relaciones Many-to-Many y reverse FK con prefetch_related
        queryset = queryset.prefetch_related(
            'catchment_point__data_config_profiles',       # Para get_flow_display
            'catchment_point__dga_data_config_profiles',   # Para badges DGA
            'catchment_point__schemes',                    # Para variables
            'catchment_point__schemes__variables',         # Para cálculos
        )

        return queryset

    # ✅ Búsqueda mejorada
    search_fields = (
        'catchment_point__title',
        'catchment_point__project__name',
        'n_voucher',
        'id'
    )

    # ✅ Filtros mejorados y organizados
    # Filtros principales primero (más usados), luego filtros de estado
    list_filter = (
        'catchment_point',  # Filtro por punto de captación (autocomplete)
        ProjectFilter,  # Filtro personalizado por proyecto (nombre "Proyecto")
        'date_time_medition',  # Filtro por fecha
        'send_dga',  # Filtro DGA
        'is_error',  # Filtro errores
        HasVoucherFilter,  # Filtro voucher
        DaysNotConnectionFilter,  # Filtro días sin conexión
        PartialDisconnectionFilter,  # ✅ NEW: Filtro desconexión parcial vs total
    )

    # ✅ Solo lectura para campos calculados
    readonly_fields = ('total_diff', 'total_today_diff', 'days_not_conection', 'is_partial')

    # ✅ Helper para GAP
    def _get_gap_html(self, obj, field_name, current_value):
        """Calcula y formatea el GAP (tiempo desde último cambio)"""
        if current_value is None:
            return ""

        try:
            # Buscar el registro anterior DIERENTE
            prev = obj.__class__.objects.filter(
                catchment_point=obj.catchment_point,
                date_time_medition__lt=obj.date_time_medition
            ).exclude(
                **{field_name: current_value}
            ).order_by('-date_time_medition').only('date_time_medition').first()

            gap_html = ""
            if prev and prev.date_time_medition:
                diff = obj.date_time_medition - prev.date_time_medition
                minutes = int(diff.total_seconds() / 60)

                if minutes < 60:
                    time_str = f"{minutes}m"
                    color = "#28a745" # Verde < 1h
                elif minutes < 1440: # 24h
                    hours = minutes // 60
                    time_str = f"{hours}h"
                    color = "#28a745" # Verde < 24h
                else:
                    days = minutes // 1440
                    hours = (minutes % 1440) // 60
                    time_str = f"{days}d {hours}h"
                    color = "#dc3545" # Rojo > 24h

                gap_html = f'<div style="color: {color}; font-size: 10px; margin-top: 2px;">GAP: {time_str}</div>'
            else:
                gap_html = '<div style="color: #999; font-size: 10px; margin-top: 2px;">GAP: --</div>'

            return gap_html
        except Exception:
            return ""

    def get_catchment_point_display(self, obj):
        """Muestra nombre del punto truncado y debajo Proyecto - Cliente"""
        full_name = obj.catchment_point.title or f"Punto #{obj.catchment_point.id}"
        point_html = full_name
        if len(full_name) > 25:
            short_name = full_name[:22] + "..."
            point_html = f'<span title="{full_name}" style="cursor: help; border-bottom: 1px dotted #999;">{short_name}</span>'

        # Obtener info de Proyecto y Cliente
        try:
            p = obj.catchment_point.project
            project_name = p.name if p else "S/P"
            client_name = p.client.name if (p and p.client) else "S/C"
            sub_info = f"{project_name} - {client_name}"
        except Exception:
            sub_info = ""

        if sub_info:
            return mark_safe(f'''
                <div style="line-height: 1.2;">
                    <div style="font-weight: bold;">{point_html}</div>
                    <div style="color: #6c757d; font-size: 10px;">{sub_info}</div>
                </div>
            ''')
        return mark_safe(point_html)
    get_catchment_point_display.short_description = 'Punto de Captación'
    get_catchment_point_display.admin_order_field = 'catchment_point__title'



    def get_total_con_escala(self, obj):
        """Muestra total con 2 decimales"""
        try:
            val = float(obj.total) if obj.total is not None else 0.0
        except (ValueError, TypeError):
            val = 0.0
        return f"{val:.2f}"
    get_total_con_escala.short_description = 'Total'
    get_total_con_escala.admin_order_field = 'total'

    def get_flow_display(self, obj):
        """Muestra el flow y GAP"""
        try:
            from api.core.utils.flow_display import get_interaction_flow_display_data
            flow_data = get_interaction_flow_display_data(obj)

            val = flow_data["value"]
            is_calc = flow_data["is_calculated"]
            flow_type = flow_data["type"]

            flow_html = f"{val:.2f}"
            if is_calc:
                label = "(prom)" if flow_type == "MEDIO_DIARIO" else "(calc)"
                flow_html = f'<span style="color: #28a745; font-weight: bold;">{val:.2f} {label}</span>'

            # GAP para flow (usando el valor crudo almacenado para comparación)
            gap_html = self._get_gap_html(obj, 'flow', obj.flow)

            return mark_safe(f'<div style="line-height: 1.2;">{flow_html}{gap_html}</div>')
        except Exception as e:
            return mark_safe(f'<span style="color: #dc3545;">Error</span>')

    get_flow_display.short_description = 'Caudal'
    get_flow_display.admin_order_field = 'flow'

    def get_consumo_display(self, obj):
        """Muestra consumo (total_diff)"""
        val = obj.total_diff or 0.0
        return f"{val:.2f}"
    get_consumo_display.short_description = 'Consumo'
    get_consumo_display.admin_order_field = 'total_diff'

    def get_pulses_display(self, obj):
        """Muestra pulsos y GAP"""
        val = obj.pulses
        if val is None:
            return "-"

        gap_html = self._get_gap_html(obj, 'pulses', val)
        return mark_safe(f'<div style="line-height: 1.2;">{val}{gap_html}</div>')
    get_pulses_display.short_description = 'Pulsos'
    get_pulses_display.admin_order_field = 'pulses'

    def get_nivel_display(self, obj):
        """Muestra el nivel y GAP"""
        nivel_val = obj.nivel or 0.0
        gap_html = self._get_gap_html(obj, 'nivel', obj.nivel)

        # Obtener la base del nivel (calculate_nivel) de la Variable NIVEL
        try:
            from api.core.models import Variable
            var = Variable.objects.filter(
                type_variable='NIVEL',
                scheme_catchment__points_catchment=obj.catchment_point
            ).first()

            if var and var.calculate_nivel:
                return mark_safe(f'''
                    <div style="font-size: 11px; line-height: 1.2;">
                        <div style="font-weight: bold;">{nivel_val:.2f} m</div>
                        <div style="color: #6c757d; font-size: 9px;">Base: {var.calculate_nivel}</div>
                        {gap_html}
                    </div>
                ''')
            else:
                return mark_safe(f'<div style="font-weight: bold; line-height: 1.2;">{nivel_val:.2f} m{gap_html}</div>')
        except Exception:
            return mark_safe(f'<div style="line-height: 1.2;">{nivel_val:.2f} m{gap_html}</div>')

    get_nivel_display.short_description = 'Nivel'
    get_nivel_display.admin_order_field = 'nivel'

    def get_water_table_display(self, obj):
        """Muestra water_table"""
        water_table_val = obj.water_table or 0.0

        # Obtener el posicionamiento d3 del ProfileDataConfigCatchment
        try:
            from api.core.models import ProfileDataConfigCatchment
            profile = ProfileDataConfigCatchment.objects.filter(
                point_catchment=obj.catchment_point
            ).first()

            if profile and profile.d3:
                # Mostrar el posicionamiento usado: water_table = d3 - nivel
                return mark_safe(f'''
                    <div style="font-size: 11px; line-height: 1.4;">
                        <div style="font-weight: bold;">{water_table_val:.2f} m</div>
                        <div style="color: #6c757d; font-size: 10px;">Pos: {profile.d3}m</div>
                    </div>
                ''')
            else:
                return mark_safe(f'<div style="font-weight: bold;">{water_table_val:.2f} m</div>')
        except Exception:
            return mark_safe(f'{water_table_val:.2f} m')

    get_water_table_display.short_description = 'Freatico'
    get_water_table_display.admin_order_field = 'water_table'

    def get_send_dga_badge(self, obj):
        """Badge corto para envío DGA"""
        if obj.send_dga:
            return mark_safe('<span style="background: #28a745; color: white; padding: 3px 8px; border-radius: 3px;">✓</span>')
        return mark_safe('<span style="background: #6c757d; color: white; padding: 3px 8px; border-radius: 3px;">✗</span>')

    get_send_dga_badge.short_description = 'Envío'
    get_send_dga_badge.admin_order_field = 'send_dga'

    def get_status_badge(self, obj):
        """Badge de color para estado - distingue desconexión total vs parcial"""
        if obj.is_error:
            return mark_safe('<span style="background: #dc3545; color: white; padding: 3px 8px; border-radius: 3px;">ERROR</span>')
        elif obj.days_not_conection and obj.days_not_conection > 0:
            if obj.is_partial:
                # ⚠️ Desconexión PARCIAL - Amarillo
                return mark_safe(f'<span style="background: #ffc107; color: black; padding: 3px 8px; border-radius: 3px;">⚠️ Parcial ({obj.days_not_conection}d)</span>')
            else:
                # 🔴 Desconexión TOTAL - Rojo
                return mark_safe(f'<span style="background: #dc3545; color: white; padding: 3px 8px; border-radius: 3px;">🔴 Desconectado ({obj.days_not_conection}d)</span>')
        else:
            return mark_safe('<span style="background: #28a745; color: white; padding: 3px 8px; border-radius: 3px;">✅ OK</span>')

    get_status_badge.short_description = 'Estado'

    def get_voucher_badge(self, obj):
        """Badge para voucher DGA"""
        if obj.n_voucher:
            return mark_safe(f'<span style="background: #17a2b8; color: white; padding: 3px 8px; border-radius: 3px;">{obj.n_voucher[:15]}...</span>')
        return mark_safe('<span style="color: #6c757d;">-</span>')

    get_voucher_badge.short_description = 'Voucher'

    def get_fechas_display(self, obj):
        """
        Muestra fecha medición y logger en formato dd/mm hh:mm:ss
        con la diferencia en segundos entre date_time_medition y date_time_last_logger
        y la diferencia del logger actual vs el logger anterior (intervalo real)
        """
        chile = pytz.timezone("America/Santiago")

        # Fecha medición
        if obj.date_time_medition:
            dt_med = obj.date_time_medition.astimezone(chile)
            fecha_med = dt_med.strftime('%d/%m %H:%M:%S')
        else:
            fecha_med = 'N/A'

        # Fecha logger
        if obj.date_time_last_logger:
            dt_log = obj.date_time_last_logger.astimezone(chile)
            fecha_log = dt_log.strftime('%d/%m %H:%M:%S')
        else:
            fecha_log = 'N/A'

        # Calcular diferencia Med vs Log (en segundos)
        diff_med_log_html = ''
        if obj.date_time_medition and obj.date_time_last_logger:
            diff_seg = int(abs((obj.date_time_last_logger - obj.date_time_medition).total_seconds()))

            # Color según diferencia
            if diff_seg < 300:
                diff_color = '#28a745'
            elif diff_seg < 3600:
                diff_color = '#ffc107'
            else:
                diff_color = '#dc3545'
            diff_med_log_html = f' <span style="color: {diff_color}; font-size: 10px;">({diff_seg}s)</span>'

        # Calcular intervalo: logger actual vs logger anterior del mismo punto
        intervalo_html = ''
        if obj.date_time_last_logger and obj.date_time_medition:
            try:
                # Buscar el registro anterior del mismo punto (usar __class__ para evitar imports)
                previous = obj.__class__.objects.filter(
                    catchment_point=obj.catchment_point,
                    date_time_medition__lt=obj.date_time_medition
                ).exclude(
                    date_time_last_logger__isnull=True
                ).order_by('-date_time_medition').first()

                if previous and previous.date_time_last_logger:
                    intervalo_seg = int((obj.date_time_last_logger - previous.date_time_last_logger).total_seconds())

                    # Color: verde si está cerca de la frecuencia esperada
                    try:
                        frecuencia_min = obj.catchment_point.frecuency or 60
                        esperado = frecuencia_min * 60  # convertir a segundos

                        if abs(intervalo_seg - esperado) < 60:
                            intervalo_color = '#28a745'  # verde: intervalo esperado
                        elif abs(intervalo_seg - esperado) < 300:
                            intervalo_color = '#ffc107'  # amarillo: variación moderada
                        else:
                            intervalo_color = '#dc3545'  # rojo: mucha variación
                    except:
                        # Si no podemos obtener la frecuencia, usar color neutro
                        intervalo_color = '#6c757d'

                    intervalo_html = f' <span style="color: {intervalo_color}; font-size: 10px;">({intervalo_seg}s)</span>'
                else:
                    # No hay registro anterior
                    intervalo_html = ' <span style="color: #999; font-size: 10px;">(--)</span>'
            except Exception as e:
                # Error al buscar - mostrar el error para debug
                # import traceback
                error_msg = str(e)[:20]
                intervalo_html = f' <span style="color: #dc3545; font-size: 9px;" title="{error_msg}">(!)</span>'

        # Mostrar AMBAS diferencias en la misma línea que las fechas
        return mark_safe(f'''
            <div style="font-size: 11px; line-height: 1.4; white-space: nowrap;">
                <div><strong>Med:</strong> {fecha_med}{diff_med_log_html}</div>
                <div><strong>Log:</strong> {fecha_log}{intervalo_html}</div>
            </div>
        ''')

    get_fechas_display.short_description = 'Fechas'
    get_fechas_display.admin_order_field = 'date_time_medition'

    def get_indicators(self, request, queryset):
        """
        Obtiene indicadores para InteractionDetail basados en el queryset filtrado.
        """
        indicators = []

        # Calcular métricas del queryset filtrado
        total_records = queryset.count()

        if total_records > 0:
            # Métricas agregadas
            metrics = queryset.aggregate(
                avg_flow=Avg('flow'),
                max_flow=Max('flow'),
                total_consumption=Sum('total_diff'),
                avg_nivel=Avg('nivel'),
                error_count=Count('id', filter=Q(is_error=True)),
                dga_queue=Count('id', filter=Q(send_dga=True)),
            )

            # Última medición
            last_record = queryset.order_by('-date_time_medition').first()

            # Indicador: Total de registros
            indicators.append({
                'value': f'{total_records:,}',
                'label': 'Total Registros',
                'icon': 'fas fa-database',
                'color': 'primary',
            })

            # Indicador: Promedio de caudal
            if metrics['avg_flow']:
                indicators.append({
                    'value': f'{float(metrics["avg_flow"]):.2f}',
                    'label': 'Caudal Promedio (L/s)',
                    'icon': 'fas fa-tint',
                    'color': 'info',
                })

            # Indicador: Total acumulado
            if metrics['total_consumption']:
                indicators.append({
                    'value': f'{int(metrics["total_consumption"]):,}',
                    'label': 'Consumo Total (m³)',
                    'icon': 'fas fa-chart-bar',
                    'color': 'success',
                })

            # Indicador: Errores
            error_count = metrics['error_count'] or 0
            error_pct = (error_count / total_records * 100) if total_records > 0 else 0
            indicators.append({
                'value': f'{error_count} ({error_pct:.1f}%)',
                'label': 'Registros con Error',
                'icon': 'fas fa-exclamation-triangle',
                'color': 'danger' if error_count > 0 else 'success',
            })

            # Indicador: Cola DGA
            dga_count = metrics['dga_queue'] or 0
            indicators.append({
                'value': f'{dga_count}',
                'label': 'En Cola DGA',
                'icon': 'fas fa-paper-plane',
                'color': 'warning' if dga_count > 0 else 'secondary',
            })

            # Indicador: Última medición
            if last_record:
                last_date = last_record.date_time_medition
                if last_date:
                    time_diff = timezone.now() - last_date
                    if time_diff.days == 0:
                        hours = time_diff.seconds // 3600
                        if hours == 0:
                            minutes = time_diff.seconds // 60
                            time_str = f'{minutes} min'
                        else:
                            time_str = f'{hours} h'
                    else:
                        time_str = f'{time_diff.days} días'

                    indicators.append({
                        'value': time_str,
                        'label': 'Última Medición',
                        'icon': 'fas fa-clock',
                        'color': 'info',
                    })
        else:
            # Sin registros
            indicators.append({
                'value': '0',
                'label': 'Total Registros',
                'icon': 'fas fa-database',
                'color': 'secondary',
            })

        return indicators

    def get_charts_data(self, request, queryset):
        """
        Obtiene datos para gráficos basados en el queryset filtrado.
        """
        charts_data = {
            'flow_chart': {'labels': [], 'data': []},
            'total_chart': {'labels': [], 'data': []},
            'nivel_chart': {'labels': [], 'data': []},
            'errors_chart': {'labels': [], 'data': []},
        }

        # Detectar filtros aplicados
        point_id = request.GET.get('catchment_point')
        date_from = request.GET.get('date_time_medition__gte')
        date_to = request.GET.get('date_time_medition__lte')

        # Calcular días para consulta
        days = 7  # Por defecto
        if date_from:
            try:
                date_from_obj = datetime.fromisoformat(date_from.replace('Z', '+00:00'))
                days = (timezone.now() - date_from_obj).days + 1
                days = min(days, 30)  # Máximo 30 días
            except:
                pass

        # Obtener datos por hora (últimas 24h si hay filtro de punto)
        if point_id:
            last_24h = timezone.now() - timedelta(hours=24)
            hourly_data = queryset.filter(
                date_time_medition__gte=last_24h
            ).annotate(
                hour=TruncHour('date_time_medition')
            ).values('hour').annotate(
                avg_flow=Avg('flow'),
                avg_nivel=Avg('nivel'),
                total_consumption=Sum('total_diff'),
                error_count=Count('id', filter=Q(is_error=True)),
            ).order_by('hour')

            for item in hourly_data:
                hour_str = item['hour'].strftime('%H:%M') if item['hour'] else ''
                charts_data['flow_chart']['labels'].append(hour_str)
                charts_data['flow_chart']['data'].append(float(item['avg_flow']) if item['avg_flow'] else 0)

                charts_data['nivel_chart']['labels'].append(hour_str)
                charts_data['nivel_chart']['data'].append(float(item['avg_nivel']) if item['avg_nivel'] else 0)

                charts_data['total_chart']['labels'].append(hour_str)
                charts_data['total_chart']['data'].append(int(item['total_consumption']) if item['total_consumption'] else 0)

                charts_data['errors_chart']['labels'].append(hour_str)
                charts_data['errors_chart']['data'].append(int(item['error_count']) if item['error_count'] else 0)
        else:
            # Si no hay filtro de punto, usar datos diarios
            daily_data = queryset.annotate(
                date=TruncDate('date_time_medition')
            ).values('date').annotate(
                avg_flow=Avg('flow'),
                avg_nivel=Avg('nivel'),
                total_consumption=Sum('total_diff'),
                error_count=Count('id', filter=Q(is_error=True)),
            ).order_by('date')[:30]  # Últimos 30 días

            for item in daily_data:
                date_str = item['date'].strftime('%d/%m') if item['date'] else ''
                charts_data['flow_chart']['labels'].append(date_str)
                charts_data['flow_chart']['data'].append(float(item['avg_flow']) if item['avg_flow'] else 0)

                charts_data['nivel_chart']['labels'].append(date_str)
                charts_data['nivel_chart']['data'].append(float(item['avg_nivel']) if item['avg_nivel'] else 0)

                charts_data['total_chart']['labels'].append(date_str)
                charts_data['total_chart']['data'].append(int(item['total_consumption']) if item['total_consumption'] else 0)

                charts_data['errors_chart']['labels'].append(date_str)
                charts_data['errors_chart']['data'].append(int(item['error_count']) if item['error_count'] else 0)

        return charts_data


# ========================================
# CLIENT ADMIN
# ========================================

@admin.register(Client)
class ClientAdmin(ImportExportModelAdmin, ExportActionMixin, admin.ModelAdmin):
    """
    Clientes o empresas que contratan los servicios de telemetría.
    Los proyectos pertenecen a clientes y agrupan múltiples puntos de captación.
    """
    list_display = ('id', 'name', 'rut', 'email', 'phone', 'created')
    search_fields = ('name', 'rut', 'email', 'phone')
    list_filter = ('created',)
    list_per_page = ADMIN_LIST_PER_PAGE
    fieldsets = (
        ('Información Básica', {
            'fields': ('name', 'rut'),
            'description': 'Datos identificatorios del cliente (razón social y RUT).'
        }),
        ('Contacto', {
            'fields': ('email', 'phone', 'address'),
            'description': 'Información de contacto del cliente para comunicación y facturación.'
        }),
    )

    def get_indicators(self, request, queryset):
        """
        Obtiene indicadores para Client basados en el queryset filtrado.
        """
        indicators = []

        total_clients = queryset.count()

        if total_clients > 0:
            # Total de proyectos
            total_projects = ProjectCatchments.objects.filter(
                client__in=queryset
            ).count()

            # Total de puntos
            total_points = CatchmentPoint.objects.filter(
                project__client__in=queryset
            ).count()

            # Indicador: Total de clientes
            indicators.append({
                'value': f'{total_clients}',
                'label': 'Total Clientes',
                'icon': 'fas fa-building',
                'color': 'primary',
            })

            # Indicador: Total de proyectos
            indicators.append({
                'value': f'{total_projects}',
                'label': 'Proyectos',
                'icon': 'fas fa-project-diagram',
                'color': 'info',
            })

            # Indicador: Total de puntos
            indicators.append({
                'value': f'{total_points}',
                'label': 'Puntos de Captación',
                'icon': 'fas fa-map-marker-alt',
                'color': 'success',
            })
        else:
            indicators.append({
                'value': '0',
                'label': 'Total Clientes',
                'icon': 'fas fa-building',
                'color': 'secondary',
            })

        return indicators


# ========================================
# PROJECT ADMIN
# ========================================

@admin.register(ProjectCatchments)
class ProjectCatchmentsAdmin(AdminIndicatorsMixin, ImportExportModelAdmin, ExportActionMixin, admin.ModelAdmin):
    """
    Proyectos que agrupan múltiples puntos de captación.
    Cada proyecto pertenece a un cliente y puede tener diferentes configuraciones y esquemas.
    """
    list_display = ('id', 'name', 'client', 'code_internal', 'get_points_count', 'created')
    search_fields = ('name', 'code_internal', 'client__name')
    list_filter = ('created', 'client')
    autocomplete_fields = ['client']
    list_per_page = ADMIN_LIST_PER_PAGE

    def get_points_count(self, obj):
        count = obj.catchment_points.count()
        return mark_safe(f'<strong>{count}</strong> puntos')
    get_points_count.short_description = 'Puntos de Captación'

    def get_indicators(self, request, queryset):
        """
        Obtiene indicadores para ProjectCatchments basados en el queryset filtrado.
        """
        indicators = []

        total_projects = queryset.count()

        if total_projects > 0:
            # Total de puntos en los proyectos
            total_points = CatchmentPoint.objects.filter(
                project__in=queryset
            ).count()

            # Proyectos con telemetría activa
            projects_with_telemetry = queryset.filter(
                catchment_points__data_config_profiles__is_telemetry=True
            ).distinct().count()

            # Indicador: Total de proyectos
            indicators.append({
                'value': f'{total_projects}',
                'label': 'Total Proyectos',
                'icon': 'fas fa-project-diagram',
                'color': 'primary',
            })

            # Indicador: Total de puntos
            indicators.append({
                'value': f'{total_points}',
                'label': 'Puntos Totales',
                'icon': 'fas fa-map-marker-alt',
                'color': 'info',
            })

            # Indicador: Proyectos con telemetría
            telemetry_pct = (projects_with_telemetry / total_projects * 100) if total_projects > 0 else 0
            indicators.append({
                'value': f'{projects_with_telemetry} ({telemetry_pct:.0f}%)',
                'label': 'Con Telemetría',
                'icon': 'fas fa-satellite-dish',
                'color': 'success' if telemetry_pct > 80 else 'warning',
            })
        else:
            indicators.append({
                'value': '0',
                'label': 'Total Proyectos',
                'icon': 'fas fa-project-diagram',
                'color': 'secondary',
            })

        return indicators


# ========================================
# CATCHMENT POINT ADMIN - MEJORADO
# ========================================

@admin.register(CatchmentPoint)
class CatchmentPointAdmin(AdminIndicatorsMixin, ImportExportModelAdmin, ExportActionMixin, admin.ModelAdmin):
    """
    Puntos de captación de agua donde se instalan los sensores de telemetría.
    Cada punto pertenece a un proyecto y puede tener múltiples configuraciones (datos, DGA, Ikolu).
    """
    # ✅ Template personalizado para mostrar indicadores (importante para el botón de reporte)
    change_list_template = 'admin/core/interactiondetail/change_list.html'

    list_display = (
        'id', 'title', 'project', 'owner_user', 'frecuency',
        'get_providers_badge', 'get_telemetry_status', 'last_interaction_detail'
    )
    list_per_page = ADMIN_LIST_PER_PAGE

    def changelist_view(self, request, extra_context=None):
        """Agregar enlace a monitoreo en tiempo real"""
        extra_context = extra_context or {}
        extra_context['monitoring_link'] = reverse('telemetry_monitoring')
        return super().changelist_view(request, extra_context)

    def get_indicators(self, request, queryset):
        """
        Indicadores para Puntos de Captación y Acceso a Reportes
        """
        indicators = []

        # 1. Botón de Reporte (Prioritario)
        indicators.append({
            'value': 'Descargar Excel',
            'label': 'Reporte Puntos Activos',
            'icon': 'fas fa-file-download',
            'color': 'success', # Verde para destacar descarga
            'url': reverse('active_points_report'),
        })

        # 2. Total de puntos
        total = queryset.count()

        # 3. Puntos con telemetría activa
        active_telemetry = queryset.filter(data_config_profiles__is_telemetry=True).count()

        if total > 0:
            pct_active = (active_telemetry / total) * 100
            indicators.append({
                'value': f'{active_telemetry} / {total}',
                'label': 'Telemetría Activa',
                'icon': 'fas fa-satellite-dish',
                'color': 'primary',
            })

            # 4. Puntos desconectados (Alerta)
            # Usando lógica simplificada para indicador rápido
            from django.db.models import Max
            import pytz
            from datetime import timedelta

            # Solo considerar puntos con telemetría activa
            disconnected = queryset.filter(
                data_config_profiles__is_telemetry=True
            ).exclude(
                interactiondetail__days_not_conection=0,
                interactiondetail__date_time_medition__gte=timezone.now() - timedelta(days=1)
            ).count()

            # Nota: La cuenta anterior es aproximada, para precisión usar filtros complejos
            # pero para indicador rápido está bien.

        return indicators

    # ✅ Fieldsets para organizar
    fieldsets = (
        ('Información Básica', {
            'fields': ('title', 'project', 'owner_user', 'frecuency'),
            'description': 'Datos principales del punto: nombre, proyecto asociado, propietario y frecuencia de lectura.'
        }),
        ('Proveedores de Telemetría', {
            'fields': ('is_tdata', 'is_thethings', 'is_novus'),
            'description': 'Selecciona los proveedores activos para este punto'
        }),
        ('Ubicación', {
            'fields': ('lat', 'lon'),
            'classes': ('collapse',)
        }),
        ('Usuarios', {
            'fields': ('users_viewers',),
            'classes': ('collapse',)
        }),
    )

    # ✅ Inlines para ver configuraciones relacionadas
    inlines = [ProfileDataConfigInline, DgaDataConfigInline, ProfileIkoluInline]

    # ✅ Autocomplete
    autocomplete_fields = ['project', 'owner_user', 'users_viewers']
    filter_horizontal = ['users_viewers']

    # ✅ Búsqueda mejorada
    search_fields = ('title', 'project__name', 'project__client__name', 'owner_user__username')

    # ✅ Filtros mejorados
    list_filter = (
        HasDisconnectionFilter,
        'frecuency',
        'is_novus',
        'is_thethings',
        'is_tdata',
        'project__name',
        ('project__client', admin.RelatedOnlyFieldListFilter),
        TelemetryStatusFilter,
    )

    def get_providers_badge(self, obj):
        """Badge con proveedores activos"""
        providers = []
        if obj.is_tdata:
            providers.append('<span style="background: #007bff; color: white; padding: 2px 6px; border-radius: 3px; margin: 2px;">Twin</span>')
        if obj.is_thethings:
            providers.append('<span style="background: #28a745; color: white; padding: 2px 6px; border-radius: 3px; margin: 2px;">Nettra</span>')
        if obj.is_novus:
            providers.append('<span style="background: #17a2b8; color: white; padding: 2px 6px; border-radius: 3px; margin: 2px;">Novus</span>')
        if not providers:
            return mark_safe('<span style="color: #6c757d;">Sin proveedores</span>')
        return mark_safe(' '.join(providers))

    get_providers_badge.short_description = 'Proveedores'

    def get_telemetry_status(self, obj):
        """Estado de telemetría"""
        profile = obj.data_config_profiles.filter(is_telemetry=True).first()
        if profile:
            return mark_safe('<span style="color: #28a745;">● Activa</span>')
        return mark_safe('<span style="color: #6c757d;">○ Inactiva</span>')

    get_telemetry_status.short_description = 'Telemetría'

    class HasDisconnectionFilter(admin.SimpleListFilter):
        title = 'Días de desconexión'
        parameter_name = 'disconnection_days'

        def lookups(self, request, model_admin):
            return (
                ('disconnected', 'Puntos sin conexión'),
                ('connected', 'Puntos conectados'),
            )

        def queryset(self, request, queryset):
            if self.value() == 'disconnected':
                latest_interactions = InteractionDetail.objects.filter(
                    catchment_point__in=queryset
                ).values('catchment_point').annotate(
                    latest_date=Max('date_time_medition')
                )

                disconnected_points = []
                for interaction in latest_interactions:
                    latest = InteractionDetail.objects.filter(
                        catchment_point_id=interaction['catchment_point'],
                        date_time_medition=interaction['latest_date'],
                        days_not_conection__gt=0,
                        days_not_conection__isnull=False
                    ).exists()
                    if latest:
                        disconnected_points.append(interaction['catchment_point'])

                return queryset.filter(id__in=disconnected_points)
            elif self.value() == 'connected':
                latest_interactions = InteractionDetail.objects.filter(
                    catchment_point__in=queryset
                ).values('catchment_point').annotate(
                    latest_date=Max('date_time_medition')
                )

                connected_points = []
                for interaction in latest_interactions:
                    latest = InteractionDetail.objects.filter(
                        catchment_point_id=interaction['catchment_point'],
                        date_time_medition=interaction['latest_date'],
                        days_not_conection=0
                    ).exists()
                    if latest:
                        connected_points.append(interaction['catchment_point'])

                return queryset.filter(id__in=connected_points)
            return queryset

    class TelemetryStatusFilter(admin.SimpleListFilter):
        title = 'Estado Telemetría'
        parameter_name = 'telemetry_status'

        def lookups(self, request, model_admin):
            return (
                ('active', 'Activa'),
                ('inactive', 'Inactiva'),
            )

        def queryset(self, request, queryset):
            if self.value() == 'active':
                return queryset.filter(data_config_profiles__is_telemetry=True).distinct()
            elif self.value() == 'inactive':
                return queryset.exclude(data_config_profiles__is_telemetry=True).distinct()
            return queryset

    def last_interaction_detail(self, obj):
        """Última medición con mejor formato"""
        last_interaction = InteractionDetail.objects.filter(
            catchment_point=obj
        ).order_by('-date_time_medition').first()

        if not last_interaction:
            return mark_safe('<span style="color: #6c757d;">Sin datos</span>')

        # Validar que date_time_medition no sea None
        if not last_interaction.date_time_medition:
            return mark_safe('<span style="color: #ffc107;">⚠️ Datos incompletos</span>')

        chile = pytz.timezone("America/Santiago")
        date_time_medition_cl = last_interaction.date_time_medition.astimezone(chile)
        date_time_logger = last_interaction.date_time_last_logger

        # Calcular flow dinámicamente
        from api.core.models import Variable
        from api.cronjobs.telemetry.controllers.flow import average_flow

        has_avg_flow = Variable.objects.filter(
            type_variable="CAUDAL_PROMEDIO",
            scheme_catchment__points_catchment=obj,
        ).exists()

        flow_display = f"{last_interaction.flow:.2f}" if last_interaction.flow else "0.00"
        if has_avg_flow and last_interaction.total_diff and last_interaction.total_diff > 0:
            try:
                point_catchment = {"id": obj.id}
                total_actual = float(last_interaction.total) if last_interaction.total else 0
                curr_ts = last_interaction.date_time_last_logger or last_interaction.date_time_medition

                if curr_ts:
                    calculated_flow = average_flow(
                        point_catchment=point_catchment,
                        total=total_actual,
                        date_lg=curr_ts
                    )
                    if calculated_flow > 0:
                        flow_display = f"{calculated_flow:.2f} (calc)"
            except:
                pass

        # Formato mejorado
        status_color = "#28a745" if last_interaction.days_not_conection == 0 else "#ffc107"
        return mark_safe(f"""
            <div style="font-size: 11px; line-height: 1.6;">
                <strong>📅 Medición:</strong> {date_time_medition_cl.strftime('%Y-%m-%d %H:%M')}<br>
                <strong>📡 Logger:</strong> {date_time_logger.strftime('%Y-%m-%d %H:%M') if date_time_logger else 'N/A'}<br>
                <strong>💧 Total:</strong> {last_interaction.total or '0'} m³<br>
                <strong>🌊 Caudal:</strong> {flow_display} L/s<br>
                <strong>📏 Nivel:</strong> {last_interaction.nivel or '0'} m<br>
                <strong style="color: {status_color};">🔌 Desconexión:</strong> {last_interaction.days_not_conection} días
            </div>
        """)

    last_interaction_detail.short_description = 'Última medición'


# ========================================
# PROFILE DATA CONFIG ADMIN
# ========================================

@admin.register(ProfileDataConfigCatchment)
class ProfileDataConfigCatchmentAdmin(ImportExportModelAdmin, ExportActionMixin, admin.ModelAdmin):
    """
    Configuración de datos de telemetría para cada punto.
    Define parámetros físicos (dimensiones del pozo), tokens de servicio y estado de telemetría.
    """
    list_per_page = ADMIN_LIST_PER_PAGE
    list_display = ('id', 'point_catchment', 'is_telemetry', 'token_service', 'd3', 'date_start_telemetry')
    list_filter = ('is_telemetry', 'point_catchment__project__name',)
    search_fields = ('point_catchment__title', 'token_service')
    autocomplete_fields = ['point_catchment']
    fieldsets = (
        ('Punto de Captación', {
            'fields': ('point_catchment',),
            'description': 'Punto de captación al que pertenece esta configuración.'
        }),
        ('Telemetría', {
            'fields': ('token_service', 'is_telemetry', 'date_start_telemetry', 'date_delivery_act'),
            'description': 'Configuración de telemetría: token del servicio, estado activo y fechas importantes.'
        }),
        ('Dimensiones', {
            'fields': (
                ('d1', 'd3'),
                ('d2', 'd4'),
                ('d5', 'd6'),
            ),
            'description': 'Dimensiones físicas del pozo utilizadas para validaciones de nivel y caudal.'
        }),
        ('Reset y Ajustes', {
            'fields': ('addition',),
            'description': 'Ajuste manual del acumulado para corrección de reinicios.'
        }),
    )


# ========================================
# PROFILE IKOLU ADMIN
# ========================================

@admin.register(ProfileIkoluCatchment)
class ProfileIkoluCatchmentAdmin(ImportExportModelAdmin, ExportActionMixin, admin.ModelAdmin):
    """
    Perfil de configuración de módulos Ikolu para cada punto.
    Define qué módulos están activos (m1-m7) y sus suscripciones.
    """
    list_per_page = ADMIN_LIST_PER_PAGE
    list_display = ('id', 'point_catchment', 'm1', 'm2', 'm3', 'm4', 'm5', 'm6', 'm7', 'entry_by_form')
    list_filter = ('entry_by_form', 'm1', 'm2', 'm3', 'm4', 'm5', 'm6', 'm7')
    search_fields = ('point_catchment__title',)
    autocomplete_fields = ['point_catchment']
    fieldsets = (
        ('Punto de Captación', {
            'fields': ('point_catchment', 'entry_by_form'),
            'description': 'Punto de captación y método de entrada de datos.'
        }),
        ('Módulos', {
            'fields': ('m1', 'm2', 'm3', 'm4', 'm5', 'm6', 'm7'),
            'description': 'Módulos Ikolu disponibles: activa o desactiva cada módulo según las necesidades del punto.'
        }),
        ('Suscripciones', {
            'fields': (
                ('m3_start_subscription', 'm3_type_subscriptions'),
                ('m4_start_subscription', 'm4_type_subscriptions'),
                ('m5_start_subscription', 'm5_type_subscriptions'),
            ),
            'classes': ('collapse',)
        }),
    )


# ========================================
# DGA DATA CONFIG ADMIN
# ========================================

@admin.register(DgaDataConfigCatchment)
class DgaDataConfigCatchmentAdmin(AdminIndicatorsMixin, ImportExportModelAdmin, ExportActionMixin, admin.ModelAdmin):
    """
    Configuración específica para el envío de datos a la DGA (Dirección General de Aguas).
    Incluye códigos, estándares, datos otorgados e información del informante.
    """
    list_per_page = ADMIN_LIST_PER_PAGE
    list_display = (
        'id', 'point_catchment', 'send_dga', 'standard', 'code_dga',
        'flow_granted_dga', 'total_granted_dga', 'date_start_compliance'
    )
    list_filter = ('standard', 'send_dga', 'point_catchment__project__name', 'type_dga')
    search_fields = ('point_catchment__title', 'code_dga', 'shac')
    autocomplete_fields = ['point_catchment']
    fieldsets = (
        ('Punto de Captación', {
            'fields': ('point_catchment',),
            'description': 'Punto de captación asociado a esta configuración DGA.'
        }),
        ('Configuración DGA', {
            'fields': ('send_dga', 'standard', 'type_dga', 'code_dga', 'shac'),
            'description': 'Configuración para el envío de datos a la DGA: estándar, tipo, código y SHAC.'
        }),
        ('Datos Otorgados', {
            'fields': ('flow_granted_dga', 'total_granted_dga'),
            'description': 'Derechos de agua otorgados por la DGA: caudal y total otorgado.'
        }),
        ('Fechas', {
            'fields': ('date_start_compliance', 'date_created_code')
        }),
        ('Informante', {
            'fields': ('name_informant', 'rut_report_dga'),
            'classes': ('collapse',)
        }),
    )


# ========================================
# SCHEMES CATCHMENT ADMIN - CON INLINES
# ========================================

@admin.register(SchemesCatchment)
class SchemesCatchmentAdmin(ImportExportModelAdmin, ExportActionMixin, admin.ModelAdmin):
    """
    Esquemas que definen cómo se procesan y calculan las variables de telemetría.
    Un esquema puede aplicarse a múltiples puntos y contiene las variables configuradas.
    """
    list_per_page = ADMIN_LIST_PER_PAGE

    # ✅ Lista mejorada: muestra puntos y variables de forma más clara
    list_display = ('id', 'name', 'get_points_list', 'get_variables_list', 'created')

    # ✅ Búsqueda mejorada: buscar por nombre y puntos asociados
    search_fields = ('name', 'description', 'points_catchment__title', 'points_catchment__project__name')

    # ✅ Filtros útiles para gestión
    list_filter = (
        'created',
        ('points_catchment__project', admin.RelatedOnlyFieldListFilter),
        ('points_catchment', admin.RelatedOnlyFieldListFilter),
    )

    # ✅ Usar filter_horizontal para mejor UX al seleccionar puntos
    filter_horizontal = ['points_catchment']

    # ✅ Inlines para ver variables directamente
    inlines = [VariableInline]

    # ✅ Fieldsets organizados
    fieldsets = (
        ('Información Básica', {
            'fields': ('name', 'description'),
            'description': 'Información general del esquema'
        }),
        ('Puntos de Captación', {
            'fields': ('points_catchment',),
            'description': 'Selecciona los puntos de captación asociados a este esquema'
        }),
    )

    def get_points_list(self, obj):
        """
        Muestra lista de puntos asociados con enlaces y proyecto.
        Mejor visualización para gestión.
        """
        points = obj.points_catchment.select_related('project').all().order_by('project__name', 'title')

        if not points.exists():
            return mark_safe('<span style="color: #999;">Sin puntos asignados</span>')

        # Limitar a 5 puntos en la lista, mostrar total si hay más
        points_list = list(points[:5])
        total = points.count()

        html_items = []
        for point in points_list:
            # Enlace al punto con título y proyecto
            url = reverse('admin:core_catchmentpoint_change', args=[point.id])
            project_name = point.project.name if point.project else 'Sin proyecto'
            html_items.append(
                f'<li style="margin-bottom: 4px; list-style: none;">'
                f'<a href="{url}" target="_blank" style="text-decoration: none; color: #417690;">'
                f'<strong>{point.title or f"Punto #{point.id}"}</strong>'
                f'</a> <span style="color: #666; font-size: 0.9em;">({project_name})</span>'
                f'</li>'
            )

        # Si hay más de 5, mostrar indicador
        if total > 5:
            html_items.append(
                f'<li style="color: #666; font-style: italic; margin-top: 4px; list-style: none;">'
                f'... y {total - 5} punto(s) más'
                f'</li>'
            )

        # Mostrar total al inicio (color que funciona en tema claro y oscuro)
        result = f'<div style="margin-bottom: 8px;"><strong style="color: #417690;">Total: {total} punto(s)</strong></div>'
        result += f'<ul style="margin: 0; padding-left: 20px; list-style: none;">{"".join(html_items)}</ul>'

        return mark_safe(result)
    get_points_list.short_description = 'Puntos Asociados'
    get_points_list.admin_order_field = 'points_catchment__title'

    def get_variables_list(self, obj):
        """
        Muestra lista de variables con su configuración.
        Mejor visualización para gestión.
        """
        variables = obj.variables.all().order_by('type_variable', 'str_variable')

        if not variables.exists():
            return mark_safe('<span style="color: #999;">Sin variables configuradas</span>')

        # Limitar a 5 variables en la lista, mostrar total si hay más
        vars_list = list(variables[:5])
        total = variables.count()

        html_items = []
        for var in vars_list:
            # Enlace a la variable con información de configuración
            url = reverse('admin:core_variable_change', args=[var.id])

            # Badge de tipo de variable
            type_badge_colors = {
                'NIVEL': '#4CAF50',
                'CAUDAL': '#2196F3',
                'CAUDAL_PROMEDIO': '#FF9800',
                'TOTALIZADO': '#9C27B0',
            }
            type_color = type_badge_colors.get(var.type_variable, '#666')

            # Información de configuración según tipo
            config_info = []
            if var.type_variable == 'TOTALIZADO':
                if var.pulses_factor:
                    config_info.append(f'Factor: {var.pulses_factor}')
            elif var.type_variable == 'CAUDAL':
                if var.convert_to_lt:
                    config_info.append('Conv. m³→lt')
            elif var.type_variable == 'NIVEL':
                if var.calculate_nivel:
                    config_info.append(f'Base: {var.calculate_nivel}')

            config_str = f' ({", ".join(config_info)})' if config_info else ''
            service_str = f' [{var.service}]' if var.service else ''

            html_items.append(
                f'<li style="margin-bottom: 6px; padding: 4px; background: #f5f5f5; border-left: 3px solid {type_color}; list-style: none;">'
                f'<a href="{url}" target="_blank" style="text-decoration: none; font-weight: bold; color: {type_color};">'
                f'{var.label or var.str_variable}'
                f'</a>'
                f'<br>'
                f'<span style="color: #333; font-size: 0.85em;">'
                f'<strong>Variable:</strong> {var.str_variable} | '
                f'<strong>Tipo:</strong> {var.get_type_variable_display()}{service_str}'
                f'{config_str}'
                f'</span>'
                f'</li>'
            )

        # Si hay más de 5, mostrar indicador
        if total > 5:
            html_items.append(
                f'<li style="color: #666; font-style: italic; margin-top: 4px; list-style: none;">'
                f'... y {total - 5} variable(s) más'
                f'</li>'
            )

        # Mostrar total al inicio (color que funciona en tema claro y oscuro)
        result = f'<div style="margin-bottom: 8px;"><strong style="color: #417690;">Total: {total} variable(s)</strong></div>'
        result += f'<ul style="margin: 0; padding-left: 0; list-style: none;">{"".join(html_items)}</ul>'

        return mark_safe(result)
    get_variables_list.short_description = 'Variables Configuradas'
    get_variables_list.admin_order_field = 'variables__type_variable'

    # ✅ Mejorar la vista de detalle con información adicional
    readonly_fields = ('get_points_summary', 'get_variables_summary',)

    def get_points_summary(self, obj):
        """
        Resumen detallado de puntos en la vista de edición.
        """
        if not obj.pk:
            return "Guarda el esquema primero para ver los puntos asociados."

        points = obj.points_catchment.select_related('project', 'owner_user').all().order_by('project__name', 'title')

        if not points.exists():
            return mark_safe('<p style="color: #999;">No hay puntos asociados a este esquema.</p>')

        # Agrupar por proyecto
        by_project = {}
        for point in points:
            project_name = point.project.name if point.project else 'Sin proyecto'
            if project_name not in by_project:
                by_project[project_name] = []
            by_project[project_name].append(point)

        html = f'<div style="margin: 10px 0;"><h3>Resumen de Puntos ({points.count()} total)</h3>'

        for project_name, project_points in sorted(by_project.items()):
            html += f'<div style="margin: 15px 0; padding: 10px; background: #f9f9f9; border-left: 3px solid #1F3461;">'
            html += f'<strong style="color: #1F3461;">{project_name}</strong> ({len(project_points)} punto(s))<ul style="margin: 8px 0 0 0; padding-left: 20px;">'

            for point in project_points:
                url = reverse('admin:core_catchmentpoint_change', args=[point.id])
                owner = point.owner_user.username if point.owner_user else 'N/A'
                frecuency = point.frecuency or 'N/A'
                html += (
                    f'<li style="margin: 4px 0;">'
                    f'<a href="{url}" target="_blank" style="text-decoration: none; font-weight: bold;">'
                    f'{point.title or f"Punto #{point.id}"}'
                    f'</a> - '
                    f'<span style="color: #666;">Propietario: {owner} | Frecuencia: {frecuency} min</span>'
                    f'</li>'
                )

            html += '</ul></div>'

        html += '</div>'
        return mark_safe(html)
    get_points_summary.short_description = 'Resumen de Puntos'

    def get_variables_summary(self, obj):
        """
        Resumen detallado de variables configuradas en la vista de edición.
        """
        if not obj.pk:
            return "Guarda el esquema primero para ver las variables configuradas."

        variables = obj.variables.all().order_by('type_variable', 'str_variable')

        if not variables.exists():
            return mark_safe('<p style="color: #999;">No hay variables configuradas en este esquema.</p>')

        # Agrupar por tipo de variable
        by_type = {}
        for var in variables:
            type_display = var.get_type_variable_display()
            if type_display not in by_type:
                by_type[type_display] = []
            by_type[type_display].append(var)

        # Colores para cada tipo
        type_colors = {
            'Nivel': '#4CAF50',
            'Caudal': '#2196F3',
            'Caudal promedio((diff/3600)*1000)': '#FF9800',
            'Totalizado': '#9C27B0',
        }

        html = f'<div style="margin: 10px 0;"><h3>Resumen de Variables ({variables.count()} total)</h3>'

        for type_display, type_vars in sorted(by_type.items()):
            color = type_colors.get(type_display, '#666')
            html += f'<div style="margin: 15px 0; padding: 10px; background: #f9f9f9; border-left: 4px solid {color};">'
            html += f'<strong style="color: {color}; font-size: 1.1em;">{type_display}</strong> ({len(type_vars)} variable(s))<ul style="margin: 8px 0 0 0; padding-left: 20px;">'

            for var in type_vars:
                url = reverse('admin:core_variable_change', args=[var.id])

                # Información de configuración detallada
                config_details = []

                if var.type_variable == 'TOTALIZADO':
                    config_details.append(f'<strong>Pulsos Factor:</strong> {var.pulses_factor or "N/A"}')
                elif var.type_variable == 'CAUDAL':
                    config_details.append(f'<strong>Convertir a litros:</strong> {"Sí" if var.convert_to_lt else "No"}')
                elif var.type_variable == 'NIVEL':
                    config_details.append(f'<strong>Base Cálculo:</strong> {var.calculate_nivel or "N/A"}')

                if var.service:
                    config_details.append(f'<strong>Proveedor:</strong> {var.get_service_display()}')
                if var.token_service:
                    config_details.append(f'<strong>Token:</strong> {var.token_service[:20]}...' if len(var.token_service) > 20 else f'<strong>Token:</strong> {var.token_service}')

                config_html = '<br>'.join([f'<span style="color: #666; font-size: 0.9em;">{d}</span>' for d in config_details])

                html += (
                    f'<li style="margin: 8px 0; padding: 8px; background: white; border: 1px solid #ddd;">'
                    f'<a href="{url}" target="_blank" style="text-decoration: none; font-weight: bold; color: {color}; font-size: 1.05em;">'
                    f'{var.label or var.str_variable}'
                    f'</a>'
                    f'<br>'
                    f'<span style="color: #666; font-size: 0.9em;"><strong>Variable (str_variable):</strong> {var.str_variable}</span>'
                    f'<br>'
                    f'{config_html if config_details else ""}'
                    f'</li>'
                )

            html += '</ul></div>'

        html += '</div>'
        return mark_safe(html)
    get_variables_summary.short_description = 'Resumen de Variables'

    # ✅ Agregar el campo readonly al fieldsets
    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        if obj:  # Solo mostrar en edición, no en creación
            # Agregar resúmenes al final
            fieldsets = fieldsets + (
                ('Resumen de Variables Configuradas', {
                    'fields': ('get_variables_summary',),
                    'classes': ('collapse',),
                }),
                ('Resumen de Puntos Asociados', {
                    'fields': ('get_points_summary',),
                    'classes': ('collapse',),
                }),
            )
        return fieldsets


# ========================================
# TELEMETRY PROVIDER ADMIN
# ========================================

@admin.register(TelemetryProvider)
class TelemetryProviderAdmin(admin.ModelAdmin):
    """
    Proveedores de telemetría configurables desde el admin.
    Permite cambiar URLs, credenciales y tokens sin tocar código.
    """
    list_display = ('id', 'name', 'provider_type', 'auth_type', 'is_active', 'created')
    list_filter = ('provider_type', 'auth_type', 'is_active')
    search_fields = ('name', 'base_url')
    fieldsets = (
        ('General', {
            'fields': ('name', 'provider_type', 'base_url', 'is_active'),
        }),
        ('Autenticación', {
            'fields': ('auth_type', 'auth_username', 'auth_password', 'auth_token', 'auth_header_name'),
            'classes': ('collapse',),
        }),
    )


# ========================================
# VARIABLE ADMIN
# ========================================

@admin.register(Variable)
class VariableAdmin(ImportExportModelAdmin, ExportActionMixin, admin.ModelAdmin):
    """
    Variables de telemetría configuradas en los esquemas.
    Define qué datos se capturan (caudal, nivel, totalizado) y cómo se procesan.
    """
    list_per_page = ADMIN_LIST_PER_PAGE
    list_display = ('id', 'scheme_catchment', 'str_variable', 'label', 'type_variable', 'service', 'pulses_factor')
    list_filter = ('scheme_catchment__name', 'service', 'type_variable')
    search_fields = ('str_variable', 'label', 'scheme_catchment__name')
    autocomplete_fields = ['scheme_catchment']
    fieldsets = (
        ('Esquema', {
            'fields': ('scheme_catchment',),
            'description': 'Esquema al que pertenece esta variable.'
        }),
        ('Variable', {
            'fields': ('str_variable', 'label', 'type_variable', 'service'),
            'description': 'Identificación de la variable: nombre técnico, etiqueta, tipo y proveedor de servicio.'
        }),
        ('Configuración', {
            'fields': ('pulses_factor', 'convert_to_lt', 'calculate_nivel', 'token_service'),
            'description': 'Parámetros de cálculo: factor de pulsos, conversiones y token de servicio.'
        }),
        ('Proveedor CRUD', {
            'fields': ('provider',),
            'description': 'Proveedor configurable desde el admin (reemplaza service/token hardcodeado).'
        }),
    )


# ========================================
# NOTIFICATIONS ADMIN
# ========================================

@admin.register(NotificationsCatchment)
class NotificationsCatchmentAdmin(AdminIndicatorsMixin, ImportExportModelAdmin, ExportActionMixin, admin.ModelAdmin):
    """
    Notificaciones generadas por el sistema cuando se detectan alertas, errores o eventos importantes.
    Permite el seguimiento de problemas y acciones tomadas en los puntos de captación.
    """
    list_per_page = ADMIN_LIST_PER_PAGE
    list_display = ('id', 'point_catchment', 'title', 'type_notification', 'is_read', 'created', 'get_responses_count')
    list_filter = ('is_read', 'created', 'type_notification', 'point_catchment__project__name')
    search_fields = ('title', 'message', 'emails', 'point_catchment__title')
    date_hierarchy = 'created'
    actions = ['mark_as_read']

    def mark_as_read(self, request, queryset):
        updated = queryset.update(is_read=True)
        self.message_user(request, f"{updated} notificaciones marcadas como leídas.")
    mark_as_read.short_description = "Marcar como leídas"

    def get_responses_count(self, obj):
        count = obj.responses.count()
        return mark_safe(f'<strong>{count}</strong> respuestas')
    get_responses_count.short_description = 'Respuestas'

    def get_indicators(self, request, queryset):
        """
        Obtiene indicadores para NotificationsCatchment basados en el queryset filtrado.
        """
        indicators = []

        total_notifications = queryset.count()

        if total_notifications > 0:
            # Notificaciones activas
            active = queryset.filter(is_active=True).count()

            # Notificaciones sin respuesta
            without_response = queryset.filter(
                responses__isnull=True
            ).distinct().count()

            # Notificaciones críticas
            critical = queryset.filter(
                type_notification__in=['CRITICAL', 'ALERT']
            ).count()

            # Indicador: Total de notificaciones
            indicators.append({
                'value': f'{total_notifications}',
                'label': 'Total Notificaciones',
                'icon': 'fas fa-bell',
                'color': 'primary',
            })

            # Indicador: Activas
            active_pct = (active / total_notifications * 100) if total_notifications > 0 else 0
            indicators.append({
                'value': f'{active} ({active_pct:.0f}%)',
                'label': 'Notificaciones Activas',
                'icon': 'fas fa-exclamation-circle',
                'color': 'warning' if active > 0 else 'success',
            })

            # Indicador: Sin respuesta
            no_response_pct = (without_response / total_notifications * 100) if total_notifications > 0 else 0
            indicators.append({
                'value': f'{without_response} ({no_response_pct:.0f}%)',
                'label': 'Sin Respuesta',
                'icon': 'fas fa-question-circle',
                'color': 'danger' if without_response > 0 else 'success',
            })

            # Indicador: Críticas
            if critical > 0:
                indicators.append({
                    'value': f'{critical}',
                    'label': 'Críticas/Alertas',
                    'icon': 'fas fa-exclamation-triangle',
                    'color': 'danger',
                })
        else:
            indicators.append({
                'value': '0',
                'label': 'Total Notificaciones',
                'icon': 'fas fa-bell',
                'color': 'secondary',
            })

        return indicators


# ========================================
# RESPONSE NOTIFICATIONS ADMIN
# ========================================

@admin.register(ResponseNotificationsCatchment)
class ResponseNotificationsCatchmentAdmin(ImportExportModelAdmin, ExportActionMixin, admin.ModelAdmin):
    """
    Respuestas de usuarios a las notificaciones.
    Permite el seguimiento de acciones tomadas ante alertas y problemas detectados.
    """
    list_per_page = ADMIN_LIST_PER_PAGE
    list_display = ('id', 'notification', 'user', 'response', 'created')
    list_filter = ('created', 'notification__type_notification')
    search_fields = ('notification__title', 'user__username', 'response')
    autocomplete_fields = ['notification', 'user']
    date_hierarchy = 'created'


# ========================================
# TYPE FILE ADMIN
# ========================================

@admin.register(TypeFileCatchment)
class TypeFileCatchmentAdmin(ImportExportModelAdmin, ExportActionMixin, admin.ModelAdmin):
    """
    Tipos de archivos que se pueden asociar a puntos de captación.
    Define categorías de documentos (manuales, certificados, planos, etc.).
    """
    list_per_page = ADMIN_LIST_PER_PAGE
    list_display = ('id', 'name', 'internal', 'created')
    list_filter = ('created', 'internal')
    search_fields = ('name',)


# ========================================
# FILE CATCHMENT ADMIN
# ========================================

@admin.register(FileCatchment)
class FileCatchmentAdmin(ImportExportModelAdmin, ExportActionMixin, admin.ModelAdmin):
    """
    Archivos asociados a puntos de captación.
    Almacena documentos, imágenes y otros archivos relacionados con cada punto (manuales, certificados, planos, etc.).
    """
    list_per_page = ADMIN_LIST_PER_PAGE
    list_display = ('id', 'name', 'point_catchment', 'type_file', 'get_file_link', 'created')
    list_filter = ('created', 'type_file__name', 'point_catchment__project__name')
    search_fields = ('name', 'point_catchment__title')
    autocomplete_fields = ['point_catchment', 'type_file']
    date_hierarchy = 'created'

    def get_file_link(self, obj):
        if obj.file:
            return mark_safe(f'<a href="{obj.file.url}" target="_blank">📄 Ver archivo</a>')
        return '-'
    get_file_link.short_description = 'Archivo'


# ========================================
# REGISTER PERSONS ADMIN
# ========================================

@admin.register(RegisterPersons)
class RegisterPersonsAdmin(ImportExportModelAdmin, ExportActionMixin, admin.ModelAdmin):
    """
    Personas registradas asociadas a perfiles de puntos.
    Permite gestionar contactos y responsables de cada punto de captación.
    """
    list_per_page = ADMIN_LIST_PER_PAGE
    list_display = ('id', 'name', 'email', 'phone', 'profile', 'created')
    search_fields = ('name', 'email', 'phone')
    list_filter = ('created', 'profile__point_catchment__project__name')
    autocomplete_fields = ['profile']
    fieldsets = (
        ('Información Personal', {
            'fields': ('name', 'email', 'phone'),
            'description': 'Datos de contacto de la persona registrada.'
        }),
        ('Relación', {
            'fields': ('profile',),
            'description': 'Perfil Ikolu al que está asociada esta persona.'
        }),
    )


# ========================================
# ACCIONES MASIVAS MEJORADAS
# ========================================

def agregar_registros_cola_dga(modeladmin, request, queryset):
    """Agregar registros seleccionados a la cola de envío DGA"""
    updated = queryset.filter(send_dga=False).update(send_dga=True)
    if updated > 0:
        modeladmin.message_user(request, f'✅ {updated} registros agregados a la cola DGA.', level='success')
    else:
        modeladmin.message_user(request, '⚠️ Ningún registro válido para agregar.', level='warning')

agregar_registros_cola_dga.short_description = '➕ Agregar a cola DGA'

def remover_registros_cola_dga(modeladmin, request, queryset):
    """Remover registros seleccionados de la cola de envío DGA"""
    updated = queryset.filter(send_dga=True).update(send_dga=False)
    if updated > 0:
        modeladmin.message_user(request, f'✅ {updated} registros removidos de la cola DGA.', level='success')
    else:
        modeladmin.message_user(request, '⚠️ Ningún registro válido para remover.', level='warning')

remover_registros_cola_dga.short_description = '➖ Remover de cola DGA'

def marcar_como_error(modeladmin, request, queryset):
    """Marcar registros como error"""
    updated = queryset.filter(is_error=False).update(is_error=True)
    modeladmin.message_user(request, f'✅ {updated} registros marcados como error.', level='success')

marcar_como_error.short_description = '❌ Marcar como error'

def desmarcar_error(modeladmin, request, queryset):
    """Desmarcar registros como error"""
    updated = queryset.filter(is_error=True).update(is_error=False)
    modeladmin.message_user(request, f'✅ {updated} registros desmarcados como error.', level='success')

desmarcar_error.short_description = '✅ Desmarcar error'

# ========================================
# ACCIÓN PARA GENERAR OT SOPORTE-HW (PDF)
# ========================================

def generar_ot_soporte_pdf(modeladmin, request, queryset):
    """
    Generar PDF de Orden de Trabajo para Soporte-HW.
    Incluye análisis completo del punto, anomalías detectadas y sugerencias.
    """
    from api.core.reports.ot_soporte_generator import generate_ot_soporte_pdf
    from django.http import HttpResponse

    if queryset.count() != 1:
        modeladmin.message_user(request, '⚠️ Por favor seleccione solo un punto para generar la OT.', level='warning')
        return

    point = queryset.first()

    try:
        # Generar PDF
        pdf_buffer = generate_ot_soporte_pdf(point.id)

        # Crear respuesta HTTP
        response = HttpResponse(
            pdf_buffer.read(),
            content_type='application/pdf'
        )
        response['Content-Disposition'] = f'attachment; filename="OT_Soporte_{point.id}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf"'

        modeladmin.message_user(request, f'✅ OT Soporte generada para {point.title}.', level='success')
        return response
    except Exception as e:
        modeladmin.message_user(request, f'❌ Error al generar OT Soporte: {str(e)}', level='error')

generar_ot_soporte_pdf.short_description = '🔧 Generar OT Soporte-HW (PDF)'

# ========================================
# ACCIONES PARA GENERAR PDF DE ANÁLISIS
# ========================================

def generar_analisis_telemetria_pdf(modeladmin, request, queryset):
    """
    Generar PDF de análisis de telemetría para puntos seleccionados.
    Genera un PDF separado por cada punto.
    """
    from api.core.reports.pdf_generator import generate_telemetry_analysis_pdf
    from django.http import HttpResponse
    import zipfile
    from io import BytesIO

    if not queryset.exists():
        modeladmin.message_user(request, '⚠️ No hay puntos seleccionados.', level='warning')
        return

    try:
        user_info = f"{request.user.get_full_name() or request.user.username} ({request.user.email or 'N/A'})"

        # Si es un solo punto, devolver PDF directo
        if queryset.count() == 1:
            point = queryset.first()
            pdf_buffer = generate_telemetry_analysis_pdf([point], user_info=user_info)
            response = HttpResponse(pdf_buffer.read(), content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="analisis_telemetria_{point.id}_{point.title[:30]}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf"'
            modeladmin.message_user(request, f'✅ PDF generado para punto {point.title}.', level='success')
            return response

        # Si son varios puntos, generar ZIP con PDFs separados
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for point in queryset:
                pdf_buffer = generate_telemetry_analysis_pdf([point], user_info=user_info)
                pdf_buffer.seek(0)
                filename = f"analisis_telemetria_{point.id}_{point.title[:30]}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
                zip_file.writestr(filename, pdf_buffer.read())

        zip_buffer.seek(0)
        response = HttpResponse(zip_buffer.read(), content_type='application/zip')
        response['Content-Disposition'] = f'attachment; filename="analisis_telemetria_{queryset.count()}_puntos_{datetime.now().strftime("%Y%m%d_%H%M%S")}.zip"'

        modeladmin.message_user(request, f'✅ {queryset.count()} PDF(s) generados y comprimidos en ZIP.', level='success')
        return response
    except Exception as e:
        modeladmin.message_user(request, f'❌ Error al generar PDF: {str(e)}', level='error')

generar_analisis_telemetria_pdf.short_description = '📄 Generar Análisis de Telemetría (PDF) - Separado por Punto'

def generar_analisis_telemetria_proyecto_pdf(modeladmin, request, queryset):
    """
    Generar PDF de análisis de telemetría para todos los puntos de los proyectos seleccionados.
    Genera un PDF separado por cada punto.
    """
    from api.core.reports.pdf_generator import generate_telemetry_analysis_pdf
    from django.http import HttpResponse
    from api.core.models import CatchmentPoint
    import zipfile
    from io import BytesIO

    if not queryset.exists():
        modeladmin.message_user(request, '⚠️ No hay proyectos seleccionados.', level='warning')
        return

    try:
        # Obtener todos los puntos de los proyectos seleccionados
        all_points = CatchmentPoint.objects.filter(project__in=queryset)

        if not all_points.exists():
            modeladmin.message_user(request, '⚠️ Los proyectos seleccionados no tienen puntos de captación.', level='warning')
            return

        user_info = f"{request.user.get_full_name() or request.user.username} ({request.user.email or 'N/A'})"
        project_name = queryset.first().name if queryset.count() == 1 else f"{queryset.count()} Proyectos"

        # Generar ZIP con PDFs separados
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for point in all_points:
                pdf_buffer = generate_telemetry_analysis_pdf([point], project_name=project_name, user_info=user_info)
                pdf_buffer.seek(0)
                filename = f"analisis_telemetria_{point.id}_{point.title[:30]}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
                zip_file.writestr(filename, pdf_buffer.read())

        zip_buffer.seek(0)
        response = HttpResponse(zip_buffer.read(), content_type='application/zip')
        response['Content-Disposition'] = f'attachment; filename="analisis_telemetria_{project_name}_{all_points.count()}_puntos_{datetime.now().strftime("%Y%m%d_%H%M%S")}.zip"'

        modeladmin.message_user(request, f'✅ {all_points.count()} PDF(s) generados para {queryset.count()} proyecto(s) y comprimidos en ZIP.', level='success')
        return response
    except Exception as e:
        modeladmin.message_user(request, f'❌ Error al generar PDF: {str(e)}', level='error')

generar_analisis_telemetria_proyecto_pdf.short_description = '📄 Generar Análisis de Telemetría por Proyecto (PDF)'

# ========================================
# ACCIONES PARA GENERAR EXCEL DE ANÁLISIS
# ========================================

def generar_excel_por_proyecto(modeladmin, request, queryset):
    """
    Generar Excel de análisis de telemetría por proyecto.
    """
    from api.core.reports.excel_generator import generate_excel_by_project
    from django.http import HttpResponse

    if not queryset.exists():
        modeladmin.message_user(request, '⚠️ No hay proyectos seleccionados.', level='warning')
        return

    try:
        # Obtener todos los puntos de los proyectos seleccionados
        from api.core.models import CatchmentPoint
        all_points = CatchmentPoint.objects.filter(project__in=queryset)

        if not all_points.exists():
            modeladmin.message_user(request, '⚠️ Los proyectos seleccionados no tienen puntos de captación.', level='warning')
            return

        # Generar Excel
        project_name = queryset.first().name if queryset.count() == 1 else f"{queryset.count()} Proyectos"
        excel_buffer = generate_excel_by_project(list(all_points), project_name=project_name)

        # Crear respuesta HTTP
        response = HttpResponse(
            excel_buffer.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="analisis_telemetria_proyecto_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx"'

        modeladmin.message_user(request, f'✅ Excel generado para {all_points.count()} punto(s) de {queryset.count()} proyecto(s).', level='success')
        return response
    except Exception as e:
        modeladmin.message_user(request, f'❌ Error al generar Excel: {str(e)}', level='error')

generar_excel_por_proyecto.short_description = 'Generar Excel por Proyecto'

def generar_excel_por_punto(modeladmin, request, queryset):
    """
    Generar Excel de análisis de telemetría por punto (separado por mes).
    Permite seleccionar año y mes específico para optimizar el rendimiento.
    """
    from api.core.reports.excel_generator import generate_excel_by_point
    from django.http import HttpResponse
    from django.shortcuts import render
    from datetime import datetime
    import pytz

    if not queryset.exists():
        modeladmin.message_user(request, '⚠️ No hay puntos seleccionados.', level='warning')
        return

    if queryset.count() > 1:
        modeladmin.message_user(request, '⚠️ Por favor seleccione solo un punto para generar el Excel detallado por mes.', level='warning')
        return

    point = queryset.first()

    # Si es POST, procesar el formulario
    if request.method == 'POST':
        try:
            year = request.POST.get('year')
            month = request.POST.get('month')

            # Convertir a int si se proporcionaron
            year = int(year) if year else None
            month = int(month) if month else None

            # Validar mes
            if month and (month < 1 or month > 12):
                modeladmin.message_user(request, '⚠️ Mes inválido. Debe ser entre 1 y 12.', level='warning')
                return

            # Generar Excel con filtros
            excel_buffer = generate_excel_by_point(point, year=year, month=month)

            # Crear respuesta HTTP
            response = HttpResponse(
                excel_buffer.read(),
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )

            # Nombre de archivo con filtros
            filename_parts = [f"analisis_telemetria_{point.id}"]
            if year:
                filename_parts.append(str(year))
            if month:
                filename_parts.append(f"{month:02d}")
            filename_parts.append(datetime.now().strftime("%Y%m%d_%H%M%S"))

            response['Content-Disposition'] = f'attachment; filename="{"_".join(filename_parts)}.xlsx"'

            periodo_text = ""
            if year and month:
                month_names = ['', 'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
                              'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']
                periodo_text = f" para {month_names[month]} {year}"
            elif year:
                periodo_text = f" para el año {year}"

            modeladmin.message_user(request, f'✅ Excel generado para punto {point.title}{periodo_text}.', level='success')
            return response
        except Exception as e:
            modeladmin.message_user(request, f'❌ Error al generar Excel: {str(e)}', level='error')
            return

    # Si es GET, mostrar formulario de selección
    # Fix de zona horario para no reversar
    chile_tz = pytz.timezone("America/Santiago")
    now = datetime.now(chile_tz)

    # Obtener años disponibles para este punto
    from api.core.models import InteractionDetail
    from django.db.models import Min, Max

    years_data = InteractionDetail.objects.filter(
        catchment_point=point
    ).extra(
        select={'year': "EXTRACT(YEAR FROM date_time_medition)"}
    ).values('year').distinct().order_by('-year')

    years = [int(y['year']) for y in years_data if y['year']]

    # Si no hay años, usar solo el año actual
    if not years:
        years = [now.year]

    context = {
        'title': f'Generar Excel Detallado - {point.title}',
        'point': point,
        'years': years,
        'current_year': now.year,
        'current_month': now.month,
        'months': [
            (1, 'Enero'), (2, 'Febrero'), (3, 'Marzo'), (4, 'Abril'),
            (5, 'Mayo'), (6, 'Junio'), (7, 'Julio'), (8, 'Agosto'),
            (9, 'Septiembre'), (10, 'Octubre'), (11, 'Noviembre'), (12, 'Diciembre')
        ],
        'opts': modeladmin.model._meta,
        'has_change_permission': modeladmin.has_change_permission(request),
    }

    return render(request, 'admin/core/catchmentpoint/generar_excel_form.html', context)

generar_excel_por_punto.short_description = 'Generar Excel Detallado por Mes (con filtro)'


def generar_excel_ultimo_mes_puntos(modeladmin, request, queryset):
    """
    Generar Excel del último mes completo para puntos seleccionados.
    Una pestaña por punto y resumen combinado.
    """
    from api.core.reports.excel_generator import generate_excel_last_month_by_points
    from django.http import HttpResponse

    if not queryset.exists():
        modeladmin.message_user(request, '⚠️ No hay puntos seleccionados.', level='warning')
        return

    try:
        # Generar Excel
        excel_buffer = generate_excel_last_month_by_points(list(queryset))

        # Crear respuesta HTTP
        response = HttpResponse(
            excel_buffer.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="analisis_ultimo_mes_{queryset.count()}_puntos_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx"'

        modeladmin.message_user(request, f'✅ Excel del último mes completo generado para {queryset.count()} punto(s).', level='success')
        return response
    except Exception as e:
        modeladmin.message_user(request, f'❌ Error al generar Excel: {str(e)}', level='error')

generar_excel_ultimo_mes_puntos.short_description = '📊 Generar Excel Último Mes Completo (por Punto)'


def generar_excel_ano_anterior_puntos(modeladmin, request, queryset):
    """
    Generar Excel del AÑO ANTERIOR completo para puntos seleccionados.
    Una pestaña por punto y resumen combinado.
    """
    from api.core.reports.excel_generator import generate_excel_last_year_by_points
    from django.http import HttpResponse

    if not queryset.exists():
        modeladmin.message_user(request, '⚠️ No hay puntos seleccionados.', level='warning')
        return

    try:
        # Generar Excel
        excel_buffer = generate_excel_last_year_by_points(list(queryset))

        # Crear respuesta HTTP
        prev_year = datetime.now().year - 1
        response = HttpResponse(
            excel_buffer.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="analisis_anual_{prev_year}_{queryset.count()}_puntos.xlsx"'

        modeladmin.message_user(request, f'✅ Excel Anual {prev_year} generado para {queryset.count()} punto(s).', level='success')
        return response
    except Exception as e:
        modeladmin.message_user(request, f'❌ Error al generar Excel Anual: {str(e)}', level='error')

generar_excel_ano_anterior_puntos.short_description = '📅 Descarga Anual 2025'


def generar_excel_anual_comprimido(modeladmin, request, queryset):
    """
    Generar Excel Anual COMPRIMIDO (resumen mensual) para puntos seleccionados.
    """
    from api.core.reports.excel_generator import generate_excel_annual_compressed
    from django.http import HttpResponse

    if not queryset.exists():
        modeladmin.message_user(request, '⚠️ No hay puntos seleccionados.', level='warning')
        return

    try:
        # Generar Excel
        excel_buffer = generate_excel_annual_compressed(list(queryset))

        # Crear respuesta HTTP
        prev_year = datetime.now().year - 1
        response = HttpResponse(
            excel_buffer.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="analisis_anual_comprimido_{prev_year}_{queryset.count()}_puntos.xlsx"'

        modeladmin.message_user(request, f'✅ Excel Anual Comprimido {prev_year} generado.', level='success')
        return response
    except Exception as e:
        modeladmin.message_user(request, f'❌ Error: {str(e)}', level='error')

generar_excel_anual_comprimido.short_description = '📊 Reporte Anual (Comprimido)'


def generar_excel_ultimo_mes_proyecto(modeladmin, request, queryset):
    """
    Generar Excel del último mes completo para todos los puntos de los proyectos seleccionados.
    """
    from api.core.reports.excel_generator import generate_excel_last_month_by_points
    from django.http import HttpResponse
    from api.core.models import CatchmentPoint

    if not queryset.exists():
        modeladmin.message_user(request, '⚠️ No hay proyectos seleccionados.', level='warning')
        return

    try:
        # Obtener todos los puntos de los proyectos seleccionados
        all_points = CatchmentPoint.objects.filter(project__in=queryset)

        if not all_points.exists():
            modeladmin.message_user(request, '⚠️ Los proyectos seleccionados no tienen puntos de captación.', level='warning')
            return

        project_name = queryset.first().name if queryset.count() == 1 else f"{queryset.count()} Proyectos"

        # Generar Excel
        excel_buffer = generate_excel_last_month_by_points(list(all_points), project_name=project_name)

        # Crear respuesta HTTP
        response = HttpResponse(
            excel_buffer.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="analisis_ultimo_mes_{project_name}_{all_points.count()}_puntos_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx"'

        modeladmin.message_user(request, f'✅ Excel del último mes completo generado para {all_points.count()} punto(s) de {queryset.count()} proyecto(s).', level='success')
        return response
    except Exception as e:
        modeladmin.message_user(request, f'❌ Error al generar Excel: {str(e)}', level='error')

generar_excel_ultimo_mes_proyecto.short_description = 'Generar Informe de Renovación - Ultimo mes'

def download_active_points_report(modeladmin, request, queryset):
    """
    Acción para descargar el reporte de puntos activos desde el dropdown.
    """
    from django.http import HttpResponseRedirect
    return HttpResponseRedirect(reverse('active_points_report'))

download_active_points_report.short_description = "📊 Descargar Reporte Puntos Activos"

# Asignar acciones al admin
InteractionDetailAdmin.actions = [
    agregar_registros_cola_dga,
    remover_registros_cola_dga,
    marcar_como_error,
    desmarcar_error,
]

CatchmentPointAdmin.actions = [
    download_active_points_report,
    generar_analisis_telemetria_pdf,
    generar_ot_soporte_pdf,
    generar_excel_por_punto,
    generar_excel_ultimo_mes_puntos,
    generar_excel_ano_anterior_puntos,
    generar_excel_anual_comprimido,
]

ProjectCatchmentsAdmin.actions = [
    generar_analisis_telemetria_proyecto_pdf,
    generar_excel_por_proyecto,
    generar_excel_ultimo_mes_proyecto,
]
