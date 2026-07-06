"""
API Gateway Module for SmartHydro Core API

Provides enterprise-grade API management capabilities:
- Semantic API versioning (v1/v2/v3)
- Circuit breaker pattern for external providers
- Multi-tenant rate limiting
- Request lifecycle management and correlation
- Standardized gateway responses

Architecture: Layer 7 gateway pattern sitting between Django URL router
and view layers, providing cross-cutting concerns for all API endpoints.
"""

__version__ = "1.0.0"
