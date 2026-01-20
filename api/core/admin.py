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


# ========================================
# ACCIÓN PARA GENERAR OT SOPORTE-HW (PDF)
# ========================================


def generar_ot_soporte_pdf(modeladmin, request, queryset):
    """
    Generar PDF de Orden de Trabajo para Soporte-HW.
    Incluye análisis completo del punto, anomalías detectadas y sugerencias.
    """
    from django.http import HttpResponse

    from api.reports.ot_soporte_generator import generate_ot_soporte_pdf

    if queryset.count() != 1:
        modeladmin.message_user(
            request,
            "⚠️ Por favor seleccione solo un punto para generar la OT.",
            level="warning",
        )
        return

    point = queryset.first()

    try:
        # Generar PDF
        pdf_buffer = generate_ot_soporte_pdf(point.id)

        # Crear respuesta HTTP
        response = HttpResponse(pdf_buffer.read(), content_type="application/pdf")
        response["Content-Disposition"] = (
            f'attachment; filename="OT_Soporte_{point.id}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf"'
        )

        modeladmin.message_user(
            request, f"✅ OT Soporte generada para {point.title}.", level="success"
        )
        return response
    except Exception as e:
        modeladmin.message_user(
            request, f"❌ Error al generar OT Soporte: {str(e)}", level="error"
        )


generar_ot_soporte_pdf.short_description = "🔧 Generar OT Soporte-HW (PDF)"

# ========================================
# ACCIONES PARA GENERAR PDF DE ANÁLISIS
# ========================================


def generar_analisis_telemetria_pdf(modeladmin, request, queryset):
    """
    Generar PDF de análisis de telemetría para puntos seleccionados.
    Genera un PDF separado por cada punto.
    """
    import zipfile
    from io import BytesIO

    from django.http import HttpResponse

    from api.reports.pdf_generator import generate_telemetry_analysis_pdf

    if not queryset.exists():
        modeladmin.message_user(
            request, "⚠️ No hay puntos seleccionados.", level="warning"
        )
        return

    try:
        user_info = f"{request.user.get_full_name() or request.user.username} ({request.user.email or 'N/A'})"

        # Si es un solo punto, devolver PDF directo
        if queryset.count() == 1:
            point = queryset.first()
            pdf_buffer = generate_telemetry_analysis_pdf([point], user_info=user_info)
            response = HttpResponse(pdf_buffer.read(), content_type="application/pdf")
            response["Content-Disposition"] = (
                f'attachment; filename="analisis_telemetria_{point.id}_{point.title[:30]}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf"'
            )
            modeladmin.message_user(
                request, f"✅ PDF generado para punto {point.title}.", level="success"
            )
            return response

        # Si son varios puntos, generar ZIP con PDFs separados
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for point in queryset:
                pdf_buffer = generate_telemetry_analysis_pdf(
                    [point], user_info=user_info
                )
                pdf_buffer.seek(0)
                filename = f"analisis_telemetria_{point.id}_{point.title[:30]}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
                zip_file.writestr(filename, pdf_buffer.read())

        zip_buffer.seek(0)
        response = HttpResponse(zip_buffer.read(), content_type="application/zip")
        response["Content-Disposition"] = (
            f'attachment; filename="analisis_telemetria_{queryset.count()}_puntos_{datetime.now().strftime("%Y%m%d_%H%M%S")}.zip"'
        )

        modeladmin.message_user(
            request,
            f"✅ {queryset.count()} PDF(s) generados y comprimidos en ZIP.",
            level="success",
        )
        return response
    except Exception as e:
        modeladmin.message_user(
            request, f"❌ Error al generar PDF: {str(e)}", level="error"
        )


generar_analisis_telemetria_pdf.short_description = (
    "📄 Generar Análisis de Telemetría (PDF) - Separado por Punto"
)


