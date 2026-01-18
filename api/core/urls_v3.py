"""
URLs para API Dinámica - Sistema Flexible
"""

from django.urls import path
from .views.v3_views import (
    PointTelemetryDynamicView,
    SystemStatusDynamicView,
)

app_name = 'api_dynamic'

urlpatterns = [
    # Telemetría Dinámica por Punto
    path(
        "telemetry/point/<int:point_id>/",
        PointTelemetryDynamicView.as_view(),
        name="point_telemetry",
    ),
    # Resumen de Salud del Sistema
    path(
        "status/system/",
        SystemStatusDynamicView.as_view(),
        name="system_status",
    ),
]
