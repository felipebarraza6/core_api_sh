"""
Provider URLs

Routes for dynamic provider management endpoints.
"""

from django.urls import path
from . import views

app_name = 'providers'

urlpatterns = [
    # Provider management
    path('', views.ProviderListView.as_view(), name='provider-list'),
    path('status/', views.provider_status, name='provider-status'),
    path('<str:provider_name>/', views.ProviderDetailView.as_view(), name='provider-detail'),
    path('<str:provider_name>/test/', views.test_provider, name='provider-test'),

    # Point-provider configurations
    path('points/<int:point_id>/', views.PointProviderConfigView.as_view(), name='point-providers'),
    path('points/<int:point_id>/<int:config_id>/', views.PointProviderConfigDetailView.as_view(), name='point-provider-detail'),

    # Data fetching
    path('points/<int:point_id>/data/fetch/', views.fetch_point_data, name='fetch-point-data'),
    path('points/<int:point_id>/providers/<str:provider_name>/data/fetch/', views.fetch_point_data, name='fetch-point-data-provider'),
]
