"""
URLs unificadas para la API.

Consolida todos los endpoints en un esquema coherente sin versiones.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter

# ViewSets unificados (nuevos)
from api.unified.views.catchment_points import CatchmentPointViewSet
from api.unified.views.devices import DeviceViewSet
from api.unified.views.dashboard import DashboardViewSet

# ViewSets legacy (migrated to correct apps)
from api.core.views import users as views_users
from api.crm.views import ClientViewSet, ProjectViewSet, PersonViewSet
from api.notifications.views import NotificationViewSet, NotificationResponseViewSet
from api.documents.views import DocumentTypeViewSet
from api.telemetry.views import CoreVariableViewSet
from api.core.views import interaction_detail as views_detail
from api.core.views import management as views_management


# Router principal unificado
router = DefaultRouter()

# ========================================
# RECURSOS PRINCIPALES (Nuevos - Unificados)
# ========================================
router.register(r'points', CatchmentPointViewSet, basename='points')
router.register(r'devices', DeviceViewSet, basename='devices')
router.register(r'dashboard', DashboardViewSet, basename='dashboard')

# ========================================
# RECURSOS LEGACY (Migrados del router anterior)
# ========================================
# Users
router.register(r'users', views_users.UserViewSet, basename='users')

# Interaction details
router.register(r'interaction_detail', views_detail.InteractionXLS)
router.register(r'interaction_detail_override', views_detail.InteractionDetailOverrideViewSet, basename='interaction_detail_override')
router.register(r'interaction_detail_override_month', views_detail.InteractionDetailOverrideMonthViewSet, basename='interaction_detail_override_month')
router.register(r'interaction_detail_json', views_detail.InteractionDetailViewSet, basename='interaction_detail_json')

# Catchment related (legacy names for backwards compatibility)
router.register(r'client', views_catchment.ClientViewSet, basename='client')
router.register(r'project_catchments', views_catchment.ProjectViewSet, basename='project_catchments')
router.register(r'catchment_point', views_catchment.CatchmentPointViewSet, basename='catchment_point')
router.register(r'notifications_catchment', views_catchment.NotificationViewSet, basename='notifications_catchment')
router.register(r'response_notifications_catchment', views_catchment.NotificationResponseViewSet, basename='response_notifications_catchment')
router.register(r'type_file_catchment', views_catchment.DocumentTypeViewSet, basename='type_file_catchment')
router.register(r'variable', views_catchment.CoreVariableViewSet, basename='variable')
router.register(r'register_persons', views_catchment.PersonViewSet, basename='register_persons')

# Management
router.register(r'management', views_management.ManagementViewSet, basename='management')


app_name = 'unified'

urlpatterns = [
    # Router automático para CRUD + actions
    path('', include(router.urls)),
]

"""
Endpoints resultantes:

NUEVOS (Unificados):
    /api/points/                    - Puntos de captación (mejorado)
    /api/points/{id}/records/       - Registros de telemetría
    /api/points/{id}/latest/        - Última lectura
    /api/points/{id}/status/        - Estado online/offline
    /api/points/{id}/config/        - Configuración dinámica

    /api/devices/                   - Dispositivos IoT
    /api/devices/{id}/config/       - Configuración dinámica

    /api/dashboard/summary/         - Resumen ejecutivo
    /api/dashboard/realtime/        - Datos en tiempo real
    /api/dashboard/health/          - Salud del sistema

LEGACY (Compatibilidad):
    /api/users/                     - Usuarios
    /api/client/                    - Clientes
    /api/project_catchments/        - Proyectos
    /api/catchment_point/           - Puntos (legacy)
    /api/variable/                  - Variables
    /api/notifications_catchment/   - Notificaciones
    /api/management/                - Gestión
"""
