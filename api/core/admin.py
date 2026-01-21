from datetime import datetime, timedelta

import pytz

# Django
from django.contrib import admin
from django.db.models import Avg, Count, F
from django.db.models import Max
from django.db.models import Max as MaxFunc
from django.db.models import Min, Q, Sum
from django.db.models.functions import TruncDate, TruncHour, TruncMonth
from django.urls import reverse
from django.utils import timezone

# Models
from django.utils.safestring import mark_safe
from import_export.admin import ExportActionMixin, ImportExportModelAdmin

from api.telemetry.models.catchment_points import (
    CatchmentPoint,
    ProfileDataConfigCatchment,
    ProfileIkoluCatchment,
)
from api.notifications.models import Notification, NotificationResponse
from api.notifications.models import Notification, NotificationResponse
from api.notifications.models import Notification, NotificationResponse
from api.telemetry.models.telemetry import (
    CoreVariable,
    SchemeVariable,
    TelemetryRecord,
    TelemetryScheme,
    VirtualVariable,
)
from api.telemetry.models.configuration import (
    ConfigurationScheme,
    SamplingFrequency,
    VariableType,
)
from api.telemetry.providers.models import CatchmentPointProvider
from api.core.models import User

# ========================================
# CONFIGURACIÓN GLOBAL DE ADMIN Y MENÚ
# ========================================

# Configurar títulos del admin
admin.site.site_header = "SmartHydro - Panel de Control"
admin.site.site_title = "SmartHydro Admin"
admin.site.index_title = "Panel de Administración"

# Configuración global de admin
# (La organización del menú se gestiona en settings.py via JAZZMIN_SETTINGS)

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
        if hasattr(response, "status_code"):
            return response

        # Obtener el queryset del contexto
        if hasattr(response, "context_data"):
            cl = response.context_data.get("cl")
            if cl:
                queryset = cl.queryset
                # Obtener indicadores
                indicators = self.get_indicators(request, queryset)
                response.context_data["indicators"] = indicators

                # Agregar datos para gráficos si el admin los necesita
                if hasattr(self, "get_charts_data"):
                    import json

                    charts_data = self.get_charts_data(request, queryset)
                    # Convertir a JSON para el template
                    response.context_data["charts_data"] = json.dumps(charts_data)

        return response


# ========================================
# INLINES - Ver relaciones en la misma página
# ========================================


class VariableInline(admin.TabularInline):
    """Inline para ver y editar variables dinámicas de un punto"""

    model = CoreVariable
    extra = 1
    fields = (
        "name",
        "internal_code",
        "type_variable",
        "unit",
        "provider_key",
        "scale_factor",
        "offset",
        "is_active",
    )


class SchemeVariableInline(admin.TabularInline):
    """Variables dentro de un esquema"""

    model = SchemeVariable
    extra = 1
    fields = (
        "name",
        "internal_code",
        "type_variable",
        "unit",
        "provider_key",
        "scale_factor",
        "offset",
        "is_active",
    )


class VirtualVariableInline(admin.TabularInline):
    """Variables virtuales dentro de un esquema"""

    model = VirtualVariable
    extra = 1
    fields = ("name", "internal_code", "unit", "operation", "sources", "is_active")


@admin.register(TelemetryScheme)
class TelemetrySchemeAdmin(ImportExportModelAdmin, ExportActionMixin, admin.ModelAdmin):
    """
    Administración de Esquemas de Telemetría.
    Permite definir plantillas reutilizables para múltiples puntos.
    """

    list_display = ("id", "name", "description", "get_points_count")
    search_fields = ("name", "description")
    inlines = [SchemeVariableInline, VirtualVariableInline]

    def get_points_count(self, obj):
        count = obj.catchment_points.count()
        return mark_safe(f"<strong>{count}</strong> puntos")

    get_points_count.short_description = "Puntos Vinculados"


