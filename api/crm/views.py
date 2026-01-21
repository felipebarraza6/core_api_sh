"""
CRM Views - V2.0
"""

from rest_framework import viewsets, permissions, filters
from django_filters.rest_framework import DjangoFilterBackend
from .models import (
    Client, JobPosition, Project, Person,
    CostCategory, CostSubCategory, CostType, CostSubType, ProjectCost,
    TaskCategory, TaskSubCategory, TaskType, TaskSubType, CrmTask, TaskResponse,
    SurveyFieldType, SurveyFieldDefinition, TechnicalSurvey
)
from .serializers import (
    ClientSerializer, JobPositionSerializer, ProjectSerializer, PersonSerializer,
    CostCategorySerializer, CostSubCategorySerializer, CostTypeSerializer, CostSubTypeSerializer, ProjectCostSerializer,
    TaskCategorySerializer, TaskSubCategorySerializer, TaskTypeSerializer, TaskSubTypeSerializer, CrmTaskSerializer, TaskResponseSerializer,
    SurveyFieldTypeSerializer, SurveyFieldDefinitionSerializer, TechnicalSurveySerializer
)


# =============================================================================
# CLIENTE Y CARGOS
# =============================================================================

class ClientViewSet(viewsets.ModelViewSet):
    """ViewSet for Client management."""
    queryset = Client.objects.prefetch_related('job_positions', 'projects')
    serializer_class = ClientSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['status']
    search_fields = ['name', 'rut', 'email']


class JobPositionViewSet(viewsets.ModelViewSet):
    """ViewSet for JobPosition - Cargos por cliente."""
    queryset = JobPosition.objects.select_related('client')
    serializer_class = JobPositionSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['client', 'department']
    search_fields = ['name', 'department']


# =============================================================================
# PROYECTO Y CONTACTOS
# =============================================================================

class ProjectViewSet(viewsets.ModelViewSet):
    """ViewSet for Project management."""
    queryset = Project.objects.select_related('client').prefetch_related('costs', 'tasks', 'technical_surveys', 'contacts')
    serializer_class = ProjectSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['status', 'client']
    search_fields = ['name', 'code_internal']


class PersonViewSet(viewsets.ModelViewSet):
    """ViewSet for contacts."""
    queryset = Person.objects.select_related('project', 'job_position')
    serializer_class = PersonSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['project', 'job_position']
    search_fields = ['name', 'email']


# =============================================================================
# COSTOS
# =============================================================================

class CostCategoryViewSet(viewsets.ModelViewSet):
    """ViewSet for cost categories."""
    queryset = CostCategory.objects.prefetch_related('subcategories')
    serializer_class = CostCategorySerializer
    permission_classes = [permissions.IsAuthenticated]
    search_fields = ['name']


class CostSubCategoryViewSet(viewsets.ModelViewSet):
    """ViewSet for cost subcategories."""
    queryset = CostSubCategory.objects.select_related('category')
    serializer_class = CostSubCategorySerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ['category']


class CostTypeViewSet(viewsets.ModelViewSet):
    """ViewSet for cost types (income/expense)."""
    queryset = CostType.objects.prefetch_related('subtypes')
    serializer_class = CostTypeSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ['flow']
    search_fields = ['name']


class CostSubTypeViewSet(viewsets.ModelViewSet):
    """ViewSet for cost subtypes."""
    queryset = CostSubType.objects.select_related('cost_type')
    serializer_class = CostSubTypeSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ['cost_type']


class ProjectCostViewSet(viewsets.ModelViewSet):
    """ViewSet for project costs."""
    queryset = ProjectCost.objects.select_related('project', 'category', 'subcategory', 'cost_type', 'cost_subtype')
    serializer_class = ProjectCostSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['project', 'category', 'cost_type', 'is_estimated']
    search_fields = ['description']


# =============================================================================
# TAREAS
# =============================================================================

class TaskCategoryViewSet(viewsets.ModelViewSet):
    """ViewSet for task categories."""
    queryset = TaskCategory.objects.prefetch_related('subcategories')
    serializer_class = TaskCategorySerializer
    permission_classes = [permissions.IsAuthenticated]
    search_fields = ['name']


class TaskSubCategoryViewSet(viewsets.ModelViewSet):
    """ViewSet for task subcategories."""
    queryset = TaskSubCategory.objects.select_related('category')
    serializer_class = TaskSubCategorySerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ['category']


class TaskTypeViewSet(viewsets.ModelViewSet):
    """ViewSet for task types."""
    queryset = TaskType.objects.prefetch_related('subtypes')
    serializer_class = TaskTypeSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ['requires_response']
    search_fields = ['name']


class TaskSubTypeViewSet(viewsets.ModelViewSet):
    """ViewSet for task subtypes."""
    queryset = TaskSubType.objects.select_related('task_type')
    serializer_class = TaskSubTypeSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ['task_type']


class CrmTaskViewSet(viewsets.ModelViewSet):
    """ViewSet for CRM Tasks."""
    queryset = CrmTask.objects.select_related(
        'project', 'category', 'subcategory', 'task_type', 'task_subtype', 'assigned_to'
    ).prefetch_related('responses', 'documents')
    serializer_class = CrmTaskSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['status', 'priority', 'category', 'task_type', 'project', 'assigned_to']
    search_fields = ['title', 'description']


class TaskResponseViewSet(viewsets.ModelViewSet):
    """ViewSet for task responses."""
    queryset = TaskResponse.objects.select_related('task', 'responded_by').prefetch_related('documents')
    serializer_class = TaskResponseSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ['task', 'responded_by']


# =============================================================================
# LEVANTAMIENTO TÉCNICO
# =============================================================================

class SurveyFieldTypeViewSet(viewsets.ModelViewSet):
    """ViewSet for survey field types."""
    queryset = SurveyFieldType.objects.all()
    serializer_class = SurveyFieldTypeSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ['data_type']


class SurveyFieldDefinitionViewSet(viewsets.ModelViewSet):
    """ViewSet for survey field definitions."""
    queryset = SurveyFieldDefinition.objects.select_related('field_type').filter(is_active=True)
    serializer_class = SurveyFieldDefinitionSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ['field_type', 'group', 'is_required']
    search_fields = ['name', 'code']


class TechnicalSurveyViewSet(viewsets.ModelViewSet):
    """ViewSet for technical surveys."""
    queryset = TechnicalSurvey.objects.select_related('project', 'surveyed_by').prefetch_related('documents')
    serializer_class = TechnicalSurveySerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['project', 'requires_dga', 'requires_telemetry']
    search_fields = ['name', 'gps_coordinates']
