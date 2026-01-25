# ViewSets unificados para API v4
from api.unified.views.base import BaseViewSet
from api.unified.views.catchment_points import CatchmentPointViewSet
from api.unified.views.devices import DeviceViewSet
from api.unified.views.dashboard import DashboardViewSet

__all__ = [
    'BaseViewSet',
    'CatchmentPointViewSet',
    'DeviceViewSet',
    'DashboardViewSet',
]
