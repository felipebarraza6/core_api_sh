"""
Event Bus Implementation

Pub/Sub event bus using Redis Streams for reliable delivery.
Provides async event publishing and consumer group management.
"""

import asyncio
import json
import logging
from typing import Any, Callable, Dict, List, Optional

from django.conf import settings
from django.core.cache import cache

from .domain import DomainEvent
from .models import EventStore, EventStatus, DeadLetterQueue

logger = logging.getLogger("api.events.bus")


class EventBus:
    """
    Central event bus for publishing and subscribing to domain events.

    Uses Redis for transport and PostgreSQL for persistence.
    """

    STREAM_KEY = "smarthydro:events"
    PUBLISH_TIMEOUT = 5  # seconds

    @classmethod
    async def publish(cls, event: DomainEvent) -> str:
        """
        Publish a domain event to the bus.

        Args:
            event: Domain event to publish

        Returns:
            Event ID

        Usage:
            event = TelemetryReceived(device_id="123", ...)
            event_id = await EventBus.publish(event)
        """
        # Persist to event store first
        sequence = await cls._get_next_sequence()

        store_entry = EventStore.objects.create(
            event_type=event.event_type,
            event_version=event.event_version,
            aggregate_type=event.aggregate_type,
            aggregate_id=event.aggregate_id,
            payload=event.payload,
            metadata=event.metadata,
            sequence_number=sequence,
            status=EventStatus.PENDING,
            occurred_at=event.occurred_at,
        )

        # Publish to Redis Stream for async processing
        try:
            event_data = json.dumps(event.to_dict())
            # Use Redis Streams for reliable delivery
            cache.client.xadd(
                cls.STREAM_KEY,
                {
                    "event_id": str(store_entry.id),
                    "event_type": event.event_type,
                    "aggregate_type": event.aggregate_type,
                    "aggregate_id": event.aggregate_id,
                    "data": event_data,
                    "sequence": str(sequence),
                },
                maxlen=100000,  # Keep last 100k events
            )
        except Exception as e:
            logger.error(f"Failed to publish to Redis Stream: {e}")
            # Event is still in EventStore, can be processed later

        logger.info(f"Event published: {event.event_type} (seq: {sequence})")
        return str(store_entry.id)

    @classmethod
    def publish_sync(cls, event: DomainEvent) -> str:
        """Synchronous version of publish for non-async contexts."""
        sequence = cls._get_next_sequence_sync()

        store_entry = EventStore.objects.create(
            event_type=event.event_type,
            event_version=event.event_version,
            aggregate_type=event.aggregate_type,
            aggregate_id=event.aggregate_id,
            payload=event.payload,
            metadata=event.metadata,
            sequence_number=sequence,
            status=EventStatus.PENDING,
            occurred_at=event.occurred_at,
        )

        try:
            event_data = json.dumps(event.to_dict())
            # Use Redis list as fallback for sync contexts
            cache.client.lpush(
                f"{cls.STREAM_KEY}:pending",
                json.dumps({
                    "event_id": str(store_entry.id),
                    "event_type": event.event_type,
                    "data": event_data,
                    "sequence": sequence,
                })
            )
        except Exception as e:
            logger.error(f"Failed to publish to Redis: {e}")

        return str(store_entry.id)

    @classmethod
    async def subscribe(
        cls,
        consumer_group: str,
        event_types: List[str],
        handler: Callable,
        batch_size: int = 10,
    ):
        """
        Subscribe to events as a consumer group.

        Args:
            consumer_group: Unique consumer group name
            event_types: List of event types to subscribe to
            handler: Async handler function
            batch_size: Number of events to process per batch
        """
        from .models import EventSubscription

        # Register subscription
        subscription, _ = EventSubscription.objects.get_or_create(
            consumer_group=consumer_group,
            defaults={"event_types": event_types},
        )

        logger.info(
            f"Consumer group '{consumer_group}' subscribed to: {event_types}"
        )

        # Process events from EventStore (for events that missed Redis)
        while True:
            try:
                # Get pending events from EventStore
                pending_events = EventStore.objects.filter(
                    event_type__in=event_types,
                    status=EventStatus.PENDING,
                    sequence_number__gt=subscription.last_sequence_processed,
                ).order_by("sequence_number")[:batch_size]

                for event in pending_events:
                    try:
                        event.mark_processing()

                        # Reconstruct domain event
                        domain_event = DomainEvent.from_dict({
                            "type": event.event_type,
                            "aggregate_type": event.aggregate_type,
                            "aggregate_id": event.aggregate_id,
                            "data": event.payload,
                            "metadata": event.metadata,
                        })

                        # Call handler
                        await handler(domain_event)

                        event.mark_completed(consumer_group)

                        # Update subscription position
                        subscription.last_sequence_processed = event.sequence_number
                        subscription.last_processed_at = timezone.now()
                        subscription.consecutive_errors = 0
                        subscription.save()

                    except Exception as e:
                        logger.error(
                            f"Handler error for {event.event_type}: {e}"
                        )
                        await cls._handle_handler_error(event, e, consumer_group)

                if not pending_events:
                    await asyncio.sleep(1)  # Wait before checking again

            except Exception as e:
                logger.error(f"Subscription error: {e}")
                await asyncio.sleep(5)

    @classmethod
    async def _get_next_sequence(cls) -> int:
        """Get next global sequence number."""
        try:
            return cache.client.incr("events:sequence")
        except Exception:
            # Fallback: use database
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT COALESCE(MAX(sequence_number), 0) + 1
                    FROM events_store
                """)
                return cursor.fetchone()[0]

    @classmethod
    def _get_next_sequence_sync(cls) -> int:
        """Synchronous version of sequence generation."""
        try:
            return cache.incr("events:sequence")
        except Exception:
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT COALESCE(MAX(sequence_number), 0) + 1
                    FROM events_store
                """)
                return cursor.fetchone()[0]

    @classmethod
    async def _handle_handler_error(
        cls,
        event: EventStore,
        error: Exception,
        handler_name: str,
        max_retries: int = 3,
    ):
        """Handle handler errors with retry logic and dead letter queue."""
        retry_count = event.metadata.get("retry_count", 0)

        if retry_count < max_retries:
            # Retry with exponential backoff
            event.metadata["retry_count"] = retry_count + 1
            event.status = EventStatus.RETRYING
            event.save(update_fields=["metadata", "status"])

            wait_time = 2 ** retry_count  # 1, 2, 4 seconds
            await asyncio.sleep(wait_time)
        else:
            # Max retries reached, send to dead letter queue
            event.mark_failed()

            DeadLetterQueue.objects.create(
                original_event=event,
                event_type=event.event_type,
                payload=event.payload,
                metadata=event.metadata,
                failure_reason=str(error),
                error_type=type(error).__name__,
                handler_name=handler_name,
                retry_count=retry_count,
            )

            logger.warning(
                f"Event {event.event_type} sent to DLQ after {max_retries} retries"
            )
