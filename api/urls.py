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
    # API REST - Django REST Framework Router
    path("api/", include(("api.core.router", "api"), namespace="api")),
    # Presentation Layer (Technical Landing)
    path("presentation/", include("api.presentation.urls")),
    # API V2 - Batch endpoints optimizados
    path("api/v2/", include(("api.core.urls_v2", "api_v2"), namespace="api_v2")),
    re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}),
    path(
        "api/password_reset/",
        include("django_rest_passwordreset.urls", namespace="password_reset"),
    ),
    # CRM - Gestión de Clientes, Proyectos y Tareas
    path("api/crm/", include("api.crm.urls")),
    # Chatbot Integration
    path("api/chat-bot/", include("api.chatbot.urls")),
    # Providers - Sistema dinámico de proveedores de telemetría
    path("api/providers/", include(("api.telemetry.providers.urls", "providers"), namespace="providers")),
    # Telemetry Unified - Nueva API centralizada (V2.1)
    path("api/telemetry/", include("api.telemetry.urls")),
    # Prometheus Metrics
    path("metrics/", prometheus_metrics, name="prometheus-metrics"),
    # Health Check
    path("health/", health_check, name="health_check"),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

if exports:
    urlpatterns += [
        re_path(r"^metrics/?$", exports.ExportToDjangoView, name="prometheus-metrics"),
    ]