@admin.register(CoreVariable)
class VariableAdmin(ImportExportModelAdmin, ExportActionMixin, admin.ModelAdmin):
    """
    Gestión independiente de variables de telemetría.
    Permite configurar cómo se extraen y escalan los datos de cada sensor.
    """

    list_display = (
        "id",
        "name",
        "point",
        "type_definition",
        "type_variable",
        "internal_code",
        "unit",
        "is_active",
    )
    list_filter = ("is_active", "type_definition", "unit", "point__project__name")
    search_fields = ("name", "internal_code", "type_variable", "point__title")
    autocomplete_fields = ["point", "type_definition"]
    list_per_page = ADMIN_LIST_PER_PAGE
    ordering = ("point", "name")
    
    fieldsets = (
        ("Información Básica", {
            "fields": ("point", "name", "internal_code", "unit")
        }),
        ("Tipo y Procesamiento", {
            "fields": ("type_definition", "type_variable", "operation", "formula")
        }),
        ("Configuración de Ingesta", {
            "fields": ("provider_key", "scale_factor", "offset", "sources", "priority")
        }),
        ("Validación", {
            "fields": ("min_value", "max_value", "configuration")
        }),
        ("Estado", {
            "fields": ("is_virtual", "is_active")
        }),
    )


class ProfileDataConfigInline(admin.StackedInline):
    """Inline para configuración de datos del punto"""

    model = ProfileDataConfigCatchment
    extra = 0
    fieldsets = (
        (
            None,
            {
                "fields": (
                    ("d1", "d3"),
                    ("d2", "d4"),
                    ("d5", "d6"),
                )
            },
        ),
        (
            "Reset y Ajustes",
            {
                "fields": ("addition",),
                "description": "Ajuste manual del acumulado para corrección de reinicios.",
            },
        ),
        (
            "Configuración Telemetría",
            {
                "fields": ("is_telemetry", "date_start_telemetry", "date_delivery_act"),
                "classes": ("collapse",),
            },
        ),
    )




class ProfileIkoluInline(admin.StackedInline):
    """Inline para perfil Ikolu del punto"""

    model = ProfileIkoluCatchment
    extra = 0
    fieldsets = (
        (
            "Módulos",
            {"fields": ("m1", "m2", "m3", "m4", "m5", "m6", "m7", "entry_by_form")},
        ),
        (
            "Suscripciones",
            {
                "fields": (
                    ("m3_start_subscription", "m3_type_subscriptions"),
                    ("m4_start_subscription", "m4_type_subscriptions"),
                    ("m5_start_subscription", "m5_type_subscriptions"),
                ),
                "classes": ("collapse",),
            },
        ),
    )


class ProviderInline(admin.TabularInline):
    """Inline para ver/agregar proveedores de telemetría conectados al punto"""
    model = CatchmentPointProvider
    extra = 1
    fields = ('provider', 'point_code', 'is_active', 'config_override')
    autocomplete_fields = ('provider',)
    verbose_name = "Proveedor de Telemetría"
    verbose_name_plural = "Proveedores de Telemetría"


class PointConfigurationValueInline(admin.TabularInline):
    """Inline para valores de configuración dinámica del punto"""
    from api.telemetry.models.configuration import PointConfigurationValue
    
    model = PointConfigurationValue
    extra = 0
    fields = ('field', 'value')
    readonly_fields = ('field',)
    verbose_name = "Configuración"
    verbose_name_plural = "Configuraciones del Punto"
    can_delete = False
    
    def has_add_permission(self, request, obj=None):
        """Los valores se crean automáticamente desde el esquema."""
        return False
    
    def has_delete_permission(self, request, obj=None):
        """No permitir eliminar directamente."""
        return False


# ========================================
# FILTROS PARA CATCHMENT POINT
# ========================================