def generar_analisis_telemetria_proyecto_pdf(modeladmin, request, queryset):
    """
    Generar PDF de análisis de telemetría para todos los puntos de los proyectos seleccionados.
    Genera un PDF separado por cada punto.
    """
    import zipfile
    from io import BytesIO

    from django.http import HttpResponse

    from api.telemetry.models.catchment_points import CatchmentPoint
    from api.core.reports.pdf_generator import generate_telemetry_analysis_pdf

    if not queryset.exists():
        modeladmin.message_user(
            request, "⚠️ No hay proyectos seleccionados.", level="warning"
        )
        return

    try:
        # Obtener todos los puntos de los proyectos seleccionados
        all_points = CatchmentPoint.objects.filter(project__in=queryset)

        if not all_points.exists():
            modeladmin.message_user(
                request,
                "⚠️ Los proyectos seleccionados no tienen puntos de captación.",
                level="warning",
            )
            return

        user_info = f"{request.user.get_full_name() or request.user.username} ({request.user.email or 'N/A'})"
        project_name = (
            queryset.first().name
            if queryset.count() == 1
            else f"{queryset.count()} Proyectos"
        )

        # Generar ZIP con PDFs separados
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for point in all_points:
                pdf_buffer = generate_telemetry_analysis_pdf(
                    [point], project_name=project_name, user_info=user_info
                )
                pdf_buffer.seek(0)
                filename = f"analisis_telemetria_{point.id}_{point.title[:30]}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
                zip_file.writestr(filename, pdf_buffer.read())

        zip_buffer.seek(0)
        response = HttpResponse(zip_buffer.read(), content_type="application/zip")
        response["Content-Disposition"] = (
            f'attachment; filename="analisis_telemetria_{project_name}_{all_points.count()}_puntos_{datetime.now().strftime("%Y%m%d_%H%M%S")}.zip"'
        )

        modeladmin.message_user(
            request,
            f"✅ {all_points.count()} PDF(s) generados para {queryset.count()} proyecto(s) y comprimidos en ZIP.",
            level="success",
        )
        return response
    except Exception as e:
        modeladmin.message_user(
            request, f"❌ Error al generar PDF: {str(e)}", level="error"
        )


generar_analisis_telemetria_proyecto_pdf.short_description = (
    "📄 Generar Análisis de Telemetría por Proyecto (PDF)"
)

# ========================================
# ACCIONES PARA GENERAR EXCEL DE ANÁLISIS
# ========================================


