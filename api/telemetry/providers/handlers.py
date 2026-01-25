
# PROXY FOR BACKWARD COMPATIBILITY
# Moved to api.ingestion.services.provider_handlers
import warnings
from api.ingestion.services.provider_handlers import *

warnings.warn(
    "api.telemetry.providers.handlers is deprecated. Use api.ingestion.services.provider_handlers instead.",
    DeprecationWarning,
    stacklevel=2
)