class HasDisconnectionFilter(admin.SimpleListFilter):
    title = "Días de desconexión"
    parameter_name = "disconnection_days"

    def lookups(self, request, model_admin):
        return (
            ("disconnected", "Puntos sin conexión"),
            ("connected", "Puntos conectados"),
        )

    def queryset(self, request, queryset):
        if self.value() == "disconnected":
            disconnected_points = (
                TelemetryRecord.objects.filter(point__in=queryset, is_error=True)
                .values_list("point_id", flat=True)
                .distinct()
            )
            return queryset.filter(id__in=disconnected_points)
        if self.value() == "connected":
            recent_limit = timezone.now() - timedelta(days=2)
            connected_points = (
                TelemetryRecord.objects.filter(
                    point__in=queryset, timestamp__gte=recent_limit, is_error=False
                )
                .values_list("point_id", flat=True)
                .distinct()
            )
            return queryset.filter(id__in=connected_points)
        return queryset


class TelemetryStatusFilter(admin.SimpleListFilter):
    title = "Estado Telemetría"
    parameter_name = "telemetry_status"

    def lookups(self, request, model_admin):
        return (
            ("active", "Activa"),
            ("inactive", "Inactiva"),
        )

    def queryset(self, request, queryset):
        if self.value() == "active":
            return queryset.filter(data_config_profiles__is_telemetry=True).distinct()
        if self.value() == "inactive":
            return queryset.exclude(data_config_profiles__is_telemetry=True).distinct()
        return queryset


# ========================================
# USER ADMIN
# ========================================

from django.contrib.auth.admin import UserAdmin


class UserAdm(ExportActionMixin, UserAdmin):
    """
    Usuarios del sistema con acceso al panel de administración.
    Define permisos y roles para gestionar la plataforma de telemetría.
    """

    list_display = (
        "username",
        "email",
        "first_name",
        "last_name",
        "is_staff",
        "is_active",
        "date_joined",
    )
    search_fields = ("username", "email", "first_name", "last_name")
    list_filter = ("is_staff", "is_active", "is_superuser", "date_joined")
    ordering = ("-date_joined",)

    # Fieldsets para el formulario de edición
    fieldsets = (
        (
            "Información Básica",
            {
                "fields": ("username", "password"),
                "description": "Credenciales de acceso del usuario.",
            },
        ),
        (
            "Información Personal",
            {
                "fields": ("first_name", "last_name", "email"),
                "description": "Datos personales y de contacto del usuario.",
            },
        ),
        (
            "Permisos",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                ),
                "description": "Control de acceso y permisos del usuario en el sistema.",
            },
        ),
        (
            "Fechas Importantes",
            {
                "fields": ("last_login", "date_joined"),
                "classes": ("collapse",),
                "description": "Información de registro y última sesión.",
            },
        ),
    )

    # Fieldsets para el formulario de creación
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("username", "password1", "password2"),
            },
        ),
        (
            "Información Personal",
            {
                "fields": ("first_name", "last_name", "email"),
            },
        ),
        (
            "Permisos",
            {
                "fields": ("is_staff", "is_active", "is_superuser"),
            },
        ),
    )

    readonly_fields = ("last_login", "date_joined")


admin.site.register(User, UserAdm)


# ========================================
# FILTROS PARA CATCHMENT POINT
# ========================================


# PROJECT ADMIN REMOVED - MOVED TO CRM APP


# ========================================
# CATCHMENT POINT ADMIN - MEJORADO
# ========================================


