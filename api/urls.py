"""URls Core"""
from django.contrib import admin
from django.urls import path, include, re_path

from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView
from api.core.admin_views import (
    telemetry_monitoring_view, telemetry_monitoring_api, admin_dashboard_view,
    telemetry_point_records_api, dga_compliance_report_view
)
from api.core.views.health import health_check, index
from api.core.views.status import status_json, status_dashboard
from api.core.views.reports import ActiveCatchmentPointsReportView
from api.core.views.compliance import DgaComprobanteVerifyView
from api.core.views.docs import DocsPortalView, SalesDocsPortalView, MathContextDocsPortalView


# Configuración del Admin Site con logo SmartHydro
admin.site.site_header = "SmartHydro - Control de Telemetría"
admin.site.site_title = "SmartHydro"
admin.site.index_title = "Panel de Administración"

urlpatterns = [
    # Health check y raíz (sin autenticación, deben ir al inicio)
    path('', index, name='index'),
    path('docs/', DocsPortalView.as_view(), name='docs_portal'),
    path('docs/sales/', SalesDocsPortalView.as_view(), name='sales_docs'),
    path('docs/math/', MathContextDocsPortalView.as_view(), name='math_docs'),
    path('health/', health_check, name='health'),
    path('status/', status_json, name='status_json'),
    path('status/dashboard/', status_dashboard, name='status_dashboard'),

    # Rutas del admin personalizadas (deben ir ANTES de admin.site.urls)
    path('admin/dashboard/', admin_dashboard_view, name='admin_dashboard'),
    path('admin/telemetry-monitoring/', telemetry_monitoring_view, name='telemetry_monitoring'),
    path('admin/telemetry-monitoring/api/', telemetry_monitoring_api, name='telemetry_monitoring_api'),
    path('admin/telemetry-monitoring/api/point/<int:point_id>/records/', telemetry_point_records_api, name='telemetry_point_records_api'),
    path('admin/dga-compliance-report/', dga_compliance_report_view, name='dga_compliance_report'),
    # Admin de Django (debe ir al final para no interceptar las rutas personalizadas)
    path('admin/', admin.site.urls),

    # Reports
    path('reports/active-points/', ActiveCatchmentPointsReportView.as_view(), name='active_points_report'),
    # Compliance
    path('compliance/dga/verify/', DgaComprobanteVerifyView.as_view(), name='dga_comprobante_verify'),
    # API Original (sin cambios)
    path('api/', include(('api.core.router', 'api'), namespace='api')),
    # API Optimizada (nueva, separada)
    path('api/ik/', include(('api.api_ik.routes', 'api_ik'), namespace='api_ik')),
    re_path(r'^media/(?P<path>.*)$', serve,
            {'document_root': settings.MEDIA_ROOT}),
    path('api/password_reset/', include('django_rest_passwordreset.urls', namespace='password_reset')),
    # Chatbot Integration
    path('api/chat-bot/', include('api.core.chatbot.urls')),

    # OpenAPI Schema + Swagger UI + Redoc
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/schema/swagger-ui/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/schema/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

