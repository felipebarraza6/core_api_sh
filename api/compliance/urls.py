from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ComplianceVoucherViewSet, 
    ComplianceConfigViewSet, 
    ComplianceDashboardViewSet
)

router = DefaultRouter()
router.register(r'vouchers', ComplianceVoucherViewSet, basename='compliance-voucher')
router.register(r'config', ComplianceConfigViewSet, basename='compliance-config')
router.register(r'dashboard', ComplianceDashboardViewSet, basename='compliance-dashboard')

urlpatterns = [
    path('', include(router.urls)),
]
