
# PROXY FOR BACKWARD COMPATIBILITY
# Moved to api.ingestion.mqtt.handler
import warnings
from api.ingestion.mqtt.handler import *

warnings.warn(
    "api.telemetry.providers.mqtt_handler is deprecated. Use api.ingestion.mqtt.handler instead.",
    DeprecationWarning,
    stacklevel=2
)
