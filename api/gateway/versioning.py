"""
API Versioning System

Provides semantic API versioning with:
- Header-based version selection (X-API-Version)
- URL path-based versioning fallback
- Deprecation warnings for old versions
- Version feature mapping

Version policy:
- v1: Legacy API (stable, deprecated)
- v2: Current unified API (stable)
- v3: Next-gen with GraphQL support (beta)
"""

import logging
from typing import Optional

from rest_framework.versioning import BaseVersioning
from rest_framework.exceptions import NotAcceptable

logger = logging.getLogger("api.gateway")


class APIVersioning(BaseVersioning):
    """
    Semantic API versioning using X-API-Version header.

    Supported versions:
    - v1: Legacy endpoints (maintenance mode)
    - v2: Current unified API (recommended)
    - v3: Enhanced API with new features (preview)

    Default: v2
    """

    DEFAULT_VERSION = "v2"
    ALLOWED_VERSIONS = ["v1", "v2", "v3"]
    DEPRECATED_VERSIONS = ["v1"]
    VERSION_PARAMETER = "X-API-Version"

    # Feature mapping per version
    FEATURES = {
        "v1": {
            "telemetry": "basic",
            "compliance": "basic",
            "crm": False,
            "documents": False,
            "chatbot": False,
            "websocket": False,
            "batch": False,
        },
        "v2": {
            "telemetry": "advanced",
            "compliance": "advanced",
            "crm": True,
            "documents": True,
            "chatbot": True,
            "websocket": True,
            "batch": True,
        },
        "v3": {
            "telemetry": "advanced",
            "compliance": "advanced",
            "crm": True,
            "documents": True,
            "chatbot": True,
            "websocket": True,
            "batch": True,
            "graphql": True,
            "realtime": True,
        },
    }

    def determine_version(self, request, *args, **kwargs):
        version = self.DEFAULT_VERSION

        # Priority 1: Header
        header_version = request.headers.get(self.VERSION_PARAMETER)
        if header_version:
            version = header_version.lower().lstrip("v")
            version = f"v{version}"

        # Priority 2: Query parameter
        elif "api_version" in request.query_params:
            version = request.query_params["api_version"].lower()
            if not version.startswith("v"):
                version = f"v{version}"

        # Priority 3: URL path (e.g., /api/v2/...)
        else:
            path_version = self._extract_from_path(request.path)
            if path_version:
                version = path_version

        # Validate
        if version not in self.ALLOWED_VERSIONS:
            raise NotAcceptable(
                detail={
                    "error": "Unsupported API version",
                    "requested_version": version,
                    "supported_versions": self.ALLOWED_VERSIONS,
                    "default_version": self.DEFAULT_VERSION,
                }
            )

        # Attach to request
        request.api_version = version

        # Warn if deprecated
        if version in self.DEPRECATED_VERSIONS:
            request._gateway_deprecated_version = version
            logger.warning(f"Deprecated API version {version} used by {request.path}")

        return version

    def _extract_from_path(self, path: str) -> Optional[str]:
        """Extract version from URL path like /api/v2/..."""
        parts = path.split("/")
        for part in parts:
            if part.startswith("v") and part[1:].isdigit():
                return part
        return None

    @classmethod
    def get_features(cls, version: str) -> dict:
        """Get feature availability for a version."""
        return cls.FEATURES.get(version, cls.FEATURES[cls.DEFAULT_VERSION])

    @classmethod
    def is_feature_available(cls, version: str, feature: str) -> bool:
        """Check if a feature is available in a version."""
        features = cls.get_features(version)
        return features.get(feature, False)
