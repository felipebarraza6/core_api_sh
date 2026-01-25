
# PROXY FOR BACKWARD COMPATIBILITY
# Moved to api.ingestion.mqtt.parser
import warnings
from api.ingestion.mqtt.parser import *

warnings.warn(
    "api.telemetry.providers.mqtt_parser is deprecated. Use api.ingestion.mqtt.parser instead.",
    DeprecationWarning,
    stacklevel=2
)
