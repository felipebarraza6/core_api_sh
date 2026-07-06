from django.contrib import admin
from .models import CircuitBreakerLog, APICallLog, TenantRateLimitConfig


@admin.register(CircuitBreakerLog)
class CircuitBreakerLogAdmin(admin.ModelAdmin):
    list_display = ["provider_name", "state", "failure_count", "success_count", "updated_at"]
    list_filter = ["state", "provider_name"]
    search_fields = ["provider_name"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(APICallLog)
class APICallLogAdmin(admin.ModelAdmin):
    list_display = ["method", "path", "status_code", "tenant_id", "duration_ms", "created_at"]
    list_filter = ["method", "status_code", "version", "endpoint_name"]
    search_fields = ["path", "tenant_id", "request_id"]
    readonly_fields = ["created_at"]
    date_hierarchy = "created_at"


@admin.register(TenantRateLimitConfig)
class TenantRateLimitConfigAdmin(admin.ModelAdmin):
    list_display = ["tenant_id", "tier", "requests_per_minute", "is_active", "valid_from"]
    list_filter = ["tier", "is_active"]
    search_fields = ["tenant_id"]
