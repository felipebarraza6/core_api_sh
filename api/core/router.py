"""Urls Customers."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from api.core.views import users as views_users
from api.core.views import catchment_points as views_catchment
from api.core.views import interaction_detail as views_detail
from api.core.views import management as views_management

router = DefaultRouter()

# Users
router.register(r'users', views_users.UserViewSet, basename='users')

# Interaction details
router.register(r'interaction_detail', views_detail.InteractionXLS)
router.register(r'interaction_detail_dga', views_detail.InteractionXLSDga, basename='interaction_detail_dga')
router.register(r'interaction_detail_override', views_detail.InteractionDetailOverrideViewSet, basename='interaction_detail_override')
router.register(r'interaction_detail_override_month', views_detail.InteractionDetailOverrideMonthViewSet, basename='interaction_detail_override_month')
router.register(r'interaction_detail_override_month_xlsx', views_detail.InteractionXLSMonth, basename='interaction_detail_override_month_xlsx')
router.register(r'interaction_detail_json', views_detail.InteractionDetailViewSet, basename='interaction_detail_json')

# Catchment related (New Apps)
router.register(r'client', views_catchment.ClientViewSet, basename='client')
router.register(r'project_catchments', views_catchment.ProjectViewSet, basename='project_catchments')
router.register(r'catchment_point', views_catchment.CatchmentPointViewSet, basename='catchment_point')
router.register(r'profile_ikolu_catchment', views_catchment.ProfileIkoluCatchmentViewSet, basename='profile_ikolu_catchment')
router.register(r'notifications_catchment', views_catchment.NotificationViewSet, basename='notifications_catchment')
router.register(r'response_notifications_catchment', views_catchment.NotificationResponseViewSet, basename='response_notifications_catchment')
router.register(r'type_file_catchment', views_catchment.DocumentTypeViewSet, basename='type_file_catchment')
router.register(r'file_catchment', views_catchment.DocumentViewSet, basename='file_catchment')
router.register(r'profile_data_config_catchment', views_catchment.ProfileDataConfigCatchmentViewSet, basename='profile_data_config_catchment')
router.register(r'dga_data_config_catchment', views_catchment.DgaDataConfigCatchmentViewSet, basename='dga_data_config_catchment')
router.register(r'variable', views_catchment.CoreVariableViewSet, basename='variable')
router.register(r'register_persons', views_catchment.PersonViewSet, basename='register_persons')

# Management
router.register(r'management', views_management.ManagementViewSet, basename='management')

urlpatterns = [
    path('', include(router.urls))
]
