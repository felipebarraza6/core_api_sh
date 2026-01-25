
# PROXY FOR BACKWARD COMPATIBILITY
# Moved to api.ingestion.services.provider_manager
import warnings
from api.ingestion.services.provider_manager import *

warnings.warn(
    "api.telemetry.providers.manager is deprecated. Use api.ingestion.services.provider_manager instead.",
    DeprecationWarning,
    stacklevel=2
)
