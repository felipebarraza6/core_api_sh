from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    TelemetryProviderViewSet,
    CatchmentPointProviderViewSet,
    ProviderDataView
)

# Crear router para las vistas basadas en ViewSet
router = DefaultRouter()
router.register(r'providers', TelemetryProviderViewSet, basename='telemetry-provider')
router.register(r'point-providers', CatchmentPointProviderViewSet, basename='catchment-point-provider')

urlpatterns = [
    # Incluir las rutas del router
    path('', include(router.urls)),

    # Endpoint para obtener datos de proveedores
    path('data/<str:provider_name>/<str:point_code>/', ProviderDataView.as_view(), name='provider-data'),

    # Endpoint para obtener datos por punto de captación
    path('point/<int:point_id>/data/', ProviderDataView.as_view(), name='point-data'),
]