"""
Multi-Tenant Rate Limiting

Advanced throttling system providing:
- Per-tenant rate limits based on subscription tier
- Resource-specific limits (telemetry, compliance, exports)
- Burst handling with token bucket algorithm
- Endpoint-specific overrides
- Sliding window tracking

Tiers:
- free: 30 req/min, burst 5
- basic: 60 req/min, burst 10
- professional: 300 req/min, burst 30
- enterprise: 1000 req/min, burst 100
"""

import logging
import time
from typing import Optional

from django.core.cache import cache
from rest_framework.throttling import BaseThrottle
from rest_framework.exceptions import Throttled

from .models import TenantRateLimitConfig

logger = logging.getLogger("api.gateway.throttle")


class TenantRateThrottle(BaseThrottle):
    """
    Multi-tenant aware rate throttle with tier-based limits.

    Identifies tenant from:
    1. X-Tenant-ID header
    2. Authenticated user's tenant
    3. Subdomain

    Falls back to default limits if no tenant identified.
    """

    CACHE_PREFIX = "throttle"
    WINDOW_SIZE = 60  # 1 minute window

    # Default tier limits
    DEFAULT_LIMITS = {
        "free": {"rpm": 30, "burst": 5},
        "basic": {"rpm": 60, "burst": 10},
        "professional": {"rpm": 300, "burst": 30},
        "enterprise": {"rpm": 1000, "burst": 100},
    }

    def get_cache_key(self, request, view) -> str:
        """Generate cache key for rate limit tracking."""
        tenant_id = self._get_tenant_id(request) or "anonymous"
        endpoint = request.path.replace("/", "_")
        return f"{self.CACHE_PREFIX}:{tenant_id}:{endpoint}:{request.method}"

    def allow_request(self, request, view) -> bool:
        """Check if request is within rate limits."""
        tenant_id = self._get_tenant_id(request)

        # Get limits for tenant
        limits = self._get_tenant_limits(tenant_id, request)

        # Check resource-specific limits
        resource_limit = self._get_resource_limit(request, limits)
        if resource_limit:
            limits["rpm"] = min(limits["rpm"], resource_limit)

        # Apply endpoint override
        endpoint_override = self._get_endpoint_override(request, tenant_id)
        if endpoint_override:
            limits["rpm"] = endpoint_override

        cache_key = self.get_cache_key(request, view)
        window_start = int(time.time()) // self.WINDOW_SIZE * self.WINDOW_SIZE
        window_key = f"{cache_key}:{window_start}"

        # Get current count
        current_count = cache.get(window_key, 0)

        if current_count >= limits["rpm"]:
            # Check burst allowance
            burst_key = f"{cache_key}:burst"
            burst_tokens = cache.get(burst_key, limits["burst"])

            if burst_tokens <= 0:
                wait_time = self.WINDOW_SIZE - (int(time.time()) - window_start)
                raise Throttled(
                    detail={
                        "error": "Rate limit exceeded",
                        "limit": limits["rpm"],
                        "window": "1 minute",
                        "retry_after_seconds": wait_time,
                        "tenant": tenant_id or "default",
                        "tier": limits.get("tier", "default"),
                    },
                    wait=wait_time,
                )

            # Consume burst token
            cache.set(burst_key, burst_tokens - 1, self.WINDOW_SIZE)

        # Increment counter
        pipe = cache.client.pipeline() if hasattr(cache, "client") else None
        if pipe:
            pipe.incr(window_key)
            pipe.expire(window_key, self.WINDOW_SIZE)
            pipe.execute()
        else:
            try:
                cache.incr(window_key)
            except ValueError:
                cache.set(window_key, 1, self.WINDOW_SIZE)

        # Add rate limit headers to response
        request._throttle_limit = limits["rpm"]
        request._throttle_remaining = max(0, limits["rpm"] - current_count - 1)

        return True

    def _get_tenant_id(self, request) -> Optional[str]:
        """Extract tenant ID from request."""
        tenant = request.headers.get("X-Tenant-ID")
        if tenant:
            return tenant

        if request.user.is_authenticated:
            return getattr(request.user, "tenant_id", None)

        host = request.get_host()
        if "." in host:
            subdomain = host.split(".")[0]
            if subdomain not in ("api", "www", "ikolu"):
                return subdomain

        return None

    def _get_tenant_limits(self, tenant_id: Optional[str], request) -> dict:
        """Get rate limits for tenant."""
        if not tenant_id:
            return {"rpm": 30, "burst": 5, "tier": "anonymous"}

        # Try database config
        try:
            config = TenantRateLimitConfig.objects.filter(
                tenant_id=tenant_id,
                is_active=True,
            ).select_related().first()

            if config and config.is_valid():
                return {
                    "rpm": config.requests_per_minute,
                    "burst": config.burst_limit,
                    "tier": config.tier,
                    "telemetry": config.telemetry_limit_per_minute,
                    "compliance": config.compliance_limit_per_minute,
                    "export": config.export_limit_per_minute,
                    "custom": config.custom_limits,
                }
        except Exception:
            pass

        # Fallback to defaults
        if request.user.is_authenticated:
            return {"rpm": 60, "burst": 10, "tier": "basic"}

        return {"rpm": 30, "burst": 5, "tier": "anonymous"}

    def _get_resource_limit(self, request, limits: dict) -> Optional[int]:
        """Get resource-specific limit if applicable."""
        path = request.path

        if "/telemetry/" in path and "telemetry" in limits:
            return limits["telemetry"]
        elif "/compliance/" in path and "compliance" in limits:
            return limits["compliance"]
        elif "/documents/" in path and "export" in limits:
            return limits["export"]

        return None

    def _get_endpoint_override(self, request, tenant_id: Optional[str]) -> Optional[int]:
        """Check for endpoint-specific custom limits."""
        if not tenant_id:
            return None

        cache_key = f"throttle:override:{tenant_id}:{request.path}"
        override = cache.get(cache_key)
        return override


class BurstRateThrottle(TenantRateThrottle):
    """
    Burst throttle for handling traffic spikes.
    Allows short bursts beyond normal rate limits.
    """

    BURST_MULTIPLIER = 2
    BURST_DURATION = 10  # seconds

    def allow_request(self, request, view) -> bool:
        """Allow burst requests with separate bucket."""
        tenant_id = self._get_tenant_id(request)
        limits = self._get_tenant_limits(tenant_id, request)

        burst_limit = limits["burst"] * self.BURST_MULTIPLIER
        burst_key = f"{self.CACHE_PREFIX}:burst:{tenant_id or 'anon'}:{int(time.time()) // self.BURST_DURATION}"

        current_burst = cache.get(burst_key, 0)

        if current_burst >= burst_limit:
            # Fall through to regular throttle
            return super().allow_request(request, view)

        # Allow burst
        try:
            cache.incr(burst_key)
        except ValueError:
            cache.set(burst_key, 1, self.BURST_DURATION)

        return True
