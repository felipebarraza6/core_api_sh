"""
CRM Views
"""

from rest_framework import viewsets, permissions, filters
from django_filters.rest_framework import DjangoFilterBackend
from .models import Client, Project, CrmTask, TechnicalSurvey, ProjectCost, Person
from .serializers import (
    ClientSerializer, ProjectSerializer, CrmTaskSerializer, 
    TechnicalSurveySerializer, ProjectCostSerializer, PersonSerializer
)


class ClientViewSet(viewsets.ModelViewSet):
    """ViewSet for Client management."""
    queryset = Client.objects.all()
    serializer_class = ClientSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['status']
    search_fields = ['name', 'rut', 'email']


class ProjectViewSet(viewsets.ModelViewSet):
    """ViewSet for Project management."""
    queryset = Project.objects.select_related('client').prefetch_related('costs', 'tasks')
    serializer_class = ProjectSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['status', 'client']
    search_fields = ['name', 'code_internal']


class CrmTaskViewSet(viewsets.ModelViewSet):
    """ViewSet for CRM Tasks."""
    queryset = CrmTask.objects.select_related('project', 'assigned_to')
    serializer_class = CrmTaskSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['status', 'priority', 'task_type', 'project', 'assigned_to']
    search_fields = ['title', 'description']


class TechnicalSurveyViewSet(viewsets.ModelViewSet):
    """ViewSet for technical surveys."""
    queryset = TechnicalSurvey.objects.select_related('project')
    serializer_class = TechnicalSurveySerializer
    permission_classes = [permissions.IsAuthenticated]


class ProjectCostViewSet(viewsets.ModelViewSet):
    """ViewSet for project costs."""
    queryset = ProjectCost.objects.select_related('project')
    serializer_class = ProjectCostSerializer
    permission_classes = [permissions.IsAuthenticated]


class PersonViewSet(viewsets.ModelViewSet):
    """ViewSet for contacts."""
    queryset = Person.objects.select_related('client')
    serializer_class = PersonSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['client']
    search_fields = ['name', 'email']
