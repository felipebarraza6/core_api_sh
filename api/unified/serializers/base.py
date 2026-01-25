"""
Base Serializers y Mixins para API v4.

Proporciona mixins reutilizables para agregar funcionalidad común
a todos los serializers de la API unificada.
"""

from rest_framework import serializers


class StatusMixin:
    """
    Mixin para agregar status online/offline a cualquier serializer.

    Uso:
        class MySerializer(StatusMixin, serializers.ModelSerializer):
            status = serializers.SerializerMethodField()

            def get_status(self, obj):
                return self._get_entity_status(obj)
    """

    def _get_entity_status(self, obj):
        """
        Obtiene el status de una entidad (CatchmentPoint o Device).
        """
        from api.unified.services.status_service import StatusService

        # Detectar tipo de entidad
        model_name = obj.__class__.__name__

        if model_name == 'CatchmentPoint':
            return StatusService.get_point_status(obj.id)
        elif model_name == 'Device':
            return StatusService.get_device_status(obj.id)

        return {"online": False, "offline_reason": "UNKNOWN_ENTITY"}


class ConfigMixin:
    """
    Mixin para agregar configuración dinámica a serializers.

    Uso:
        class MySerializer(ConfigMixin, serializers.ModelSerializer):
            config = serializers.SerializerMethodField()

            def get_config(self, obj):
                return self._get_entity_config(obj)
    """

    def _get_entity_config(self, obj):
        """
        Obtiene la configuración dinámica de una entidad.
        """
        if hasattr(obj, 'get_config_dict'):
            return obj.get_config_dict()
        return {}

    def _get_config_scheme_info(self, obj):
        """
        Obtiene información del esquema de configuración.
        """
        if hasattr(obj, 'configuration_scheme') and obj.configuration_scheme:
            scheme = obj.configuration_scheme
            return {
                "id": scheme.id,
                "name": scheme.name,
                "code": scheme.code,
                "category": scheme.category,
            }
        return None


class VariableSerializer(serializers.Serializer):
    """
    Serializer canónico para CoreVariable.
    Reemplaza las múltiples versiones en core/serializers y telemetry/serializers.
    """
    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField()
    internal_code = serializers.CharField()
    unit = serializers.CharField(allow_null=True)
    scale_factor = serializers.FloatField()
    offset = serializers.FloatField()
    is_virtual = serializers.BooleanField()
    is_active = serializers.BooleanField()
    min_value = serializers.FloatField(allow_null=True)
    max_value = serializers.FloatField(allow_null=True)


class TelemetryRecordSerializer(serializers.Serializer):
    """
    Serializer canónico para TelemetryRecord.
    Aplana el JSONField 'data' para facilitar consumo del frontend.
    """
    id = serializers.IntegerField(read_only=True)
    timestamp = serializers.DateTimeField()
    data = serializers.JSONField()
    metadata = serializers.JSONField()
    compliance_status = serializers.JSONField()
    is_error = serializers.BooleanField()
    is_partial = serializers.BooleanField()

    # Campos calculados para compatibilidad legacy
    flow = serializers.FloatField(read_only=True)
    total = serializers.FloatField(read_only=True)
    nivel = serializers.FloatField(read_only=True)

    def to_representation(self, instance):
        """Aplana el campo 'data' al nivel superior para fácil acceso."""
        repr_data = super().to_representation(instance)

        # Aplanar data al nivel superior
        if isinstance(instance.data, dict):
            for key, value in instance.data.items():
                if key not in repr_data:
                    repr_data[key] = value

        return repr_data
