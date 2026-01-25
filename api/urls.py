"""URls Core"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve
try:
    from django_prometheus import exports
except ModuleNotFoundError:
    exports = None

from api.core.views.metrics_view import prometheus_metrics
from api.core.views.health import health_check

# Configuración del Admin Site con logo SmartHydro
admin.site.site_header = "SmartHydro - Control de Telemetría"
admin.site.site_title = "SmartHydro"
admin.site.index_title = "Panel de Administración"

urlpatterns = [
    # Admin de Django
    path("admin/", admin.site.urls),

    # ========================================
    # API UNIFICADA (Principal)
    # ========================================
    # Endpoints: /api/points/, /api/devices/, /api/dashboard/
    path("api/", include(("api.unified.urls", "unified"), namespace="unified")),

    # API Console (Moved to Unified/Dashboard)
    # path("api/console/", include(("api.core.urls_dashboard", "api_dashboard"), namespace="api_dashboard")),
    
    # API Dynamic (Dynamic Engine)
    path("api/dynamic/", include(("api.core.urls_dynamic", "api_dynamic"), namespace="api_dynamic")),

    # ========================================
    # MÓDULOS ESPECIALIZADOS
    # ========================================
    # CRM - Gestión de Clientes, Proyectos y Tareas
    path("api/crm/", include("api.crm.urls")),
    # Compliance
    path('api/compliance/', include('api.compliance.urls')),
    # Chatbot Integration
    path("api/chat-bot/", include("api.chatbot.urls")),
    # Providers - Sistema dinámico de proveedores de telemetría
    path("api/providers/", include(("api.telemetry.providers.urls", "providers"), namespace="providers")),
    # Server-Driven UI Registry
    path("api/registry/", include("api.dynamic_registry.urls")),
    # Document Generation Engine
    path("api/documents/", include("api.documents.urls")),

    # ========================================
    # OTROS
    # ========================================
    # Presentation Layer (Technical Landing)
    path("presentation/", include("api.presentation.urls")),
    # Password Reset
    re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}),
    path(
        "api/password_reset/",
        include("django_rest_passwordreset.urls", namespace="password_reset"),
    ),
    # Prometheus Metrics
    path("metrics/", prometheus_metrics, name="prometheus-metrics"),
    # Health Check
    path("health/", health_check, name="health_check"),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

if exports:
    urlpatterns += [
        re_path(r"^metrics/?$", exports.ExportToDjangoView, name="prometheus-metrics"),
    ]
