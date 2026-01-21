"""
Providers Models

NOTA: Los modelos completos se migrarán desde api.telemetry.providers.models
Este archivo define la estructura base.
"""

from django.db import models
from api.core.models.utils import ModelApi


# Los modelos TelemetryProvider, CatchmentPointProvider, MQTTProviderConfig, etc.
# se migrarán aquí desde api/telemetry/providers/

# Por ahora, dejamos imports para evitar romper el código existente:
# from api.telemetry.providers.models import (
#     TelemetryProvider,
#     CatchmentPointProvider,
# )
# from api.telemetry.providers.mqtt_models import (
#     MQTTProviderConfig,
#     PayloadParsingRule,
#     CatchmentPointMQTT,
# )

# TODO: Migración gradual de modelos desde telemetry/providers
