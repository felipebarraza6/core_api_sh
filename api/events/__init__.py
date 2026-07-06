"""
Event Bus Module for SmartHydro Core API

Provides event-driven architecture capabilities:
- Domain events for cross-module communication
- Event store for audit trail and replay
- Async event handlers with retry policies
- Dead letter queue for failed events

Architecture: Publisher → EventBus → Redis Streams → Handlers
"""

__version__ = "1.0.0"