@admin.register(CatchmentPoint)
class CatchmentPointAdmin(
    AdminIndicatorsMixin, ImportExportModelAdmin, ExportActionMixin, admin.ModelAdmin
):
    """
    Puntos de captación de agua donde se instalan los sensores de telemetría.
    Cada punto pertenece a un proyecto y puede tener múltiples configuraciones (datos, DGA, Ikolu).
    """

    list_display = (
        "id",
        "title",
        "project",
        "owner_user",
        "frequency",
        "configuration_scheme",
        "get_telemetry_status",
        "last_interaction_detail",
    )
    list_per_page = ADMIN_LIST_PER_PAGE

    def changelist_view(self, request, extra_context=None):
        """Agregar enlace a monitoreo en tiempo real"""
        extra_context = extra_context or {}
        extra_context["monitoring_link"] = reverse("telemetry_monitoring")
        return super().changelist_view(request, extra_context)

    # ✅ Fieldsets para organizar
    fieldsets = (
        (
            "Información Básica",
            {
                "fields": (
                    "title",
                    "project",
                    "owner_user",
                    "frequency",
                    "configuration_scheme",
                    "processing_scheme",
                ),
                "description": "Datos principales del punto: nombre, proyecto asociado, propietario, frecuencia dinámica, esquema de configuración y esquema de procesamiento.",
            },
        ),
        ("Ubicación", {"fields": ("lat", "lon"), "classes": ("collapse",)}),
        ("Usuarios", {"fields": ("users_viewers",), "classes": ("collapse",)}),
        ("Legacy", {"fields": ("frecuency",), "classes": ("collapse",), "description": "Campo legacy - usar 'frequency' en su lugar"}),
    )

    # ✅ Inlines para ver configuraciones relacionadas
    inlines = [
        PointConfigurationValueInline,
        VariableInline,
        ProfileDataConfigInline,
        ProfileIkoluInline,
        ProviderInline,
    ]

    # ✅ Agregar Compliance Inline si está disponible (Sistema Dinámico V3)
    try:
        from api.telemetry.admin import ComplianceConfigInline
        inlines.append(ComplianceConfigInline)
    except ImportError:
        pass  # No disponible aún

    # ✅ Autocomplete
    autocomplete_fields = ["project", "owner_user", "users_viewers", "frequency", "configuration_scheme"]
    filter_horizontal = ["users_viewers"]

    # ✅ Búsqueda mejorada
    search_fields = (
        "title",
        "project__name",
        "project__client__name",
        "owner_user__username",
    )

    # ✅ Filtros mejorados
    list_filter = (
        HasDisconnectionFilter,
        "frequency",
        "configuration_scheme",
        "project__name",
        ("project__client", admin.RelatedOnlyFieldListFilter),
        TelemetryStatusFilter,
    )

    def get_telemetry_status(self, obj):
        """Estado de telemetría"""
        profile = obj.data_config_profiles.filter(is_telemetry=True).first()
        if profile:
            return mark_safe('<span style="color: #28a745;">● Activa</span>')
        return mark_safe('<span style="color: #6c757d;">○ Inactiva</span>')

    get_telemetry_status.short_description = "Telemetría"

    def last_interaction_detail(self, obj):
        """Última medición con mejor formato (V3)"""
        last_record = (
            TelemetryRecord.objects.filter(point=obj).order_by("-timestamp").first()
        )

        if not last_record:
            return mark_safe('<span style="color: #6c757d;">Sin datos</span>')

        chile = pytz.timezone("America/Santiago")
        timestamp_cl = last_record.timestamp.astimezone(chile)

        data = last_record.data

        # Intentar obtener variables comunes
        flow = data.get("flow", data.get("caudal", 0))
        total = data.get("total", data.get("totalizado", 0))
        nivel = data.get("nivel", 0)

        # Formato mejorado
        return mark_safe(
            f"""
            <div style="font-size: 11px; line-height: 1.6;">
                <strong>📅 Medición:</strong> {timestamp_cl.strftime('%Y-%m-%d %H:%M')}<br>
                <strong>💧 Total:</strong> {total} m³<br>
                <strong>🌊 Caudal:</strong> {flow} L/s<br>
                <strong>📏 Nivel:</strong> {nivel} m<br>
            </div>
        """
        )

    last_interaction_detail.short_description = "Última medición"


# ========================================
# PROFILE DATA CONFIG ADMIN
# ========================================


