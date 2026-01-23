from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import TelemetryViewSet

router = DefaultRouter()
router.register(r'points', TelemetryViewSet, basename='telemetry-points')

urlpatterns = [
    path('', include(router.urls)),
]
