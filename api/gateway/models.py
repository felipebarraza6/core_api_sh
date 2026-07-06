"""
Gateway models for tracking API usage, circuit breaker state,
and tenant rate limiting configuration.
"""

import uuid
from datetime import timedelta

from django.db import models
from django.utils import timezone


class CircuitState(models.TextChoices):
    CLOSED = "closed", "Closed"
    OPEN = "open", "Open"
    HALF_OPEN = "half_open", "Half-Open"


class CircuitBreakerLog(models.Model):
    """
    Tracks circuit breaker state transitions for external providers.
    Each provider (DGA, SMA, MQTT, etc.) has its own circuit.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider_name = models.CharField(
        max_length=100,
        db_index=True,
        help_text="Provider identifier (e.g., 'dga_api', 'sma_api', 'mqtt_broker')"
    )
    state = models.CharField(
        max_length=20,
        choices=CircuitState.choices,
        default=CircuitState.CLOSED
    )
    failure_count = models.PositiveIntegerField(default=0)
    success_count = models.PositiveIntegerField(default=0)
    last_failure_at = models.DateTimeField(null=True, blank=True)
    last_success_at = models.DateTimeField(null=True, blank=True)
    opened_at = models.DateTimeField(null=True, blank=True)
    failure_threshold = models.PositiveIntegerField(
        default=5,
        help_text="Number of failures before opening circuit"
    )
    recovery_timeout = models.PositiveIntegerField(
        default=60,
        help_text="Seconds to wait before half-open attempt"
    )
    half_open_max_calls = models.PositiveIntegerField(
        default=3,
        help_text="Max test calls in half-open state"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "gateway_circuit_breaker_log"
        verbose_name = "Circuit Breaker Log"
        verbose_name_plural = "Circuit Breaker Logs"
        indexes = [
            models.Index(fields=["provider_name", "state"]),
            models.Index(fields=["updated_at"]),
        ]

    def __str__(self):
        return f"{self.provider_name}: {self.state}"

    @property
    def is_closed(self):
        return self.state == CircuitState.CLOSED

    @property
    def is_open(self):
        return self.state == CircuitState.OPEN

    @property
    def can_attempt_reset(self):
        if not self.opened_at:
            return True
        return timezone.now() >= self.opened_at + timedelta(
            seconds=self.recovery_timeout
        )


class APICallLog(models.Model):
    """
    Structured logging of all API calls for analytics and monitoring.
    Uses database partitioning-friendly structure for high-volume data.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    request_id = models.CharField(max_length=64, db_index=True)
    correlation_id = models.CharField(max_length=64, db_index=True, null=True, blank=True)

    # Request metadata
    method = models.CharField(max_length=10)
    path = models.CharField(max_length=500, db_index=True)
    version = models.CharField(max_length=10, db_index=True, default="v1")
    query_params = models.JSONField(default=dict, blank=True)

    # Tenant info
    tenant_id = models.CharField(max_length=100, db_index=True, null=True, blank=True)
    user_id = models.CharField(max_length=100, db_index=True, null=True, blank=True)

    # Performance metrics
    started_at = models.DateTimeField(db_index=True)
    duration_ms = models.PositiveIntegerField(null=True, blank=True)

    # Response metadata
    status_code = models.PositiveSmallIntegerField(null=True, blank=True)
    response_size_bytes = models.PositiveIntegerField(null=True, blank=True)

    # Classification
    endpoint_name = models.CharField(max_length=200, db_index=True, null=True, blank=True)
    tags = models.JSONField(default=list, blank=True)

    # Error tracking
    error_type = models.CharField(max_length=100, null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "gateway_api_call_log"
        verbose_name = "API Call Log"
        verbose_name_plural = "API Call Logs"
        indexes = [
            models.Index(fields=["tenant_id", "created_at"]),
            models.Index(fields=["endpoint_name", "created_at"]),
            models.Index(fields=["status_code", "created_at"]),
            models.Index(fields=["version", "created_at"]),
        ]

    def __str__(self):
        return f"{self.method} {self.path} → {self.status_code}"


class TenantRateLimitConfig(models.Model):
    """
    Per-tenant rate limiting configuration.
    Allows different tiers: free, basic, professional, enterprise.
    """

    TIER_CHOICES = [
        ("free", "Free"),
        ("basic", "Basic"),
        ("professional", "Professional"),
        ("enterprise", "Enterprise"),
        ("custom", "Custom"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.CharField(max_length=100, unique=True, db_index=True)
    tier = models.CharField(max_length=20, choices=TIER_CHOICES, default="basic")

    # Rate limits per minute
    requests_per_minute = models.PositiveIntegerField(default=60)
    burst_limit = models.PositiveIntegerField(default=10)

    # Resource-specific limits
    telemetry_limit_per_minute = models.PositiveIntegerField(default=120)
    compliance_limit_per_minute = models.PositiveIntegerField(default=30)
    export_limit_per_minute = models.PositiveIntegerField(default=10)

    # Concurrent request limits
    max_concurrent_requests = models.PositiveIntegerField(default=20)

    # Overrides
    custom_limits = models.JSONField(
        default=dict,
        blank=True,
        help_text="Endpoint-specific custom limits: {'/api/telemetry/': 200}"
    )

    is_active = models.BooleanField(default=True)
    valid_from = models.DateTimeField(default=timezone.now)
    valid_until = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "gateway_tenant_rate_limit_config"
        verbose_name = "Tenant Rate Limit Config"
        verbose_name_plural = "Tenant Rate Limit Configs"

    def __str__(self):
        return f"{self.tenant_id} ({self.tier})"

    def is_valid(self):
        now = timezone.now()
        if not self.is_active:
            return False
        if now < self.valid_from:
            return False
        if self.valid_until and now > self.valid_until:
            return False
        return True
