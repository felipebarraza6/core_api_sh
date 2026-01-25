from rest_framework import serializers
from api.dynamic_registry.models import SystemModule, ModuleView, DynamicAction

class DynamicActionSerializer(serializers.ModelSerializer):
    class Meta:
        model = DynamicAction
        fields = [
            'name', 'key', 'icon', 'action_type', 'target', 
            'payload_schema', 'requires_confirmation'
        ]

class ModuleViewSerializer(serializers.ModelSerializer):
    actions = DynamicActionSerializer(many=True, read_only=True)
    
    class Meta:
        model = ModuleView
        fields = [
            'name', 'key', 'view_type', 'data_source', 
            'layout_config', 'is_home', 'order', 'actions'
        ]

class SystemModuleSerializer(serializers.ModelSerializer):
    views = ModuleViewSerializer(many=True, read_only=True)
    
    class Meta:
        model = SystemModule
        fields = [
            'name', 'slug', 'description', 'icon', 
            'order', 'required_permissions', 'views'
        ]
