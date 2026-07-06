from django.urls import path

from . import views

app_name = "analytics"

urlpatterns = [
    path("usage/", views.usage_metrics, name="usage-metrics"),
    path("performance/", views.performance_metrics, name="performance-metrics"),
    path("health/", views.health_scores, name="health-scores"),
    path("dashboard/", views.dashboard, name="dashboard"),
]
