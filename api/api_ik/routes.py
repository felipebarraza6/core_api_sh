"""
API IK Routes - Optimized Endpoints
====================================

Estos endpoints son NUEVOS y no afectan la API original.
Acceso: /api/ik/

Endpoints disponibles:
- POST /api/ik/batch/telemetry/     - Telemetría multi-punto
- POST /api/ik/batch/stats/         - Stats agregados
- POST /api/ik/login/               - Login optimizado (menos datos)
- GET  /api/ik/points_summary/      - Resumen de puntos del usuario + última telemetría
- GET  /api/ik/point/<id>/summary/  - Resumen de un punto específico
"""

from django.urls import path
from api.core.views.batch_views import BatchTelemetryView, BatchStatsView
from .views import (
    OptimizedLoginView, PointsSummaryView, PointSummaryView, MyPointsView,
    DashboardStatsView, PointCalendarView, PublicAnnouncementsView,
    PointVariablesView,
)

try:
    from django_rest_passwordreset.views import (
        ResetPasswordRequestToken,
        ResetPasswordConfirm,
        ResetPasswordValidateToken,
    )
    HAS_PASSWORD_RESET = True
except ImportError:
    HAS_PASSWORD_RESET = False

app_name = 'api_ik'

urlpatterns = [
    # Batch endpoints
    path('batch/telemetry/', BatchTelemetryView.as_view(), name='batch_telemetry'),
    path('batch/stats/', BatchStatsView.as_view(), name='batch_stats'),

    # Optimized login (menos datos que el original)
    path('login/', OptimizedLoginView.as_view(), name='login'),

    # Points summary (reemplaza get_profile para Centro de Control)
    path('points_summary/', PointsSummaryView.as_view(), name='points_summary'),
    path('point/<int:point_id>/summary/', PointSummaryView.as_view(), name='point_summary'),

    # My points (select/dropdown liviano)
    path('my_points/', MyPointsView.as_view(), name='my_points'),

    # Dashboard stats (KPIs del Centro de Control)
    path('dashboard_stats/', DashboardStatsView.as_view(), name='dashboard_stats'),

    # Point calendar (últimos N días de consumo, caudal, nivel)
    path('point/<int:point_id>/calendar/', PointCalendarView.as_view(), name='point_calendar'),

    # Point variables mapping (id → display_key para payload dinámico)
    path('point/<int:point_id>/variables/', PointVariablesView.as_view(), name='point_variables'),

    # Password reset (usando django_rest_passwordreset)
    path('auth/password-reset/', ResetPasswordRequestToken.as_view(), name='password_reset_request'),
    path('auth/password-reset/confirm/', ResetPasswordConfirm.as_view(), name='password_reset_confirm'),
    path('auth/password-reset/validate/', ResetPasswordValidateToken.as_view(), name='password_reset_validate'),

    # Public announcements (sin auth)
    path('announcements/public/', PublicAnnouncementsView.as_view(), name='public_announcements'),
]
