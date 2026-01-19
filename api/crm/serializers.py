"""
CRM Serializers
"""

from rest_framework import serializers
from .models import Client, Project, CrmTask, TechnicalSurvey, ProjectCost, Person


class ClientSerializer(serializers.ModelSerializer):
    """Serializer for Client model."""
    projects_count = serializers.IntegerField(source='projects.count', read_only=True)

    class Meta:
        model = Client
        fields = "__all__"


class ProjectCostSerializer(serializers.ModelSerializer):
    """Serializer for Project costs."""
    class Meta:
        model = ProjectCost
        fields = "__all__"


class TechnicalSurveySerializer(serializers.ModelSerializer):
    """Serializer for Technical Survey."""
    class Meta:
        model = TechnicalSurvey
        fields = "__all__"


class CrmTaskSerializer(serializers.ModelSerializer):
    """Serializer for CRM Tasks."""
    assigned_to_name = serializers.CharField(source='assigned_to.get_full_name', read_only=True)
    project_name = serializers.CharField(source='project.name', read_only=True)

    class Meta:
        model = CrmTask
        fields = "__all__"


class ProjectSerializer(serializers.ModelSerializer):
    """Serializer for Project model, providing enriched data."""
    client_name = serializers.CharField(source='client.name', read_only=True)
    costs = ProjectCostSerializer(many=True, read_only=True)
    survey = TechnicalSurveySerializer(source='technical_survey', read_only=True)
    total_estimated_costs = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = "__all__"

    def get_total_estimated_costs(self, obj):
        return sum(cost.amount for cost in obj.costs.all())


class PersonSerializer(serializers.ModelSerializer):
    """Serializer for contacts."""
    client_name = serializers.CharField(source='client.name', read_only=True)

    class Meta:
        model = Person
        fields = "__all__"
