"""
URLs para API V2 - Endpoints Optimizados y Granulares
Resuelve problemas de carga de datos del frontend actual
"""

from django.urls import path
from .views.v2_views import (
    DashboardSummaryView,
    OptimizedBatchTelemetryView,
    RealtimeDashboardView,
    UserActionControlView,
    SystemStatsView,
)

app_name = 'api_v2'

urlpatterns = [
    # Dashboard Ejecutivo - Un endpoint para todo
    path('dashboard/summary/', DashboardSummaryView.as_view(), name='dashboard_summary'),

    # Dashboard en Tiempo Real
    path('dashboard/realtime/', RealtimeDashboardView.as_view(), name='dashboard_realtime'),

    # Telemetría Optimizada
    path('telemetry/batch/', OptimizedBatchTelemetryView.as_view(), name='telemetry_batch_v2'),

    # Control de Acciones de Usuario (ERP integrado)
    path('control/user-actions/', UserActionControlView.as_view(), name='user_actions'),

    # Estadísticas del Sistema en Tiempo Real
    path('stats/system/', SystemStatsView.as_view(), name='system_stats'),

    # Legacy support - redirects to optimized endpoints
    # path('telemetry/stream/', StreamingTelemetryView.as_view(), name='telemetry_stream'),
    # path('analytics/realtime/', RealtimeAnalyticsView.as_view(), name='analytics_realtime'),
    # path('control/compliance/', ComplianceControlView.as_view(), name='compliance_control'),
    # path('chatbot/commands/', ChatbotCommandView.as_view(), name='chatbot_commands'),
    # path('stats/user-activity/', UserActivityStatsView.as_view(), name='user_activity_stats'),
]