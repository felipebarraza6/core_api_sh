# Serializers canónicos para API v4
from api.unified.serializers.base import StatusMixin, ConfigMixin
from api.unified.serializers.catchment_points import (
    CatchmentPointListSerializer,
    CatchmentPointDetailSerializer,
    CatchmentPointCreateSerializer,
)
from api.unified.serializers.devices import (
    DeviceListSerializer,
    DeviceDetailSerializer,
)

__all__ = [
    'StatusMixin',
    'ConfigMixin',
    'CatchmentPointListSerializer',
    'CatchmentPointDetailSerializer',
    'CatchmentPointCreateSerializer',
    'DeviceListSerializer',
    'DeviceDetailSerializer',
]
