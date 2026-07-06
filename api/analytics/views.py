"""
Analytics API Views

Dashboard endpoints for metrics visualization.
"""

from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response

from .models import APIUsageAggregate, EndpointHealthScore, APIDashboardSnapshot
from .services import DashboardService


@api_view(["GET"])
@permission_classes([IsAdminUser])
def usage_metrics(request):
    """
    Get API usage metrics.

    Query params:
        time_range: 1h, 6h, 24h, 7d, 30d (default: 24h)
        endpoint: Filter by endpoint name
        tenant: Filter by tenant ID
    """
    time_range = request.query_params.get("time_range", "24h")
    endpoint = request.query_params.get("endpoint")
    tenant = request.query_params.get("tenant")

    # Return latest snapshot or compute new one
    snapshot = APIDashboardSnapshot.objects.filter(
        time_range=time_range,
    ).order_by("-snapshot_time").first()

    if not snapshot:
        snapshot = DashboardService.compute_snapshot(time_range)

    return Response({
        "time_range": time_range,
        "snapshot_time": snapshot.snapshot_time,
        "total_requests": snapshot.total_requests,
        "total_errors": snapshot.total_errors,
        "top_endpoints": snapshot.top_endpoints,
        "top_tenants": snapshot.top_tenants,
        "module_breakdown": snapshot.module_breakdown,
    })


@api_view(["GET"])
@permission_classes([IsAdminUser])
def performance_metrics(request):
    """
    Get API performance metrics.

    Query params:
        time_range: 1h, 6h, 24h, 7d (default: 24h)
        endpoint: Filter by endpoint
    """
    time_range = request.query_params.get("time_range", "24h")

    snapshot = APIDashboardSnapshot.objects.filter(
        time_range=time_range,
    ).order_by("-snapshot_time").first()

    if not snapshot:
        snapshot = DashboardService.compute_snapshot(time_range)

    return Response({
        "time_range": time_range,
        "avg_latency_ms": snapshot.avg_latency_ms,
        "p95_latency_ms": snapshot.p95_latency_ms,
        "p99_latency_ms": snapshot.p99_latency_ms,
        "throughput_rps": round(snapshot.total_requests / 86400, 2) if time_range == "24h" else None,
    })


@api_view(["GET"])
@permission_classes([IsAdminUser])
def health_scores(request):
    """
    Get health scores for all endpoints.

    Query params:
        status: Filter by health status (healthy, degraded, unhealthy, critical)
        module: Filter by module name
    """
    status_filter = request.query_params.get("status")
    module = request.query_params.get("module")

    scores = EndpointHealthScore.objects.all()

    if status_filter:
        scores = scores.filter(health_status=status_filter)
    if module:
        scores = scores.filter(module_name=module)

    scores = scores.order_by("-health_score")

    return Response({
        "count": scores.count(),
        "endpoints": [
            {
                "name": s.endpoint_name,
                "module": s.module_name,
                "health_score": s.health_score,
                "status": s.health_status,
                "availability": s.availability_score,
                "latency": s.latency_score,
                "error_rate": s.error_rate_score,
                "throughput": s.throughput_score,
                "calculated_at": s.calculated_at,
            }
            for s in scores
        ],
    })


@api_view(["GET"])
@permission_classes([IsAdminUser])
def dashboard(request):
    """
    Get consolidated dashboard with all metrics.

    Query params:
        time_range: 1h, 6h, 24h, 7d, 30d (default: 24h)
    """
    time_range = request.query_params.get("time_range", "24h")

    snapshot = APIDashboardSnapshot.objects.filter(
        time_range=time_range,
    ).order_by("-snapshot_time").first()

    if not snapshot:
        snapshot = DashboardService.compute_snapshot(time_range)

    return Response({
        "generated_at": snapshot.snapshot_time,
        "time_range": snapshot.time_range,
        "summary": {
            "total_requests": snapshot.total_requests,
            "total_errors": snapshot.total_errors,
            "error_rate": round(snapshot.total_errors / snapshot.total_requests * 100, 2)
            if snapshot.total_requests > 0 else 0,
            "avg_latency_ms": snapshot.avg_latency_ms,
            "p95_latency_ms": snapshot.p95_latency_ms,
            "p99_latency_ms": snapshot.p99_latency_ms,
        },
        "health_overview": {
            "healthy": snapshot.healthy_endpoints,
            "degraded": snapshot.degraded_endpoints,
            "unhealthy": snapshot.unhealthy_endpoints,
            "critical": snapshot.critical_endpoints,
        },
        "top_endpoints": snapshot.top_endpoints[:5],
        "top_tenants": snapshot.top_tenants[:5],
        "module_breakdown": snapshot.module_breakdown,
    })
