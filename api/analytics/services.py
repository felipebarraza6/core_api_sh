"""
Analytics Services

Core business logic for metrics aggregation, health scoring,
and dashboard computation.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from django.db.models import Avg, Count, Max, Min, Q, Sum
from django.utils import timezone

from api.gateway.models import APICallLog

from .models import (
    APIUsageAggregate,
    EndpointHealthScore,
    APIDashboardSnapshot,
    TimeBucket,
)

logger = logging.getLogger("api.analytics")


class UsageAggregator:
    """Aggregates raw API call logs into time-bucketed metrics."""

    @classmethod
    def aggregate_minute(cls, target_time: Optional[datetime] = None):
        """Aggregate logs into 1-minute buckets."""
        target_time = target_time or timezone.now()
        bucket_time = target_time.replace(second=0, microsecond=0)

        # Get logs for this minute
        logs = APICallLog.objects.filter(
            created_at__gte=bucket_time,
            created_at__lt=bucket_time + timedelta(minutes=1),
        )

        # Group and aggregate
        groups = {}
        for log in logs:
            key = (log.endpoint_name, log.method, log.version, log.tenant_id)
            if key not in groups:
                groups[key] = []
            groups[key].append(log)

        for (endpoint, method, version, tenant), group_logs in groups.items():
            cls._create_aggregate(
                bucket_size=TimeBucket.MINUTE,
                bucket_time=bucket_time,
                endpoint=endpoint or "unknown",
                method=method,
                version=version,
                tenant=tenant,
                logs=group_logs,
            )

    @classmethod
    def aggregate_hour(cls, target_time: Optional[datetime] = None):
        """Roll up minute aggregates into hour buckets."""
        target_time = target_time or timezone.now()
        hour_start = target_time.replace(minute=0, second=0, microsecond=0)

        # Aggregate from minute buckets
        minutes = APIUsageAggregate.objects.filter(
            bucket_size=TimeBucket.MINUTE,
            bucket_time__gte=hour_start,
            bucket_time__lt=hour_start + timedelta(hours=1),
        )

        cls._rollup_aggregates(minutes, TimeBucket.HOUR, hour_start)

    @classmethod
    def aggregate_day(cls, target_time: Optional[datetime] = None):
        """Roll up hour aggregates into day buckets."""
        target_time = target_time or timezone.now()
        day_start = target_time.replace(hour=0, minute=0, second=0, microsecond=0)

        hours = APIUsageAggregate.objects.filter(
            bucket_size=TimeBucket.HOUR,
            bucket_time__gte=day_start,
            bucket_time__lt=day_start + timedelta(days=1),
        )

        cls._rollup_aggregates(hours, TimeBucket.DAY, day_start)

    @classmethod
    def _create_aggregate(cls, bucket_size, bucket_time, endpoint, method,
                          version, tenant, logs):
        """Create or update an aggregate record."""
        if not logs:
            return

        request_count = len(logs)
        error_count = sum(1 for l in logs if l.status_code and l.status_code >= 400)
        durations = [l.duration_ms for l in logs if l.duration_ms is not None]
        response_sizes = [l.response_size_bytes for l in logs
                         if l.response_size_bytes is not None]

        status_2xx = sum(1 for l in logs if l.status_code and 200 <= l.status_code < 300)
        status_3xx = sum(1 for l in logs if l.status_code and 300 <= l.status_code < 400)
        status_4xx = sum(1 for l in logs if l.status_code and 400 <= l.status_code < 500)
        status_5xx = sum(1 for l in logs if l.status_code and 500 <= l.status_code < 600)

        # Extract module from endpoint
        module = cls._extract_module(endpoint)

        aggregate, _ = APIUsageAggregate.objects.get_or_create(
            bucket_size=bucket_size,
            bucket_time=bucket_time,
            endpoint_name=endpoint,
            method=method,
            tenant_id=tenant,
            defaults={
                "api_version": version,
                "module_name": module,
            },
        )

        aggregate.request_count += request_count
        aggregate.error_count += error_count
        aggregate.total_duration_ms += sum(durations) if durations else 0
        aggregate.max_duration_ms = max(
            aggregate.max_duration_ms,
            max(durations) if durations else 0,
        )
        if durations:
            current_min = aggregate.min_duration_ms or float('inf')
            aggregate.min_duration_ms = min(current_min, min(durations))
        aggregate.response_size_total += sum(response_sizes) if response_sizes else 0
        aggregate.status_2xx_count += status_2xx
        aggregate.status_3xx_count += status_3xx
        aggregate.status_4xx_count += status_4xx
        aggregate.status_5xx_count += status_5xx

        aggregate.save()

    @classmethod
    def _rollup_aggregates(cls, source_aggregates, target_bucket, target_time):
        """Roll up smaller buckets into larger ones."""
        groups = {}
        for agg in source_aggregates:
            key = (agg.endpoint_name, agg.method, agg.api_version, agg.tenant_id)
            if key not in groups:
                groups[key] = []
            groups[key].append(agg)

        for (endpoint, method, version, tenant), aggs in groups.items():
            total_requests = sum(a.request_count for a in aggs)
            total_errors = sum(a.error_count for a in aggs)
            total_duration = sum(a.total_duration_ms for a in aggs)
            max_duration = max((a.max_duration_ms for a in aggs), default=0)
            min_durations = [a.min_duration_ms for a in aggs if a.min_duration_ms]
            total_response_size = sum(a.response_size_total for a in aggs)

            APIUsageAggregate.objects.update_or_create(
                bucket_size=target_bucket,
                bucket_time=target_time,
                endpoint_name=endpoint,
                method=method,
                tenant_id=tenant,
                defaults={
                    "api_version": version,
                    "module_name": aggs[0].module_name if aggs else None,
                    "request_count": total_requests,
                    "error_count": total_errors,
                    "total_duration_ms": total_duration,
                    "max_duration_ms": max_duration,
                    "min_duration_ms": min(min_durations) if min_durations else None,
                    "response_size_total": total_response_size,
                    "status_2xx_count": sum(a.status_2xx_count for a in aggs),
                    "status_3xx_count": sum(a.status_3xx_count for a in aggs),
                    "status_4xx_count": sum(a.status_4xx_count for a in aggs),
                    "status_5xx_count": sum(a.status_5xx_count for a in aggs),
                },
            )

    @staticmethod
    def _extract_module(endpoint_name: str) -> Optional[str]:
        """Extract module name from endpoint."""
        if not endpoint_name:
            return None
        parts = endpoint_name.split(".")
        if len(parts) > 1:
            return parts[0]
        if "telemetry" in endpoint_name:
            return "telemetry"
        elif "compliance" in endpoint_name:
            return "compliance"
        elif "crm" in endpoint_name:
            return "crm"
        elif "documents" in endpoint_name:
            return "documents"
        elif "chatbot" in endpoint_name:
            return "chatbot"
        return "core"


class HealthScorer:
    """Calculates health scores for API endpoints."""

    @classmethod
    def calculate_all(cls):
        """Calculate health scores for all tracked endpoints."""
        scores = EndpointHealthScore.objects.all()

        for score in scores:
            cls._calculate_endpoint(score)

    @classmethod
    def _calculate_endpoint(cls, score: EndpointHealthScore):
        """Calculate component scores for a single endpoint."""
        now = timezone.now()
        last_hour = now - timedelta(hours=1)

        # Get recent aggregates
        aggregates = APIUsageAggregate.objects.filter(
            endpoint_name=score.endpoint_name,
            bucket_size=TimeBucket.HOUR,
            bucket_time__gte=last_hour,
        )

        if not aggregates.exists():
            # No data - assume healthy
            score.availability_score = 100
            score.latency_score = 100
            score.error_rate_score = 100
            score.throughput_score = 100
            score.calculate_score()
            return

        total_requests = sum(a.request_count for a in aggregates)
        total_errors = sum(a.error_count for a in aggregates)
        avg_duration = (sum(a.total_duration_ms for a in aggregates) // total_requests
                       if total_requests > 0 else 0)

        # Availability score (based on 5xx rate)
        server_errors = sum(a.status_5xx_count for a in aggregates)
        if total_requests > 0:
            availability = (1 - server_errors / total_requests) * 100
        else:
            availability = 100
        score.availability_score = int(availability)

        # Latency score
        if avg_duration <= score.latency_p95_threshold_ms * 0.5:
            score.latency_score = 100
        elif avg_duration <= score.latency_p95_threshold_ms:
            score.latency_score = 80
        elif avg_duration <= score.latency_p95_threshold_ms * 2:
            score.latency_score = 50
        elif avg_duration <= score.latency_p95_threshold_ms * 5:
            score.latency_score = 20
        else:
            score.latency_score = 0

        # Error rate score
        if total_requests > 0:
            error_rate = (total_errors / total_requests) * 100
        else:
            error_rate = 0

        if error_rate <= score.error_rate_threshold_percent * 0.2:
            score.error_rate_score = 100
        elif error_rate <= score.error_rate_threshold_percent:
            score.error_rate_score = 80
        elif error_rate <= score.error_rate_threshold_percent * 3:
            score.error_rate_score = 40
        else:
            score.error_rate_score = 0

        # Throughput score (relative to historical average)
        score.throughput_score = 100  # Simplified - could compare to historical

        score.calculate_score()


class DashboardService:
    """Computes dashboard snapshots."""

    @classmethod
    def compute_snapshot(cls, time_range: str = "24h"):
        """Compute a dashboard snapshot for the given time range."""
        now = timezone.now()

        # Parse time range
        range_map = {
            "1h": timedelta(hours=1),
            "6h": timedelta(hours=6),
            "24h": timedelta(hours=24),
            "7d": timedelta(days=7),
            "30d": timedelta(days=30),
        }
        delta = range_map.get(time_range, timedelta(hours=24))
        start_time = now - delta

        # Get aggregates
        aggregates = APIUsageAggregate.objects.filter(
            bucket_time__gte=start_time,
        )

        # Summary metrics
        total_requests = sum(a.request_count for a in aggregates)
        total_errors = sum(a.error_count for a in aggregates)

        durations = []
        for a in aggregates:
            if a.request_count > 0 and a.total_duration_ms:
                durations.extend([a.avg_duration_ms] * a.request_count)

        avg_latency = sum(durations) // len(durations) if durations else 0
        p95_latency = cls._percentile(durations, 95) if durations else 0
        p99_latency = cls._percentile(durations, 99) if durations else 0

        # Top endpoints
        endpoint_stats = {}
        for a in aggregates:
            key = a.endpoint_name
            if key not in endpoint_stats:
                endpoint_stats[key] = {"count": 0, "errors": 0}
            endpoint_stats[key]["count"] += a.request_count
            endpoint_stats[key]["errors"] += a.error_count

        top_endpoints = sorted(
            [{"endpoint": k, **v} for k, v in endpoint_stats.items()],
            key=lambda x: x["count"],
            reverse=True,
        )[:10]

        # Top tenants
        tenant_stats = {}
        for a in aggregates:
            key = a.tenant_id or "anonymous"
            if key not in tenant_stats:
                tenant_stats[key] = {"count": 0}
            tenant_stats[key]["count"] += a.request_count

        top_tenants = sorted(
            [{"tenant": k, **v} for k, v in tenant_stats.items()],
            key=lambda x: x["count"],
            reverse=True,
        )[:10]

        # Module breakdown
        module_stats = {}
        for a in aggregates:
            key = a.module_name or "unknown"
            if key not in module_stats:
                module_stats[key] = {"count": 0, "errors": 0}
            module_stats[key]["count"] += a.request_count
            module_stats[key]["errors"] += a.error_count

        # Health overview
        health_scores = EndpointHealthScore.objects.all()
        healthy = sum(1 for h in health_scores if h.health_status == "healthy")
        degraded = sum(1 for h in health_scores if h.health_status == "degraded")
        unhealthy = sum(1 for h in health_scores if h.health_status == "unhealthy")
        critical = sum(1 for h in health_scores if h.health_status == "critical")

        snapshot = APIDashboardSnapshot.objects.create(
            time_range=time_range,
            total_requests=total_requests,
            total_errors=total_errors,
            avg_latency_ms=avg_latency,
            p95_latency_ms=p95_latency,
            p99_latency_ms=p99_latency,
            top_endpoints=top_endpoints,
            top_tenants=top_tenants,
            top_errors=[],
            module_breakdown=module_stats,
            healthy_endpoints=healthy,
            degraded_endpoints=degraded,
            unhealthy_endpoints=unhealthy,
            critical_endpoints=critical,
        )

        return snapshot

    @staticmethod
    def _percentile(data: List[int], percentile: int) -> int:
        """Calculate percentile value."""
        if not data:
            return 0
        sorted_data = sorted(data)
        index = int(len(sorted_data) * (percentile / 100))
        return sorted_data[min(index, len(sorted_data) - 1)]
