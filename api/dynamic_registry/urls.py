from django.urls import path, include
from rest_framework.routers import DefaultRouter
from api.dynamic_registry.views import RegistryViewSet, DataProxyViewSet

router = DefaultRouter()
router.register(r'modules', RegistryViewSet, basename='modules')

urlpatterns = [
    path('', include(router.urls)),
    
    # Universal Data Proxy
    path('proxy/<str:app_label>/<str:model_name>/', 
         DataProxyViewSet.as_view({'get': 'list', 'post': 'create'}), 
         name='data_proxy_list'),
    path('proxy/<str:app_label>/<str:model_name>/<int:pk>/', 
         DataProxyViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}), 
         name='data_proxy_detail'),
]
