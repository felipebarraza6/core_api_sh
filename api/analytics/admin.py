from django.contrib import admin
from .models import APIUsageAggregate, EndpointHealthScore, APIDashboardSnapshot


@admin.register(APIUsageAggregate)
class APIUsageAggregateAdmin(admin.ModelAdmin):
    list_display = [
        "endpoint_name", "method", "bucket_size", "bucket_time",
        "request_count", "error_count", "avg_duration_ms"
    ]
    list_filter = ["bucket_size", "method", "module_name", "bucket_time"]
    search_fields = ["endpoint_name", "tenant_id"]
    date_hierarchy = "bucket_time"


@admin.register(EndpointHealthScore)
class EndpointHealthScoreAdmin(admin.ModelAdmin):
    list_display = [
        "endpoint_name", "module_name", "health_score",
        "health_status", "calculated_at"
    ]
    list_filter = ["health_status", "module_name"]
    search_fields = ["endpoint_name"]


@admin.register(APIDashboardSnapshot)
class APIDashboardSnapshotAdmin(admin.ModelAdmin):
    list_display = [
        "time_range", "snapshot_time", "total_requests",
        "avg_latency_ms", "p95_latency_ms"
    ]
    list_filter = ["time_range"]
    date_hierarchy = "snapshot_time"
