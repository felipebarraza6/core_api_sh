from django.contrib import admin
from .models import EventStore, DeadLetterQueue, EventSubscription


@admin.register(EventStore)
class EventStoreAdmin(admin.ModelAdmin):
    list_display = [
        "event_type", "aggregate_type", "aggregate_id",
        "status", "sequence_number", "occurred_at"
    ]
    list_filter = ["event_type", "status", "aggregate_type", "occurred_at"]
    search_fields = ["aggregate_id", "payload", "event_type"]
    readonly_fields = ["recorded_at"]
    date_hierarchy = "occurred_at"


@admin.register(DeadLetterQueue)
class DeadLetterQueueAdmin(admin.ModelAdmin):
    list_display = [
        "event_type", "handler_name", "retry_count",
        "resolution", "created_at"
    ]
    list_filter = ["resolution", "event_type", "created_at"]
    search_fields = ["payload", "failure_reason"]
    actions = ["reprocess_events"]

    @admin.action(description="Reprocess selected events")
    def reprocess_events(self, request, queryset):
        for event in queryset.filter(resolution="pending"):
            event.reprocess()


@admin.register(EventSubscription)
class EventSubscriptionAdmin(admin.ModelAdmin):
    list_display = [
        "consumer_group", "last_sequence_processed",
        "consumer_count", "is_active", "last_processed_at"
    ]
    list_filter = ["is_active"]
