from rest_framework import serializers
from api.telemetry.models import CatchmentPoint, CoreVariable, TelemetryRecord
from api.crm.models import Project, Client
from api.subscriptions.models import PointModuleAccess

class VariableSerializer(serializers.ModelSerializer):
    class Meta:
        model = CoreVariable
        fields = (
            'id', 'name', 'internal_code', 'unit', 'scale_factor', 
            'offset', 'operation', 'formula', 'is_virtual', 'is_active'
        )

class UnifiedCatchmentPointSerializer(serializers.ModelSerializer):
    """
    Serializer unificado para Puntos de Captación.
    Combina información del negocio, configuración y salud del punto.
    """
    client_name = serializers.CharField(source='project.client.name', read_only=True)
    project_name = serializers.CharField(source='project.name', read_only=True)
    variables = VariableSerializer(many=True, read_only=True)
    status = serializers.SerializerMethodField()
    modules = serializers.SerializerMethodField()

    class Meta:
        model = CatchmentPoint
        fields = (
            'id', 'title', 'point_code', 'lat', 'lon', 
            'client_name', 'project_name', 'variables', 
            'status', 'modules', 'is_active'
        )

    def get_status(self, obj):
        last_record = TelemetryRecord.objects.filter(point=obj).first()
        if not last_record:
            return {"online": False, "last_seen": None}
        
        from django.utils import timezone
        from datetime import timedelta
        is_online = last_record.timestamp >= (timezone.now() - timedelta(minutes=obj.frequency_minutes * 2))
        
        return {
            "online": is_online,
            "last_seen": last_record.timestamp,
            "is_error": last_record.is_error
        }

    def get_modules(self, obj):
        # Mapeo de módulos activos similar a IkoluSerializer
        access = PointModuleAccess.objects.filter(point=obj, is_active=True).select_related('module')
        return {a.module.code: True for a in access}

class UnifiedTelemetryRecordSerializer(serializers.ModelSerializer):
    """
    Serializer unificado para registros de telemetría.
    Aplana el JSONField 'data' para facilitar el consumo en frontend.
    """
    class Meta:
        model = TelemetryRecord
        fields = ('id', 'timestamp', 'data', 'metadata', 'compliance_status', 'is_error')

    def to_representation(self, instance):
        repr = super().to_representation(instance)
        # Aplanar datos dinámicos
        if isinstance(instance.data, dict):
            repr.update(instance.data)
        
        # Compatibilidad legacy para dashboards antiguos
        if 'flow' not in repr and 'caudal' in repr:
            repr['flow'] = repr['caudal']
        
        return repr
