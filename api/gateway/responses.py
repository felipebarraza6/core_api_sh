"""
Standardized API Gateway Responses

Provides consistent response format across all API versions:
- Unified envelope structure
- Gateway metadata
- Error standardization
- Pagination wrapper
- Hypermedia links (HATEOAS)

Response format:
{
    "data": { ... },
    "meta": {
        "api_version": "v2",
        "gateway_version": "1.0.0",
        "request_id": "uuid",
        "timestamp": "2026-01-01T00:00:00Z",
        "duration_ms": 45
    },
    "links": {
        "self": "/api/v2/telemetry/",
        "next": "/api/v2/telemetry/?page=2",
        "prev": null
    }
}
"""

import time
import uuid
from datetime import datetime, timezone as dt_timezone
from typing import Any, Dict, List, Optional

from django.http import JsonResponse
from rest_framework.response import Response


class GatewayResponseBuilder:
    """Builder for standardized gateway responses."""

    GATEWAY_VERSION = "1.0.0"

    def __init__(self):
        self._data = None
        self._meta = {}
        self._links = {}
        self._errors = None
        self._status_code = 200

    def data(self, data: Any) -> "GatewayResponseBuilder":
        self._data = data
        return self

    def meta(
        self,
        api_version: str = "v2",
        request_id: str = None,
        duration_ms: int = None,
        **kwargs
    ) -> "GatewayResponseBuilder":
        self._meta = {
            "api_version": api_version,
            "gateway_version": self.GATEWAY_VERSION,
            "request_id": request_id or str(uuid.uuid4()),
            "timestamp": datetime.now(dt_timezone.utc).isoformat(),
            **kwargs,
        }
        if duration_ms is not None:
            self._meta["duration_ms"] = duration_ms
        return self

    def links(
        self,
        self_url: str = None,
        next_url: str = None,
        prev_url: str = None,
        **kwargs
    ) -> "GatewayResponseBuilder":
        self._links = {}
        if self_url:
            self._links["self"] = self_url
        if next_url:
            self._links["next"] = next_url
        if prev_url:
            self._links["prev"] = prev_url
        self._links.update(kwargs)
        return self

    def pagination(
        self,
        page: int,
        page_size: int,
        total_count: int,
        total_pages: int,
        base_url: str,
    ) -> "GatewayResponseBuilder":
        self._meta["pagination"] = {
            "page": page,
            "page_size": page_size,
            "total_count": total_count,
            "total_pages": total_pages,
        }

        self._links["self"] = f"{base_url}?page={page}"
        if page < total_pages:
            self._links["next"] = f"{base_url}?page={page + 1}"
        if page > 1:
            self._links["prev"] = f"{base_url}?page={page - 1}"
        self._links["first"] = f"{base_url}?page=1"
        self._links["last"] = f"{base_url}?page={total_pages}"

        return self

    def errors(
        self,
        errors: List[Dict] = None,
        error_code: str = None,
        error_message: str = None,
        status_code: int = 400,
    ) -> "GatewayResponseBuilder":
        if errors:
            self._errors = errors
        elif error_code or error_message:
            self._errors = [{"code": error_code, "message": error_message}]
        self._status_code = status_code
        return self

    def build(self) -> Dict:
        response = {}

        if self._data is not None:
            response["data"] = self._data
        if self._meta:
            response["meta"] = self._meta
        if self._links:
            response["links"] = self._links
        if self._errors:
            response["errors"] = self._errors

        return response

    def to_drf_response(self) -> Response:
        return Response(self.build(), status=self._status_code)

    def to_json_response(self) -> JsonResponse:
        return JsonResponse(self.build(), status=self._status_code)


def gateway_response(
    data: Any = None,
    api_version: str = "v2",
    request=None,
    status_code: int = 200,
    **kwargs
) -> Response:
    """
    Helper function to create standardized gateway responses.

    Usage:
        return gateway_response(
            data={"points": [...]},
            request=request,
            status_code=200
        )
    """
    builder = GatewayResponseBuilder()

    duration_ms = None
    if request and hasattr(request, "gateway_start_time"):
        duration_ms = int((time.time() * 1000) - request.gateway_start_time)

    request_id = getattr(request, "request_id", str(uuid.uuid4())) if request else str(uuid.uuid4())

    builder.data(data).meta(
        api_version=getattr(request, "api_version", api_version),
        request_id=request_id,
        duration_ms=duration_ms,
        **kwargs,
    )

    return Response(builder.build(), status=status_code)


def gateway_error_response(
    error_code: str,
    error_message: str,
    status_code: int = 400,
    request=None,
    details: Dict = None,
) -> Response:
    """Create standardized error response."""
    builder = GatewayResponseBuilder()

    duration_ms = None
    if request and hasattr(request, "gateway_start_time"):
        duration_ms = int((time.time() * 1000) - request.gateway_start_time)

    request_id = getattr(request, "request_id", str(uuid.uuid4())) if request else str(uuid.uuid4())

    builder.errors(
        error_code=error_code,
        error_message=error_message,
        status_code=status_code,
    ).meta(
        api_version=getattr(request, "api_version", "v2"),
        request_id=request_id,
        duration_ms=duration_ms,
    )

    if details:
        builder._meta["error_details"] = details

    return Response(builder.build(), status=status_code)
