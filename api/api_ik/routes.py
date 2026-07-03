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
    PointVariablesView, ClientStatsChatView, PointRecordsView, PointConfigView,
    SystemEventsSummaryView, StaffUsersListView,
)
from .views_tickets import (
    TicketsListCreateView,
    TicketDetailUpdateView,
    TicketCommentsView,
    TicketAssignView,
    TicketStatusChangeView,
    TicketStatsView,
    TicketAttachmentsView,
    TicketCategoryListCreateView,
    TicketCategoryDetailView,
    TicketMyDeskView,
    SLAConfigListCreateView,
    SLAConfigDetailView,
)
from .views_telemetry_backfill import TelemetryBackfillView
from .views_point_gaps import PointGapsView
from .views_compliance import (
    ComplianceListView,
    ToggleComplianceView,
    ComplianceFlowHistoryView,
    ComplianceNearLimitView,
)
from .views_control_center import (
    ControlCenterGeneralStatsView,
    ControlCenterDailySummaryView,
    ControlCenterProjectPointsView,
    ControlCenterListView,
    ControlCenterSystemEventsListView,
    ControlCenterSystemEventsPointDetailView,
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

    # Staff users list (para asignación de tickets/soporte)
    path('staff_users/', StaffUsersListView.as_view(), name='staff_users'),

    # Points summary (reemplaza get_profile para Centro de Control)
    path('points_summary/', PointsSummaryView.as_view(), name='points_summary'),
    path('point/<int:point_id>/summary/', PointSummaryView.as_view(), name='point_summary'),

    # My points (select/dropdown liviano)
    path('my_points/', MyPointsView.as_view(), name='my_points'),

    # Dashboard stats (KPIs del Centro de Control)
    path('dashboard_stats/', DashboardStatsView.as_view(), name='dashboard_stats'),

    # Control Center (nueva familia de endpoints, frontend en desarrollo)
    path('control_center/general_stats/', ControlCenterGeneralStatsView.as_view(), name='control_center_general_stats'),
    path('control_center/daily_summary/', ControlCenterDailySummaryView.as_view(), name='control_center_daily_summary'),
    path('control_center/project_points/', ControlCenterProjectPointsView.as_view(), name='control_center_project_points'),
    path('control_center/list/', ControlCenterListView.as_view(), name='control_center_list'),
    path('control_center/system_events/', ControlCenterSystemEventsListView.as_view(), name='control_center_system_events'),
    path('control_center/system_events/<int:point_id>/', ControlCenterSystemEventsPointDetailView.as_view(), name='control_center_system_events_point_detail'),

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

    # Tickets de soporte + SLA
    path('tickets/', TicketsListCreateView.as_view(), name='tickets_list_create'),
    path('tickets/<int:pk>/', TicketDetailUpdateView.as_view(), name='ticket_detail_update'),
    path('tickets/<int:pk>/comments/', TicketCommentsView.as_view(), name='ticket_comments'),
    path('tickets/<int:pk>/assign/', TicketAssignView.as_view(), name='ticket_assign'),
    path('tickets/<int:pk>/status/', TicketStatusChangeView.as_view(), name='ticket_status'),
    path('tickets/<int:pk>/attachments/', TicketAttachmentsView.as_view(), name='ticket_attachments'),
    path('tickets/stats/', TicketStatsView.as_view(), name='ticket_stats'),
    path('tickets/my_desk/', TicketMyDeskView.as_view(), name='ticket_my_desk'),
    path('ticket-categories/', TicketCategoryListCreateView.as_view(), name='ticket_categories_list_create'),
    path('ticket-categories/<int:pk>/', TicketCategoryDetailView.as_view(), name='ticket_categories_detail'),
    path('sla-configs/', SLAConfigListCreateView.as_view(), name='sla_configs_list_create'),
    path('sla-configs/<int:pk>/', SLAConfigDetailView.as_view(), name='sla_configs_detail'),

    # Backfill histórico de telemetría
    path('telemetry/backfill/', TelemetryBackfillView.as_view(), name='telemetry_backfill'),

    # Gap detection para un punto (solo lectura)
    path('point/<int:id>/gaps/', PointGapsView.as_view(), name='point_gaps'),

    # Compliance DGA/SMA (listado completo + toggle)
    path('compliance/', ComplianceListView.as_view(), name='compliance_list'),
    path('compliance/<int:point_id>/flow_history/', ComplianceFlowHistoryView.as_view(), name='compliance_flow_history'),
    path('compliance/<int:point_id>/near_limit/', ComplianceNearLimitView.as_view(), name='compliance_near_limit'),
    path('management/toggle_compliance/', ToggleComplianceView.as_view(), name='toggle_compliance'),

    # Chat interpretativo con stats del cliente
    path('chat/client/general_stats/', ClientStatsChatView.as_view(), name='client_stats_chat'),

    # Registros de telemetría por punto y rango de fechas
    path('point/<int:point_id>/records/', PointRecordsView.as_view(), name='point_records'),

    # Config del punto (d1-d6, addition, is_telemetry, offsets, límites)
    path('point/<int:point_id>/config/', PointConfigView.as_view(), name='point_config'),
    path('points/<int:point_id>/config/', PointConfigView.as_view(), name='points_config'),

    # Resumen de eventos del sistema (auditoría / informes)
    path('system-events/summary/', SystemEventsSummaryView.as_view(), name='system_events_summary'),
]