@admin.register(ProfileDataConfigCatchment)
class ProfileDataConfigCatchmentAdmin(
    ImportExportModelAdmin, ExportActionMixin, admin.ModelAdmin
):
    """
    Configuración de datos de telemetría para cada punto.
    Define parámetros físicos (dimensiones del pozo), tokens de servicio y estado de telemetría.
    """

    list_per_page = ADMIN_LIST_PER_PAGE
    list_display = (
        "id",
        "point_catchment",
        "is_telemetry",
        "d3",
        "date_start_telemetry",
    )
    list_filter = (
        "is_telemetry",
        "point_catchment__project__name",
    )
    search_fields = ("point_catchment__title",)
    autocomplete_fields = ["point_catchment"]
    fieldsets = (
        (
            "Punto de Captación",
            {
                "fields": ("point_catchment",),
                "description": "Punto de captación al que pertenece esta configuración.",
            },
        ),
        (
            "Telemetría",
            {
                "fields": (
                    "is_telemetry",
                    "date_start_telemetry",
                    "date_delivery_act",
                ),
                "description": "Configuración de telemetría: estado activo y fechas importantes.",
            },
        ),
        (
            "Dimensiones",
            {
                "fields": (
                    ("d1", "d3"),
                    ("d2", "d4"),
                    ("d5", "d6"),
                ),
                "description": "Dimensiones físicas del pozo utilizadas para validaciones de nivel y caudal.",
            },
        ),
        (
            "Reset y Ajustes",
            {
                "fields": ("addition",),
                "description": "Ajuste manual del acumulado para corrección de reinicios.",
            },
        ),
    )


# ========================================
# PROFILE IKOLU ADMIN
# ========================================


@admin.register(ProfileIkoluCatchment)
class ProfileIkoluCatchmentAdmin(
    ImportExportModelAdmin, ExportActionMixin, admin.ModelAdmin
):
    """
    Perfil de configuración de módulos Ikolu para cada punto.
    Define qué módulos están activos (m1-m7) y sus suscripciones.
    """

    list_per_page = ADMIN_LIST_PER_PAGE
    list_display = (
        "id",
        "point_catchment",
        "m1",
        "m2",
        "m3",
        "m4",
        "m5",
        "m6",
        "m7",
        "entry_by_form",
    )
    list_filter = ("entry_by_form", "m1", "m2", "m3", "m4", "m5", "m6", "m7")
    search_fields = ("point_catchment__title",)
    autocomplete_fields = ["point_catchment"]
    fieldsets = (
        (
            "Punto de Captación",
            {
                "fields": ("point_catchment", "entry_by_form"),
                "description": "Punto de captación y método de entrada de datos.",
            },
        ),
        (
            "Módulos",
            {
                "fields": ("m1", "m2", "m3", "m4", "m5", "m6", "m7"),
                "description": "Módulos Ikolu disponibles: activa o desactiva cada módulo según las necesidades del punto.",
            },
        ),
        (
            "Suscripciones",
            {
                "fields": (
                    ("m3_start_subscription", "m3_type_subscriptions"),
                    ("m4_start_subscription", "m4_type_subscriptions"),
                    ("m5_start_subscription", "m5_type_subscriptions"),
                ),
                "classes": ("collapse",),
            },
        ),
    )




# ========================================
# NOTIFICATIONS ADMIN
# ========================================