def generar_excel_por_proyecto(modeladmin, request, queryset):
    """
    Generar Excel de análisis de telemetría por proyecto.
    """
    from django.http import HttpResponse

    from api.core.reports.excel_generator import generate_excel_by_project

    if not queryset.exists():
        modeladmin.message_user(
            request, "⚠️ No hay proyectos seleccionados.", level="warning"
        )
        return

    try:
        # Obtener todos los puntos de los proyectos seleccionados
        from api.telemetry.models.catchment_points import CatchmentPoint

        all_points = CatchmentPoint.objects.filter(project__in=queryset)

        if not all_points.exists():
            modeladmin.message_user(
                request,
                "⚠️ Los proyectos seleccionados no tienen puntos de captación.",
                level="warning",
            )
            return

        # Generar Excel
        project_name = (
            queryset.first().name
            if queryset.count() == 1
            else f"{queryset.count()} Proyectos"
        )
        excel_buffer = generate_excel_by_project(
            list(all_points), project_name=project_name
        )

        # Crear respuesta HTTP
        response = HttpResponse(
            excel_buffer.read(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = (
            f'attachment; filename="analisis_telemetria_proyecto_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx"'
        )

        modeladmin.message_user(
            request,
            f"✅ Excel generado para {all_points.count()} punto(s) de {queryset.count()} proyecto(s).",
            level="success",
        )
        return response
    except Exception as e:
        modeladmin.message_user(
            request, f"❌ Error al generar Excel: {str(e)}", level="error"
        )


generar_excel_por_proyecto.short_description = "Generar Excel por Proyecto"


def generar_excel_por_punto(modeladmin, request, queryset):
    """
    Generar Excel de análisis de telemetría por punto (separado por mes).
    Permite seleccionar año y mes específico para optimizar el rendimiento.
    """
    from datetime import datetime

    import pytz
    from django.http import HttpResponse
    from django.shortcuts import render

    from api.core.reports.excel_generator import generate_excel_by_point

    if not queryset.exists():
        modeladmin.message_user(
            request, "⚠️ No hay puntos seleccionados.", level="warning"
        )
        return

    if queryset.count() > 1:
        modeladmin.message_user(
            request,
            "⚠️ Por favor seleccione solo un punto para generar el Excel detallado por mes.",
            level="warning",
        )
        return

    point = queryset.first()

    # Si es POST, procesar el formulario
    if request.method == "POST":
        try:
            year = request.POST.get("year")
            month = request.POST.get("month")

            # Convertir a int si se proporcionaron
            year = int(year) if year else None
            month = int(month) if month else None

            # Validar mes
            if month and (month < 1 or month > 12):
                modeladmin.message_user(
                    request, "⚠️ Mes inválido. Debe ser entre 1 y 12.", level="warning"
                )
                return

            # Generar Excel con filtros
            excel_buffer = generate_excel_by_point(point, year=year, month=month)

            # Crear respuesta HTTP
            response = HttpResponse(
                excel_buffer.read(),
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

            # Nombre de archivo con filtros
            filename_parts = [f"analisis_telemetria_{point.id}"]
            if year:
                filename_parts.append(str(year))
            if month:
                filename_parts.append(f"{month:02d}")
            filename_parts.append(datetime.now().strftime("%Y%m%d_%H%M%S"))

            response["Content-Disposition"] = (
                f'attachment; filename="{"_".join(filename_parts)}.xlsx"'
            )

            periodo_text = ""
            if year and month:
                month_names = [
                    "",
                    "Enero",
                    "Febrero",
                    "Marzo",
                    "Abril",
                    "Mayo",
                    "Junio",
                    "Julio",
                    "Agosto",
                    "Septiembre",
                    "Octubre",
                    "Noviembre",
                    "Diciembre",
                ]
                periodo_text = f" para {month_names[month]} {year}"
            elif year:
                periodo_text = f" para el año {year}"

            modeladmin.message_user(
                request,
                f"✅ Excel generado para punto {point.title}{periodo_text}.",
                level="success",
            )
            return response
        except Exception as e:
            modeladmin.message_user(
                request, f"❌ Error al generar Excel: {str(e)}", level="error"
            )
            return

    # Si es GET, mostrar formulario de selección
    # Fix de zona horario para no reversar
    chile_tz = pytz.timezone("America/Santiago")
    now = datetime.now(chile_tz)

    # Obtener años disponibles para este punto
    from django.db.models import Max, Min

    from api.core.models import TelemetryRecord

    years_data = (
        TelemetryRecord.objects.filter(point=point)
        .extra(select={"year": "EXTRACT(YEAR FROM timestamp)"})
        .values("year")
        .distinct()
        .order_by("-year")
    )

    years = [int(y["year"]) for y in years_data if y["year"]]

    # Si no hay años, usar solo el año actual
    if not years:
        years = [now.year]

    context = {
        "title": f"Generar Excel Detallado - {point.title}",
        "point": point,
        "years": years,
        "current_year": now.year,
        "current_month": now.month,
        "months": [
            (1, "Enero"),
            (2, "Febrero"),
            (3, "Marzo"),
            (4, "Abril"),
            (5, "Mayo"),
            (6, "Junio"),
            (7, "Julio"),
            (8, "Agosto"),
            (9, "Septiembre"),
            (10, "Octubre"),
            (11, "Noviembre"),
            (12, "Diciembre"),
        ],
        "opts": modeladmin.model._meta,
        "has_change_permission": modeladmin.has_change_permission(request),
    }

    return render(request, "admin/core/catchmentpoint/generar_excel_form.html", context)


generar_excel_por_punto.short_description = (
    "Generar Excel Detallado por Mes (con filtro)"
)


def generar_excel_ultimo_mes_puntos(modeladmin, request, queryset):
    """
    Generar Excel del último mes completo para puntos seleccionados.
    Una pestaña por punto y resumen combinado.
    """
    from django.http import HttpResponse

    from api.reports.excel_generator import generate_excel_last_month_by_points

    if not queryset.exists():
        modeladmin.message_user(
            request, "⚠️ No hay puntos seleccionados.", level="warning"
        )
        return

    try:
        # Generar Excel
        excel_buffer = generate_excel_last_month_by_points(list(queryset))

        # Crear respuesta HTTP
        response = HttpResponse(
            excel_buffer.read(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = (
            f'attachment; filename="analisis_ultimo_mes_{queryset.count()}_puntos_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx"'
        )

        modeladmin.message_user(
            request,
            f"✅ Excel del último mes completo generado para {queryset.count()} punto(s).",
            level="success",
        )
        return response
    except Exception as e:
        modeladmin.message_user(
            request, f"❌ Error al generar Excel: {str(e)}", level="error"
        )


generar_excel_ultimo_mes_puntos.short_description = (
    "📊 Generar Excel Último Mes Completo (por Punto)"
)


def generar_excel_ano_anterior_puntos(modeladmin, request, queryset):
    """
    Generar Excel del AÑO ANTERIOR completo para puntos seleccionados.
    Una pestaña por punto y resumen combinado.
    """
    from django.http import HttpResponse

    from api.reports.excel_generator import generate_excel_last_year_by_points

    if not queryset.exists():
        modeladmin.message_user(
            request, "⚠️ No hay puntos seleccionados.", level="warning"
        )
        return

    try:
        # Generar Excel
        excel_buffer = generate_excel_last_year_by_points(list(queryset))

        # Crear respuesta HTTP
        prev_year = datetime.now().year - 1
        response = HttpResponse(
            excel_buffer.read(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = (
            f'attachment; filename="analisis_anual_{prev_year}_{queryset.count()}_puntos.xlsx"'
        )

        modeladmin.message_user(
            request,
            f"✅ Excel Anual {prev_year} generado para {queryset.count()} punto(s).",
            level="success",
        )
        return response
    except Exception as e:
        modeladmin.message_user(
            request, f"❌ Error al generar Excel Anual: {str(e)}", level="error"
        )


generar_excel_ano_anterior_puntos.short_description = "📅 Descarga Anual 2025"


def generar_excel_anual_comprimido(modeladmin, request, queryset):
    """
    Generar Excel Anual COMPRIMIDO (resumen mensual) para puntos seleccionados.
    """
    from django.http import HttpResponse

    from api.core.reports.excel_generator import generate_excel_annual_compressed

    if not queryset.exists():
        modeladmin.message_user(
            request, "⚠️ No hay puntos seleccionados.", level="warning"
        )
        return

    try:
        # Generar Excel
        excel_buffer = generate_excel_annual_compressed(list(queryset))

        # Crear respuesta HTTP
        prev_year = datetime.now().year - 1
        response = HttpResponse(
            excel_buffer.read(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = (
            f'attachment; filename="analisis_anual_comprimido_{prev_year}_{queryset.count()}_puntos.xlsx"'
        )

        modeladmin.message_user(
            request, f"✅ Excel Anual Comprimido {prev_year} generado.", level="success"
        )
        return response
    except Exception as e:
        modeladmin.message_user(request, f"❌ Error: {str(e)}", level="error")


generar_excel_anual_comprimido.short_description = "📊 Reporte Anual (Comprimido)"


def generar_excel_ultimo_mes_proyecto(modeladmin, request, queryset):
    """
    Generar Excel del último mes completo para todos los puntos de los proyectos seleccionados.
    """
    from django.http import HttpResponse

    from api.telemetry.models.catchment_points import CatchmentPoint
    from api.core.reports.excel_generator import generate_excel_last_month_by_points

    if not queryset.exists():
        modeladmin.message_user(
            request, "⚠️ No hay proyectos seleccionados.", level="warning"
        )
        return

    try:
        # Obtener todos los puntos de los proyectos seleccionados
        all_points = CatchmentPoint.objects.filter(project__in=queryset)

        if not all_points.exists():
            modeladmin.message_user(
                request,
                "⚠️ Los proyectos seleccionados no tienen puntos de captación.",
                level="warning",
            )
            return

        project_name = (
            queryset.first().name
            if queryset.count() == 1
            else f"{queryset.count()} Proyectos"
        )

        # Generar Excel
        excel_buffer = generate_excel_last_month_by_points(
            list(all_points), project_name=project_name
        )

        # Crear respuesta HTTP
        response = HttpResponse(
            excel_buffer.read(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = (
            f'attachment; filename="analisis_ultimo_mes_{project_name}_{all_points.count()}_puntos_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx"'
        )

        modeladmin.message_user(
            request,
            f"✅ Excel del último mes completo generado para {all_points.count()} punto(s) de {queryset.count()} proyecto(s).",
            level="success",
        )
        return response
    except Exception as e:
        modeladmin.message_user(
            request, f"❌ Error al generar Excel: {str(e)}", level="error"
        )


generar_excel_ultimo_mes_proyecto.short_description = (
    "Generar Informe de Renovación - Ultimo mes"
)


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


# Asignar acciones al admin
CatchmentPointAdmin.actions = [
    generar_analisis_telemetria_pdf,
    generar_ot_soporte_pdf,
    generar_excel_por_punto,
    generar_excel_ultimo_mes_puntos,
    generar_excel_ano_anterior_puntos,
    generar_excel_anual_comprimido,
]

# Project Actions MOVED TO CRM APP
