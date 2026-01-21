"""
CRM URL Configuration - V2.0
"""

from rest_framework.routers import DefaultRouter
from .views import (
    ClientViewSet, JobPositionViewSet, ProjectViewSet, PersonViewSet,
    CostCategoryViewSet, CostSubCategoryViewSet, CostTypeViewSet, CostSubTypeViewSet, ProjectCostViewSet,
    TaskCategoryViewSet, TaskSubCategoryViewSet, TaskTypeViewSet, TaskSubTypeViewSet, CrmTaskViewSet, TaskResponseViewSet,
    SurveyFieldTypeViewSet, SurveyFieldDefinitionViewSet, TechnicalSurveyViewSet
)

router = DefaultRouter()

# Cliente y Cargos
router.register(r'clients', ClientViewSet)
router.register(r'job-positions', JobPositionViewSet)

# Proyecto y Contactos
router.register(r'projects', ProjectViewSet)
router.register(r'persons', PersonViewSet)

# Costos
router.register(r'cost-categories', CostCategoryViewSet)
router.register(r'cost-subcategories', CostSubCategoryViewSet)
router.register(r'cost-types', CostTypeViewSet)
router.register(r'cost-subtypes', CostSubTypeViewSet)
router.register(r'project-costs', ProjectCostViewSet)

# Tareas
router.register(r'task-categories', TaskCategoryViewSet)
router.register(r'task-subcategories', TaskSubCategoryViewSet)
router.register(r'task-types', TaskTypeViewSet)
router.register(r'task-subtypes', TaskSubTypeViewSet)
router.register(r'tasks', CrmTaskViewSet)
router.register(r'task-responses', TaskResponseViewSet)

# Levantamiento Técnico
router.register(r'survey-field-types', SurveyFieldTypeViewSet)
router.register(r'survey-field-definitions', SurveyFieldDefinitionViewSet)
router.register(r'surveys', TechnicalSurveyViewSet)

urlpatterns = router.urls
