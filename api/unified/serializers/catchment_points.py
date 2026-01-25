"""
Serializers canónicos para CatchmentPoint.

ÚNICO lugar para serializers de puntos de captación.
Reemplaza las versiones duplicadas en:
- api/core/serializers/catchment_points.py
- api/core/serializers/users.py
- api/telemetry/serializers.py
"""

from rest_framework import serializers

from api.telemetry.models.catchment_points import CatchmentPoint
from api.unified.serializers.base import StatusMixin, ConfigMixin, VariableSerializer


class CatchmentPointListSerializer(StatusMixin, serializers.ModelSerializer):
    """
    Serializer ligero para listados de puntos.
    Optimizado para dashboards y listas con muchos elementos.
    """
    client_name = serializers.CharField(
        source='project.client.name',
        read_only=True,
        allow_null=True
    )
    project_name = serializers.CharField(
        source='project.name',
        read_only=True,
        allow_null=True
    )
    device_name = serializers.CharField(
        source='device.name',
        read_only=True,
        allow_null=True
    )
    status = serializers.SerializerMethodField()

    class Meta:
        model = CatchmentPoint
        fields = (
            'id',
            'title',
            'point_code',
            'lat',
            'lon',
            'is_active',
            'client_name',
            'project_name',
            'device_name',
            'status',
        )

    def get_status(self, obj):
        return self._get_entity_status(obj)


class CatchmentPointDetailSerializer(StatusMixin, ConfigMixin, serializers.ModelSerializer):
    """
    Serializer completo para detalle de punto.
    Incluye variables, configuración y módulos.
    """
    client_name = serializers.CharField(
        source='project.client.name',
        read_only=True,
        allow_null=True
    )
    project_name = serializers.CharField(
        source='project.name',
        read_only=True,
        allow_null=True
    )
    device_name = serializers.CharField(
        source='device.name',
        read_only=True,
        allow_null=True
    )
    device_id = serializers.IntegerField(
        source='device.id',
        read_only=True,
        allow_null=True
    )
    status = serializers.SerializerMethodField()
    config = serializers.SerializerMethodField()
    config_scheme = serializers.SerializerMethodField()
    variables = serializers.SerializerMethodField()
    modules = serializers.SerializerMethodField()
    latest_record = serializers.SerializerMethodField()

    class Meta:
        model = CatchmentPoint
        fields = (
            'id',
            'title',
            'point_code',
            'lat',
            'lon',
            'is_active',
            'addition',
            'client_name',
            'project_name',
            'device_name',
            'device_id',
            'status',
            'config',
            'config_scheme',
            'variables',
            'modules',
            'latest_record',
            'created',
            'modified',
        )

    def get_status(self, obj):
        return self._get_entity_status(obj)

    def get_config(self, obj):
        return self._get_entity_config(obj)

    def get_config_scheme(self, obj):
        return self._get_config_scheme_info(obj)

    def get_variables(self, obj):
        variables = obj.variables.filter(is_active=True)
        return VariableSerializer(variables, many=True).data

    def get_modules(self, obj):
        """Obtiene módulos habilitados para este punto."""
        try:
            from api.subscriptions.models import PointModuleAccess
            accesses = PointModuleAccess.objects.filter(
                point=obj,
                is_active=True
            ).select_related('module')

            return [
                {
                    "id": access.module.id,
                    "name": access.module.name,
                    "code": access.module.code,
                }
                for access in accesses
            ]
        except Exception:
            return []

    def get_latest_record(self, obj):
        """Obtiene el último registro de telemetría."""
        from api.telemetry.models import TelemetryRecord

        record = TelemetryRecord.objects.filter(
            point=obj
        ).order_by('-timestamp').first()

        if not record:
            return None

        return {
            "id": record.id,
            "timestamp": record.timestamp.isoformat(),
            "data": record.data,
            "flow": record.flow,
            "total": record.total,
            "nivel": record.nivel,
            "is_error": record.is_error,
        }


class CatchmentPointCreateSerializer(serializers.ModelSerializer):
    """
    Serializer para crear/actualizar puntos.
    Campos mínimos requeridos para la creación.
    """

    class Meta:
        model = CatchmentPoint
        fields = (
            'id',
            'title',
            'point_code',
            'lat',
            'lon',
            'is_active',
            'owner_user',
            'project',
            'device',
            'configuration_scheme',
            'processing_scheme',
            'frequency',
        )
        read_only_fields = ('id',)

    def create(self, validated_data):
        return CatchmentPoint.objects.create(**validated_data)

    def update(self, instance, validated_data):
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


class CatchmentPointConfigSerializer(serializers.Serializer):
    """
    Serializer para actualizar configuración dinámica de un punto.
    """
    config = serializers.DictField(
        child=serializers.JSONField(),
        help_text="Diccionario de configuración {field_code: value}"
    )

    def update_config(self, point, validated_data):
        """Actualiza la configuración del punto."""
        from api.telemetry.models.configuration import PointConfigurationValue

        config = validated_data.get('config', {})

        for field_code, value in config.items():
            # Buscar el campo en el esquema
            if point.configuration_scheme:
                field = point.configuration_scheme.fields.filter(code=field_code).first()
                if field:
                    PointConfigurationValue.objects.update_or_create(
                        point=point,
                        field=field,
                        defaults={'value': value}
                    )

        return point.get_config_dict()
