"""
Event Handlers

Provides base classes and registry for event handlers.
Handlers are automatically discovered and registered.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Type

from .domain import DomainEvent
from .bus import EventBus

logger = logging.getLogger("api.events.handlers")


class EventHandler(ABC):
    """
    Base class for event handlers.

    Usage:
        class TelemetryAlertHandler(EventHandler):
            event_types = ["telemetry.received"]
            consumer_group = "alert-processor"

            async def handle(self, event: TelemetryReceived):
                # Process event
                pass
    """

    event_types: List[str] = []
    consumer_group: str = "default"
    batch_size: int = 10

    @abstractmethod
    async def handle(self, event: DomainEvent):
        """Handle the event. Must be implemented by subclasses."""
        pass

    async def on_error(self, event: DomainEvent, error: Exception):
        """Called when handle() raises an exception. Override for custom error handling."""
        logger.error(f"Error handling {event.event_type}: {error}")

    def start(self):
        """Start the handler as an async consumer."""
        asyncio.create_task(
            EventBus.subscribe(
                consumer_group=self.consumer_group,
                event_types=self.event_types,
                handler=self.handle,
                batch_size=self.batch_size,
            )
        )


class EventHandlerRegistry:
    """
    Registry for event handlers.
    Automatically discovers and registers handlers.
    """

    _handlers: Dict[str, List[Type[EventHandler]]] = {}

    @classmethod
    def register(cls, handler_class: Type[EventHandler]):
        """Register an event handler class."""
        for event_type in handler_class.event_types:
            if event_type not in cls._handlers:
                cls._handlers[event_type] = []
            cls._handlers[event_type].append(handler_class)
            logger.info(f"Registered {handler_class.__name__} for {event_type}")

    @classmethod
    def get_handlers(cls, event_type: str) -> List[Type[EventHandler]]:
        """Get all handlers registered for an event type."""
        return cls._handlers.get(event_type, [])

    @classmethod
    def start_all(cls):
        """Start all registered handlers."""
        started = set()
        for handlers in cls._handlers.values():
            for handler_class in handlers:
                if handler_class not in started:
                    handler = handler_class()
                    handler.start()
                    started.add(handler_class)
                    logger.info(f"Started handler: {handler_class.__name__}")


# Decorator for registering handlers
def handles(*event_types: str, consumer_group: str = "default"):
    """
    Decorator to register an event handler.

    Usage:
        @handles("telemetry.received", "telemetry.processed")
        class MyHandler(EventHandler):
            async def handle(self, event):
                pass
    """
    def decorator(cls):
        cls.event_types = list(event_types)
        cls.consumer_group = consumer_group
        EventHandlerRegistry.register(cls)
        return cls
    return decorator
