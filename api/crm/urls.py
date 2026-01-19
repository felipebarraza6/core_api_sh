"""
CRM URL Configuration
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ClientViewSet, ProjectViewSet, CrmTaskViewSet, 
    TechnicalSurveyViewSet, ProjectCostViewSet, PersonViewSet
)

router = DefaultRouter()
router.register(r'clients', ClientViewSet)
router.register(r'projects', ProjectViewSet)
router.register(r'tasks', CrmTaskViewSet)
router.register(r'surveys', TechnicalSurveyViewSet)
router.register(r'costs', ProjectCostViewSet)
router.register(r'contacts', PersonViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
