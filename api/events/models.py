"""
Event Store Models

Provides persistent storage for domain events:
- EventStore: Immutable log of all domain events
- DeadLetterQueue: Failed events for later processing
- EventSubscription: Consumer group tracking
"""

import uuid
from datetime import timedelta

from django.db import models
from django.utils import timezone


class EventStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    PROCESSING = "processing", "Processing"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"
    RETRYING = "retrying", "Retrying"


class EventStore(models.Model):
    """
    Immutable event store for audit trail and replay.
    All domain events are persisted here before being processed.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Event metadata
    event_type = models.CharField(max_length=200, db_index=True)
    event_version = models.CharField(max_length=10, default="1.0")
    aggregate_type = models.CharField(
        max_length=100,
        db_index=True,
        help_text="Type of aggregate (e.g., 'telemetry', 'compliance', 'device')"
    )
    aggregate_id = models.CharField(
        max_length=100,
        db_index=True,
        help_text="ID of the aggregate instance"
    )

    # Event data (immutable)
    payload = models.JSONField(
        help_text="Event payload data"
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Event metadata (correlation_id, user_id, source_ip, etc.)"
    )

    # Sequencing
    sequence_number = models.PositiveBigIntegerField(
        db_index=True,
        help_text="Global sequence number for ordering"
    )

    # Status tracking
    status = models.CharField(
        max_length=20,
        choices=EventStatus.choices,
        default=EventStatus.PENDING,
        db_index=True,
    )
    processed_at = models.DateTimeField(null=True, blank=True)
    processed_by = models.CharField(
        max_length=200,
        null=True,
        blank=True,
        help_text="Handler that processed this event"
    )

    # Timestamps
    occurred_at = models.DateTimeField(db_index=True)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "events_store"
        verbose_name = "Event Store Entry"
        verbose_name_plural = "Event Store Entries"
        indexes = [
            models.Index(fields=["aggregate_type", "aggregate_id", "sequence_number"]),
            models.Index(fields=["event_type", "status", "recorded_at"]),
            models.Index(fields=["status", "recorded_at"]),
        ]
        ordering = ["sequence_number"]

    def __str__(self):
        return f"{self.event_type} ({self.aggregate_type}:{self.aggregate_id})"

    def mark_processing(self):
        self.status = EventStatus.PROCESSING
        self.save(update_fields=["status"])

    def mark_completed(self, handler_name: str):
        self.status = EventStatus.COMPLETED
        self.processed_at = timezone.now()
        self.processed_by = handler_name
        self.save(update_fields=["status", "processed_at", "processed_by"])

    def mark_failed(self):
        self.status = EventStatus.FAILED
        self.save(update_fields=["status"])

    def mark_retrying(self):
        self.status = EventStatus.RETRYING
        self.save(update_fields=["status"])


class DeadLetterQueue(models.Model):
    """
    Dead letter queue for events that failed processing after max retries.
    Allows manual inspection and reprocessing.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Original event reference
    original_event = models.ForeignKey(
        EventStore,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dead_letter_entries",
    )

    # Event data (denormalized for inspection)
    event_type = models.CharField(max_length=200, db_index=True)
    payload = models.JSONField()
    metadata = models.JSONField(default=dict)

    # Failure info
    failure_reason = models.TextField()
    error_type = models.CharField(max_length=200)
    error_stack = models.TextField(null=True, blank=True)
    handler_name = models.CharField(max_length=200)

    # Retry tracking
    retry_count = models.PositiveIntegerField(default=0)
    max_retries = models.PositiveIntegerField(default=3)

    # Resolution
    RESOLUTION_CHOICES = [
        ("pending", "Pending"),
        ("reprocessed", "Reprocessed"),
        ("discarded", "Discarded"),
        ("manual", "Resolved Manually"),
    ]
    resolution = models.CharField(
        max_length=20,
        choices=RESOLUTION_CHOICES,
        default="pending",
        db_index=True,
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.CharField(max_length=100, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "events_dead_letter_queue"
        verbose_name = "Dead Letter Entry"
        verbose_name_plural = "Dead Letter Queue"
        indexes = [
            models.Index(fields=["event_type", "resolution", "created_at"]),
            models.Index(fields=["resolution", "created_at"]),
        ]

    def __str__(self):
        return f"DLQ: {self.event_type} ({self.resolution})"

    def reprocess(self):
        """Mark for reprocessing."""
        self.resolution = "reprocessed"
        self.resolved_at = timezone.now()
        self.save(update_fields=["resolution", "resolved_at"])


class EventSubscription(models.Model):
    """
    Tracks event consumer groups and their processing positions.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    consumer_group = models.CharField(max_length=200, db_index=True)
    event_types = models.JSONField(
        default=list,
        help_text="List of event types this group subscribes to"
    )

    # Processing position
    last_sequence_processed = models.PositiveBigIntegerField(default=0)
    last_processed_at = models.DateTimeField(null=True, blank=True)

    # Consumer info
    consumer_count = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    # Error tracking
    consecutive_errors = models.PositiveIntegerField(default=0)
    last_error = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "events_subscriptions"
        verbose_name = "Event Subscription"
        verbose_name_plural = "Event Subscriptions"
        unique_together = [["consumer_group"]]

    def __str__(self):
        return f"{self.consumer_group} (seq: {self.last_sequence_processed})"