@admin.register(Notification)
class NotificationAdmin(
    AdminIndicatorsMixin, ImportExportModelAdmin, ExportActionMixin, admin.ModelAdmin
):
    """
    Notificaciones generadas por el sistema cuando se detectan alertas, errores o eventos importantes.
    Permite el seguimiento de problemas y acciones tomadas en los puntos de captación.
    """

    list_per_page = ADMIN_LIST_PER_PAGE
    list_display = (
        "id",
        "point_catchment",
        "title",
        "type_notification",
        "created",
        "get_responses_count",
    )
    list_filter = ("created", "type_notification", "point_catchment__project__name")
    search_fields = ("title", "message", "point_catchment__title")
    autocomplete_fields = ["point_catchment"]
    date_hierarchy = "created"

    def get_responses_count(self, obj):
        count = obj.responses_list.count()
        return mark_safe(f"<strong>{count}</strong> respuestas")

    get_responses_count.short_description = "Respuestas"

    def get_indicators(self, request, queryset):
        """
        Obtiene indicadores para Notification basados en el queryset filtrado.
        """
        indicators = []

        total_notifications = queryset.count()

        if total_notifications > 0:
            # Notificaciones activas
            active = queryset.filter(is_active=True).count()

            # Notificaciones sin respuesta
            without_response = (
                queryset.filter(responses_list__isnull=True).distinct().count()
            )

            # Notificaciones críticas
            critical = queryset.filter(
                type_notification__in=["CRITICAL", "ALERT"]
            ).count()

            # Indicador: Total de notificaciones
            indicators.append(
                {
                    "value": f"{total_notifications}",
                    "label": "Total Notificaciones",
                    "icon": "fas fa-bell",
                    "color": "primary",
                }
            )

            # Indicador: Activas
            active_pct = (
                (active / total_notifications * 100) if total_notifications > 0 else 0
            )
            indicators.append(
                {
                    "value": f"{active} ({active_pct:.0f}%)",
                    "label": "Notificaciones Activas",
                    "icon": "fas fa-exclamation-circle",
                    "color": "warning" if active > 0 else "success",
                }
            )

            # Indicador: Sin respuesta
            no_response_pct = (
                (without_response / total_notifications * 100)
                if total_notifications > 0
                else 0
            )
            indicators.append(
                {
                    "value": f"{without_response} ({no_response_pct:.0f}%)",
                    "label": "Sin Respuesta",
                    "icon": "fas fa-question-circle",
                    "color": "danger" if without_response > 0 else "success",
                }
            )

            # Indicador: Críticas
            if critical > 0:
                indicators.append(
                    {
                        "value": f"{critical}",
                        "label": "Críticas/Alertas",
                        "icon": "fas fa-exclamation-triangle",
                        "color": "danger",
                    }
                )
        else:
            indicators.append(
                {
                    "value": "0",
                    "label": "Total Notificaciones",
                    "icon": "fas fa-bell",
                    "color": "secondary",
                }
            )

        return indicators


# ========================================
# RESPONSE NOTIFICATIONS ADMIN
# ========================================


@admin.register(NotificationResponse)
class NotificationResponseAdmin(
    ImportExportModelAdmin, ExportActionMixin, admin.ModelAdmin
):
    """
    Respuestas de usuarios a las notificaciones.
    """

    list_per_page = ADMIN_LIST_PER_PAGE
    list_display = ("id", "notification", "user", "response", "created")
    list_filter = ("created", "notification__type_notification")
    search_fields = ("notification__title", "user__username", "response")
    autocomplete_fields = ["notification", "user"]
    date_hierarchy = "created"


# ========================================
# USER ADMIN
# ========================================
# PersonAdmin MOVED TO CRM APP



@admin.register(TelemetryRecord)
class TelemetryRecordAdmin(admin.ModelAdmin):
    """
    Registros de telemetría dinámica V3.
    Almacena los datos en formato JSON permitiendo cualquier número de variables.
    """

    list_display = (
        "point",
        "timestamp",
        "get_flow",
        "get_total",
        "get_compliance_status_icons",
        "is_error",
        "is_partial",
    )
    list_filter = (
        "is_error",
        "is_partial",
        "point__project",
        "point",
        "timestamp",
    )
    date_hierarchy = "timestamp"
    search_fields = ("point__title",)
    list_per_page = ADMIN_LIST_PER_PAGE
    readonly_fields = ("data", "metadata", "timestamp", "point")

    def get_flow(self, obj):
        # Fallback sequence: caudal -> 5001 -> flow
        return obj.data.get("caudal", obj.data.get("5001", obj.data.get("flow", "-")))

    get_flow.short_description = "Caudal (L/s)"

    def get_total(self, obj):
        # Fallback sequence: total -> 5000
        return obj.data.get("total", obj.data.get("5000", "-"))

    get_total.short_description = "Total (m³)"

    def get_compliance_status_icons(self, obj):
        from django.utils.html import format_html
        if not obj.compliance_status:
            return "-"
        
        lines = []
        for provider, status in obj.compliance_status.items():
            icon = "✅" if status.get("sent") else "❌"
            voucher = status.get("voucher", "")
            text = f"{provider.upper()}: {icon}"
            if voucher:
                text += f" ({voucher})"
            lines.append(text)
        
        return format_html("<br>".join(lines))

    get_compliance_status_icons.short_description = "Compliance"


# Project Actions MOVED TO CRM APP
