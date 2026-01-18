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

from api.core.admin_views import (
    admin_dashboard_view,
    telemetry_monitoring_api,
    telemetry_monitoring_view,
    telemetry_point_records_api,
)
from api.core.views.metrics_view import prometheus_metrics

# Configuración del Admin Site con logo SmartHydro
admin.site.site_header = "SmartHydro - Control de Telemetría"
admin.site.site_title = "SmartHydro"
admin.site.index_title = "Panel de Administración"

urlpatterns = [
    # Rutas del admin personalizadas (deben ir ANTES de admin.site.urls)
    path("admin/dashboard/", admin_dashboard_view, name="admin_dashboard"),
    path(
        "admin/telemetry-monitoring/",
        telemetry_monitoring_view,
        name="telemetry_monitoring",
    ),
    path(
        "admin/telemetry-monitoring/api/",
        telemetry_monitoring_api,
        name="telemetry_monitoring_api",
    ),
    path(
        "admin/telemetry-monitoring/api/point/<int:point_id>/records/",
        telemetry_point_records_api,
        name="telemetry_point_records_api",
    ),
    # Admin de Django (debe ir al final para no interceptar las rutas personalizadas)
    path("admin/", admin.site.urls),
    # API REST - Django REST Framework Router
    path("api/", include(("api.core.router", "api"), namespace="api")),
    # API V2 - Batch endpoints optimizados
    path("api/v2/", include(("api.core.urls_v2", "api_v2"), namespace="api_v2")),
    re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}),
    path(
        "api/password_reset/",
        include("django_rest_passwordreset.urls", namespace="password_reset"),
    ),
    # Chatbot Integration
    path("api/chat-bot/", include("api.chatbot.urls")),
    # Prometheus Metrics
    path("metrics/", prometheus_metrics, name="prometheus-metrics"),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

if exports:
    urlpatterns += [
        re_path(r"^metrics/?$", exports.ExportToDjangoView, name="prometheus-metrics"),
    ]
