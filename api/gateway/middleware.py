"""
API Gateway Middleware

Core middleware that handles:
- Request correlation ID injection
- Request lifecycle tracking
- Gateway metadata injection into request
- Response standardization
"""

import time
import uuid
from typing import Optional

from django.http import HttpResponse, JsonResponse
from django.utils.deprecation import MiddlewareMixin

from .models import APICallLog


class APIGatewayMiddleware(MiddlewareMixin):
    """
    Layer 7 API Gateway middleware providing:
    - Request correlation and tracing
    - Structured request logging
    - Gateway metadata injection
    - Response time tracking
    """

    GATEWAY_VERSION = "1.0.0"

    def process_request(self, request):
        # Inject correlation ID
        request.correlation_id = (
            request.headers.get("X-Correlation-ID")
            or request.headers.get("X-Request-ID")
            or str(uuid.uuid4())
        )
        request.request_id = str(uuid.uuid4())
        request.gateway_start_time = time.time() * 1000  # ms

        # Extract tenant info from headers or auth
        request.tenant_id = self._extract_tenant_id(request)
        request.api_version = request.headers.get("X-API-Version", "v1")

        # Mark as API request if path starts with /api/
        request.is_api_request = request.path.startswith("/api/")

        return None

    def process_response(self, request, response):
        if not getattr(request, "is_api_request", False):
            return response

        # Calculate duration
        duration_ms = None
        if hasattr(request, "gateway_start_time"):
            duration_ms = int(time.time() * 1000 - request.gateway_start_time)

        # Add gateway headers
        response["X-Request-ID"] = getattr(request, "request_id", "")
        response["X-Correlation-ID"] = getattr(request, "correlation_id", "")
        response["X-Gateway-Version"] = self.GATEWAY_VERSION

        if duration_ms is not None:
            response["X-Response-Time-Ms"] = str(duration_ms)

        # Async log the API call (don't block response)
        try:
            self._log_request(request, response, duration_ms)
        except Exception:
            # Never fail the request due to logging issues
            pass

        return response

    def process_exception(self, request, exception):
        if not getattr(request, "is_api_request", False):
            return None

        # Log exception
        try:
            duration_ms = None
            if hasattr(request, "gateway_start_time"):
                duration_ms = int(time.time() * 1000 - request.gateway_start_time)

            APICallLog.objects.create(
                request_id=getattr(request, "request_id", str(uuid.uuid4())),
                correlation_id=getattr(request, "correlation_id", None),
                method=request.method,
                path=request.path[:500],
                version=getattr(request, "api_version", "v1"),
                query_params=dict(request.GET),
                tenant_id=getattr(request, "tenant_id", None),
                user_id=str(request.user.id) if request.user.is_authenticated else None,
                started_at=timezone.now(),
                duration_ms=duration_ms,
                status_code=500,
                error_type=type(exception).__name__,
                error_message=str(exception)[:1000],
            )
        except Exception:
            pass

        return None

    def _extract_tenant_id(self, request) -> Optional[str]:
        """Extract tenant ID from request headers or authentication."""
        # Priority: header > auth token > subdomain
        tenant_header = request.headers.get("X-Tenant-ID")
        if tenant_header:
            return tenant_header

        # Extract from auth token if authenticated
        if request.user.is_authenticated:
            # Check if user has a tenant attribute (from multi-tenancy)
            tenant = getattr(request.user, "tenant_id", None)
            if tenant:
                return str(tenant)

        # Extract from subdomain (e.g., tenant.ikolu.smarthydro.app)
        host = request.get_host()
        if "." in host:
            subdomain = host.split(".")[0]
            if subdomain not in ("api", "www", "ikolu"):
                return subdomain

        return None

    def _log_request(self, request, response, duration_ms: Optional[int]):
        """Create structured API call log entry."""
        from django.utils import timezone

        APICallLog.objects.create(
            request_id=getattr(request, "request_id", str(uuid.uuid4())),
            correlation_id=getattr(request, "correlation_id", None),
            method=request.method,
            path=request.path[:500],
            version=getattr(request, "api_version", "v1"),
            query_params=dict(request.GET),
            tenant_id=getattr(request, "tenant_id", None),
            user_id=str(request.user.id) if request.user.is_authenticated else None,
            started_at=timezone.now(),
            duration_ms=duration_ms,
            status_code=response.status_code,
            response_size_bytes=len(response.content) if hasattr(response, "content") else None,
            endpoint_name=self._resolve_endpoint_name(request),
            tags=self._extract_tags(request),
        )

    def _resolve_endpoint_name(self, request) -> Optional[str]:
        """Resolve the endpoint name from URL resolver."""
        try:
            if hasattr(request, "resolver_match") and request.resolver_match:
                return request.resolver_match.view_name
        except Exception:
            pass
        return None

    def _extract_tags(self, request) -> list:
        """Extract classification tags from request."""
        tags = []
        path = request.path

        if "/telemetry/" in path:
            tags.append("telemetry")
        elif "/compliance/" in path:
            tags.append("compliance")
        elif "/crm/" in path:
            tags.append("crm")
        elif "/documents/" in path:
            tags.append("documents")
        elif "/chatbot/" in path:
            tags.append("ai")

        if request.method in ("POST", "PUT", "PATCH"):
            tags.append("write")
        elif request.method == "GET":
            tags.append("read")
        elif request.method == "DELETE":
            tags.append("delete")

        return tags
