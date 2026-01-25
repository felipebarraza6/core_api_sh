"""
Serializers canónicos para Device.

Incluye soporte para campos dinámicos (configuration_scheme).
"""

from rest_framework import serializers

from api.infrastructure.models import Device, DeviceModel, Manufacturer
from api.unified.serializers.base import StatusMixin, ConfigMixin


class ManufacturerSerializer(serializers.ModelSerializer):
    """Serializer para fabricantes."""

    class Meta:
        model = Manufacturer
        fields = (
            'id',
            'name',
            'code',
            'description',
            'website',
            'integration_status',
        )


class DeviceModelSerializer(serializers.ModelSerializer):
    """Serializer para modelos de dispositivo."""
    manufacturer_name = serializers.CharField(
        source='manufacturer.name',
        read_only=True
    )

    class Meta:
        model = DeviceModel
        fields = (
            'id',
            'manufacturer',
            'manufacturer_name',
            'model_name',
            'model_code',
            'description',
        )


class DeviceListSerializer(StatusMixin, serializers.ModelSerializer):
    """
    Serializer ligero para listados de dispositivos.
    """
    model_name = serializers.CharField(
        source='device_model.model_name',
        read_only=True
    )
    manufacturer_name = serializers.CharField(
        source='device_model.manufacturer.name',
        read_only=True
    )
    points_count = serializers.SerializerMethodField()
    device_status = serializers.SerializerMethodField()

    class Meta:
        model = Device
        fields = (
            'id',
            'device_id',
            'name',
            'model_name',
            'manufacturer_name',
            'status',
            'last_seen',
            'points_count',
            'device_status',
        )

    def get_points_count(self, obj):
        return obj.catchment_points.filter(is_active=True).count()

    def get_device_status(self, obj):
        return self._get_entity_status(obj)


class DeviceDetailSerializer(StatusMixin, ConfigMixin, serializers.ModelSerializer):
    """
    Serializer completo para detalle de dispositivo.
    Incluye configuración dinámica y puntos asociados.
    """
    device_model_info = DeviceModelSerializer(source='device_model', read_only=True)
    points_count = serializers.SerializerMethodField()
    device_status = serializers.SerializerMethodField()
    config = serializers.SerializerMethodField()
    config_scheme = serializers.SerializerMethodField()
    associated_points = serializers.SerializerMethodField()

    class Meta:
        model = Device
        fields = (
            'id',
            'device_id',
            'name',
            'device_model',
            'device_model_info',
            'status',
            'last_seen',
            'imei',
            'use_internal_mqtt',
            'token',
            'points_count',
            'device_status',
            'config',
            'config_scheme',
            'associated_points',
            'created',
            'modified',
        )
        read_only_fields = ('device_id', 'token')

    def get_points_count(self, obj):
        return obj.catchment_points.filter(is_active=True).count()

    def get_device_status(self, obj):
        return self._get_entity_status(obj)

    def get_config(self, obj):
        return self._get_entity_config(obj)

    def get_config_scheme(self, obj):
        return self._get_config_scheme_info(obj)

    def get_associated_points(self, obj):
        """Lista de puntos asociados al dispositivo."""
        points = obj.catchment_points.filter(is_active=True).select_related('project')
        return [
            {
                "id": p.id,
                "title": p.title,
                "point_code": p.point_code,
                "project_name": p.project.name if p.project else None,
            }
            for p in points
        ]


class DeviceCreateSerializer(serializers.ModelSerializer):
    """
    Serializer para crear/actualizar dispositivos.
    """

    class Meta:
        model = Device
        fields = (
            'id',
            'name',
            'device_model',
            'status',
            'imei',
            'use_internal_mqtt',
            'token',
        )
        read_only_fields = ('id',)
        extra_kwargs = {
            'token': {'required': False},
        }


class DeviceConfigSerializer(serializers.Serializer):
    """
    Serializer para actualizar configuración dinámica de un dispositivo.
    """
    config = serializers.DictField(
        child=serializers.JSONField(),
        help_text="Diccionario de configuración {field_code: value}"
    )

    def update_config(self, device, validated_data):
        """Actualiza la configuración del dispositivo."""
        # Importar modelo cuando esté creado
        try:
            from api.infrastructure.models import DeviceConfigurationValue

            config = validated_data.get('config', {})

            for field_code, value in config.items():
                if device.configuration_scheme:
                    field = device.configuration_scheme.fields.filter(code=field_code).first()
                    if field:
                        DeviceConfigurationValue.objects.update_or_create(
                            device=device,
                            field=field,
                            defaults={'value': value}
                        )

            return device.get_config_dict()
        except ImportError:
            # Modelo aún no creado
            return {}
