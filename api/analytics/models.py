"""
Analytics Models

Stores aggregated metrics for API usage, performance, and health scoring.
Uses time-bucketed aggregation for efficient querying.
"""

import uuid
from datetime import timedelta

from django.db import models
from django.utils import timezone


class TimeBucket(models.TextChoices):
    MINUTE = "1m", "1 Minute"
    FIVE_MINUTES = "5m", "5 Minutes"
    HOUR = "1h", "1 Hour"
    DAY = "1d", "1 Day"


class APIUsageAggregate(models.Model):
    """
    Pre-aggregated API usage metrics by time bucket.
    Enables fast dashboard queries without scanning raw logs.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Dimensions
    bucket_size = models.CharField(max_length=5, choices=TimeBucket.choices)
    bucket_time = models.DateTimeField(db_index=True)

    endpoint_name = models.CharField(max_length=200, db_index=True)
    method = models.CharField(max_length=10)
    api_version = models.CharField(max_length=10, default="v2")

    tenant_id = models.CharField(max_length=100, db_index=True, null=True, blank=True)
    module_name = models.CharField(max_length=100, db_index=True, null=True, blank=True)

    # Metrics
    request_count = models.PositiveIntegerField(default=0)
    error_count = models.PositiveIntegerField(default=0)
    total_duration_ms = models.PositiveBigIntegerField(default=0)
    max_duration_ms = models.PositiveIntegerField(default=0)
    min_duration_ms = models.PositiveIntegerField(null=True, blank=True)
    response_size_total = models.PositiveBigIntegerField(default=0)

    # Status code distribution (denormalized)
    status_2xx_count = models.PositiveIntegerField(default=0)
    status_3xx_count = models.PositiveIntegerField(default=0)
    status_4xx_count = models.PositiveIntegerField(default=0)
    status_5xx_count = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "analytics_usage_aggregate"
        verbose_name = "API Usage Aggregate"
        verbose_name_plural = "API Usage Aggregates"
        indexes = [
            models.Index(fields=["bucket_size", "bucket_time", "endpoint_name"]),
            models.Index(fields=["tenant_id", "bucket_size", "bucket_time"]),
            models.Index(fields=["module_name", "bucket_size", "bucket_time"]),
        ]
        unique_together = [
            ["bucket_size", "bucket_time", "endpoint_name", "method", "tenant_id"],
        ]

    def __str__(self):
        return f"{self.endpoint_name} {self.method} @ {self.bucket_time}"

    @property
    def avg_duration_ms(self):
        if self.request_count == 0:
            return 0
        return self.total_duration_ms // self.request_count

    @property
    def error_rate(self):
        if self.request_count == 0:
            return 0.0
        return round(self.error_count / self.request_count * 100, 2)

    @property
    def throughput_rps(self):
        """Requests per second in this bucket."""
        bucket_seconds = {
            "1m": 60,
            "5m": 300,
            "1h": 3600,
            "1d": 86400,
        }
        seconds = bucket_seconds.get(self.bucket_size, 60)
        return round(self.request_count / seconds, 2)


class EndpointHealthScore(models.Model):
    """
    Health score tracking for API endpoints.
    Score range: 0-100 (0=dead, 100=perfect health)
    """

    HEALTH_STATUS = [
        ("healthy", "Healthy"),       # 80-100
        ("degraded", "Degraded"),     # 50-79
        ("unhealthy", "Unhealthy"),   # 20-49
        ("critical", "Critical"),      # 0-19
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    endpoint_name = models.CharField(max_length=200, unique=True, db_index=True)
    module_name = models.CharField(max_length=100, db_index=True)

    # Current score
    health_score = models.PositiveSmallIntegerField(default=100)
    health_status = models.CharField(
        max_length=20,
        choices=HEALTH_STATUS,
        default="healthy",
        db_index=True,
    )

    # Component scores (0-100 each)
    availability_score = models.PositiveSmallIntegerField(default=100)
    latency_score = models.PositiveSmallIntegerField(default=100)
    error_rate_score = models.PositiveSmallIntegerField(default=100)
    throughput_score = models.PositiveSmallIntegerField(default=100)

    # Thresholds
    latency_p95_threshold_ms = models.PositiveIntegerField(default=1000)
    error_rate_threshold_percent = models.FloatField(default=5.0)
    availability_threshold_percent = models.FloatField(default=99.0)

    # History (last 24h scores stored as JSON)
    score_history = models.JSONField(
        default=list,
        help_text="Last 24h scores: [{time, score}, ...]"
    )

    # Alert tracking
    last_alert_at = models.DateTimeField(null=True, blank=True)
    alert_count_24h = models.PositiveIntegerField(default=0)

    # Last calculation
    calculated_at = models.DateTimeField(auto_now=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "analytics_endpoint_health"
        verbose_name = "Endpoint Health Score"
        verbose_name_plural = "Endpoint Health Scores"
        indexes = [
            models.Index(fields=["health_status", "calculated_at"]),
            models.Index(fields=["module_name", "health_score"]),
        ]

    def __str__(self):
        return f"{self.endpoint_name}: {self.health_score}/100 ({self.health_status})"

    def calculate_score(self):
        """
        Calculate composite health score from components.
        Weights: availability 40%, latency 30%, error rate 20%, throughput 10%
        """
        weights = {
            "availability": 0.40,
            "latency": 0.30,
            "error_rate": 0.20,
            "throughput": 0.10,
        }

        self.health_score = int(
            self.availability_score * weights["availability"] +
            self.latency_score * weights["latency"] +
            self.error_rate_score * weights["error_rate"] +
            self.throughput_score * weights["throughput"]
        )

        # Update status
        if self.health_score >= 80:
            self.health_status = "healthy"
        elif self.health_score >= 50:
            self.health_status = "degraded"
        elif self.health_score >= 20:
            self.health_status = "unhealthy"
        else:
            self.health_status = "critical"

        # Update history
        self.score_history.append({
            "time": timezone.now().isoformat(),
            "score": self.health_score,
        })
        # Keep only last 24h entries (assuming hourly updates)
        self.score_history = self.score_history[-24:]

        self.save()
        return self.health_score


class APIDashboardSnapshot(models.Model):
    """
    Pre-computed dashboard snapshots for fast loading.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    snapshot_time = models.DateTimeField(auto_now_add=True, db_index=True)
    time_range = models.CharField(max_length=20)  # 1h, 6h, 24h, 7d, 30d

    # Summary metrics
    total_requests = models.PositiveIntegerField(default=0)
    total_errors = models.PositiveIntegerField(default=0)
    avg_latency_ms = models.PositiveIntegerField(default=0)
    p95_latency_ms = models.PositiveIntegerField(default=0)
    p99_latency_ms = models.PositiveIntegerField(default=0)

    # Top data (stored as JSON)
    top_endpoints = models.JSONField(default=list)
    top_tenants = models.JSONField(default=list)
    top_errors = models.JSONField(default=list)

    # Module breakdown
    module_breakdown = models.JSONField(default=dict)

    # Health overview
    healthy_endpoints = models.PositiveIntegerField(default=0)
    degraded_endpoints = models.PositiveIntegerField(default=0)
    unhealthy_endpoints = models.PositiveIntegerField(default=0)
    critical_endpoints = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "analytics_dashboard_snapshots"
        verbose_name = "Dashboard Snapshot"
        verbose_name_plural = "Dashboard Snapshots"
        indexes = [
            models.Index(fields=["time_range", "snapshot_time"]),
        ]

    def __str__(self):
        return f"Dashboard {self.time_range} @ {self.snapshot_time}"
