"""
CRM Serializers - V2.0
"""

from rest_framework import serializers
from .models import (
    Client, JobPosition, Project, Person,
    CostCategory, CostSubCategory, CostType, CostSubType, ProjectCost,
    TaskCategory, TaskSubCategory, TaskType, TaskSubType, CrmTask, TaskResponse,
    SurveyFieldType, SurveyFieldDefinition, TechnicalSurvey
)


# =============================================================================
# CLIENTE Y CARGOS
# =============================================================================

class JobPositionSerializer(serializers.ModelSerializer):
    class Meta:
        model = JobPosition
        fields = '__all__'


class ClientSerializer(serializers.ModelSerializer):
    job_positions = JobPositionSerializer(many=True, read_only=True)
    
    class Meta:
        model = Client
        fields = '__all__'


# =============================================================================
# PROYECTO Y CONTACTOS
# =============================================================================

class PersonSerializer(serializers.ModelSerializer):
    job_position_name = serializers.CharField(source='job_position.name', read_only=True)
    
    class Meta:
        model = Person
        fields = '__all__'


class ProjectSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source='client.name', read_only=True)
    contacts = PersonSerializer(many=True, read_only=True)
    surveys_count = serializers.IntegerField(source='technical_surveys.count', read_only=True)
    
    class Meta:
        model = Project
        fields = '__all__'


# =============================================================================
# COSTOS
# =============================================================================

class CostSubCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = CostSubCategory
        fields = '__all__'


class CostCategorySerializer(serializers.ModelSerializer):
    subcategories = CostSubCategorySerializer(many=True, read_only=True)
    
    class Meta:
        model = CostCategory
        fields = '__all__'


class CostSubTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = CostSubType
        fields = '__all__'


class CostTypeSerializer(serializers.ModelSerializer):
    subtypes = CostSubTypeSerializer(many=True, read_only=True)
    
    class Meta:
        model = CostType
        fields = '__all__'


class ProjectCostSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    cost_type_name = serializers.CharField(source='cost_type.name', read_only=True)
    cost_type_flow = serializers.CharField(source='cost_type.flow', read_only=True)
    
    class Meta:
        model = ProjectCost
        fields = '__all__'


# =============================================================================
# TAREAS
# =============================================================================

class TaskSubCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskSubCategory
        fields = '__all__'


class TaskCategorySerializer(serializers.ModelSerializer):
    subcategories = TaskSubCategorySerializer(many=True, read_only=True)
    
    class Meta:
        model = TaskCategory
        fields = '__all__'


class TaskSubTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskSubType
        fields = '__all__'


class TaskTypeSerializer(serializers.ModelSerializer):
    subtypes = TaskSubTypeSerializer(many=True, read_only=True)
    
    class Meta:
        model = TaskType
        fields = '__all__'


class TaskResponseSerializer(serializers.ModelSerializer):
    responded_by_name = serializers.CharField(source='responded_by.get_full_name', read_only=True)
    
    class Meta:
        model = TaskResponse
        fields = '__all__'


class CrmTaskSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    task_type_name = serializers.CharField(source='task_type.name', read_only=True)
    assigned_to_name = serializers.CharField(source='assigned_to.get_full_name', read_only=True)
    responses = TaskResponseSerializer(many=True, read_only=True)
    responses_count = serializers.IntegerField(source='responses.count', read_only=True)
    
    class Meta:
        model = CrmTask
        fields = '__all__'


# =============================================================================
# LEVANTAMIENTO TÉCNICO
# =============================================================================

class SurveyFieldTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = SurveyFieldType
        fields = '__all__'


class SurveyFieldDefinitionSerializer(serializers.ModelSerializer):
    field_type_name = serializers.CharField(source='field_type.name', read_only=True)
    data_type = serializers.CharField(source='field_type.data_type', read_only=True)
    
    class Meta:
        model = SurveyFieldDefinition
        fields = '__all__'


class TechnicalSurveySerializer(serializers.ModelSerializer):
    project_name = serializers.CharField(source='project.name', read_only=True)
    surveyed_by_name = serializers.CharField(source='surveyed_by.get_full_name', read_only=True)
    generated_point_id = serializers.IntegerField(source='generated_point.id', read_only=True)
    generated_point_title = serializers.CharField(source='generated_point.title', read_only=True)
    
    class Meta:
        model = TechnicalSurvey
        fields = '__all__'
