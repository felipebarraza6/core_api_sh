"""
MQTT Service Registry

Manages active DynamicMQTTHandler instances based on database configuration.
Ensures that we don't duplicate connections for the same provider.
"""

import logging
import asyncio
from typing import Dict, Optional
from .models import TelemetryProvider
from .mqtt_handler import DynamicMQTTHandler

logger = logging.getLogger(__name__)

class MQTTRegistry:
    """
    Central registry for active MQTT handlers.
    """
    _instance = None
    _handlers: Dict[int, DynamicMQTTHandler] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MQTTRegistry, cls).__new__(cls)
        return cls._instance

    async def get_handler(self, provider_id: int) -> Optional[DynamicMQTTHandler]:
        """Get or create an MQTT handler for a given provider."""
        if provider_id in self._handlers:
            return self._handlers[provider_id]

        try:
            provider = await asyncio.get_event_loop().run_in_executor(
                None, lambda: TelemetryProvider.objects.select_related('mqtt_config').get(id=provider_id)
            )
            
            if provider.provider_type != 'mqtt':
                logger.warning(f"Provider {provider.name} is not an MQTT type")
                return None

            handler = DynamicMQTTHandler(provider)
            self._handlers[provider_id] = handler
            return handler
        except TelemetryProvider.DoesNotExist:
            logger.error(f"TelemetryProvider {provider_id} not found")
            return None
        except Exception as e:
            logger.error(f"Error creating MQTT handler for provider {provider_id}: {e}")
            return None

    async def start_all(self):
        """Start all configured MQTT providers."""
        providers = await asyncio.get_event_loop().run_in_executor(
            None, lambda: list(TelemetryProvider.objects.filter(provider_type='mqtt', is_active=True))
        )
        
        for provider in providers:
            handler = await self.get_handler(provider.id)
            if handler:
                asyncio.create_task(handler.connect())

    async def stop_all(self):
        """Stop all active MQTT handlers."""
        for provider_id, handler in self._handlers.items():
            handler.disconnect()
        self._handlers.clear()

# Singleton instance
mqtt_service_registry = MQTTRegistry()
