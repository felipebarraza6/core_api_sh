"""
API IK Routes - Optimized Endpoints
====================================

Estos endpoints son NUEVOS y no afectan la API original.
Acceso: /api/ik/

Endpoints disponibles:
- POST /api/ik/batch/telemetry/ - Telemetría multi-punto
- POST /api/ik/batch/stats/ - Stats agregados
- POST /api/ik/login/ - Login optimizado (menos datos)
"""

from django.urls import path
from api.core.views.batch_views import BatchTelemetryView, BatchStatsView
from .views import OptimizedLoginView

app_name = 'api_ik'

urlpatterns = [
    # Batch endpoints
    path('batch/telemetry/', BatchTelemetryView.as_view(), name='batch_telemetry'),
    path('batch/stats/', BatchStatsView.as_view(), name='batch_stats'),
    
    # Optimized login (menos datos que el original)
    path('login/', OptimizedLoginView.as_view(), name='login'),
]
