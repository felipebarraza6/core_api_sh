"""
Provider Manager

Centralized management of telemetry providers with auto-discovery,
health monitoring, and request routing.
"""

import logging
import importlib
import pkgutil
from typing import List, Dict, Any, Optional
from django.core.cache import cache
from django.conf import settings

from .models import TelemetryProvider, CatchmentPointProvider
from .handlers import BaseProviderHandler

logger = logging.getLogger(__name__)


class ProviderManager:
    """
    Manages telemetry providers dynamically.

    Features:
    - Auto-discovery of provider implementations
    - Health monitoring and failover
    - Request routing based on configuration
    - Caching for performance
    """

    def __init__(self):
        self._providers = {}
        self._handlers = {}
        self._load_providers()
        self._load_handlers()

    def _load_providers(self):
        """Load all active providers from database."""
        try:
            providers = TelemetryProvider.objects.filter(is_active=True)
            self._providers = {p.name: p for p in providers}
            logger.info(f"Loaded {len(self._providers)} active providers")
        except Exception as e:
            logger.error(f"Error loading providers: {e}")
            self._providers = {}

    def _load_handlers(self):
        """Auto-discover and load provider handlers."""
        self._handlers = {}

        # Import built-in handlers
        try:
            from . import handlers
            for attr_name in dir(handlers):
                attr = getattr(handlers, attr_name)
                if (isinstance(attr, type) and
                    issubclass(attr, BaseProviderHandler) and
                    attr != BaseProviderHandler):
                    try:
                        if hasattr(attr, 'provider_name'):
                            handler_instance = attr()
                            provider_name = handler_instance.provider_name
                            self._handlers[provider_name] = handler_instance
                            logger.debug(f"Loaded handler for provider: {provider_name}")
                    except (ValueError, TypeError) as e:
                        logger.debug(f"Skipping handler {attr_name}: {e}")
        except ImportError as e:
            logger.warning(f"Could not load built-in handlers: {e}")

        # Auto-discover custom handlers
        self._discover_custom_handlers()

    def _discover_custom_handlers(self):
        """Discover custom provider handlers from plugins directory."""
        try:
            import sys
            from pathlib import Path

            # Look for handlers in api/core/providers/handlers/
            handlers_dir = Path(__file__).parent / 'handlers'
            if handlers_dir.exists():
                for handler_file in handlers_dir.glob('*.py'):
                    if handler_file.name == '__init__.py':
                        continue

                    module_name = f"api.core.providers.handlers.{handler_file.stem}"
                    try:
                        module = importlib.import_module(module_name)
                        for attr_name in dir(module):
                            attr = getattr(module, attr_name)
                            if (isinstance(attr, type) and
                                issubclass(attr, BaseProviderHandler) and
                                attr != BaseProviderHandler):
                                handler_instance = attr()
                                provider_name = handler_instance.provider_name
                                self._handlers[provider_name] = handler_instance
                                logger.info(f"Loaded custom handler: {provider_name}")
                    except ImportError as e:
                        logger.warning(f"Could not load handler {module_name}: {e}")

        except Exception as e:
            logger.error(f"Error discovering custom handlers: {e}")

    def get_provider(self, provider_name: str) -> Optional[TelemetryProvider]:
        """Get provider by name."""
        return self._providers.get(provider_name)

    def get_handler(self, provider_name: str) -> Optional['BaseProviderHandler']:
        """Get handler for provider."""
        return self._handlers.get(provider_name)

    def get_providers_for_point(self, point_id: int) -> List[CatchmentPointProvider]:
        """Get all active provider configurations for a point."""
        cache_key = f"point_providers_{point_id}"
        providers = cache.get(cache_key)

        if providers is None:
            try:
                providers = list(
                    CatchmentPointProvider.objects.filter(
                        point_id=point_id,
                        is_active=True
                    ).select_related('provider').order_by('-priority')
                )
                # Cache for 5 minutes
                cache.set(cache_key, providers, 300)
            except Exception as e:
                logger.error(f"Error getting providers for point {point_id}: {e}")
                providers = []

        return providers

    def get_best_provider_for_point(self, point_id: int, variable_type: str = None) -> Optional[CatchmentPointProvider]:
        """
        Get the best available provider for a point.

        Considers:
        - Provider priority
        - Health status
        - Variable type compatibility
        """
        providers = self.get_providers_for_point(point_id)

        if not providers:
            return None

        # Filter by variable type if specified
        if variable_type:
            compatible_providers = []
            for provider_config in providers:
                handler = self.get_handler(provider_config.provider.name)
                if handler and handler.supports_variable(variable_type):
                    compatible_providers.append(provider_config)
            providers = compatible_providers

        if not providers:
            return None

        # Return healthiest provider (highest priority, then best health)
        return max(providers, key=lambda p: (p.priority, p.consecutive_successes, -p.error_count))

    def refresh_cache(self):
        """Refresh all cached provider data."""
        cache.clear()  # Clear all cache (could be more selective)
        self._load_providers()
        logger.info("Provider cache refreshed")

    def get_all_providers(self) -> Dict[str, TelemetryProvider]:
        """Get all active providers."""
        return self._providers.copy()

    def get_provider_status(self) -> Dict[str, Dict]:
        """Get status of all providers."""
        status = {}
        for name, provider in self._providers.items():
            handler = self.get_handler(name)
            status[name] = {
                'provider': provider,
                'handler_available': handler is not None,
                'active_configs': CatchmentPointProvider.objects.filter(
                    provider=provider, is_active=True
                ).count()
            }
        return status

    def test_provider_connection(self, provider_name: str) -> Dict[str, Any]:
        """
        Test connection to a provider.

        Returns dict with test results.
        """
        provider = self.get_provider(provider_name)
        if not provider:
            return {'success': False, 'error': 'Provider not found'}

        handler = self.get_handler(provider_name)
        if not handler:
            return {'success': False, 'error': 'Handler not available'}

        try:
            # Use handler's test method if available
            if hasattr(handler, 'test_connection'):
                result = handler.test_connection(provider)
            else:
                # Basic connectivity test
                import requests
                response = requests.get(
                    provider.base_url,
                    headers=provider.get_auth_headers(),
                    timeout=10
                )
                result = {
                    'success': response.status_code == 200,
                    'status_code': response.status_code,
                    'response_time': response.elapsed.total_seconds()
                }

            return result

        except Exception as e:
            return {'success': False, 'error': str(e)}

    def create_provider_config(self, point_id: int, provider_name: str,
                             config: Dict[str, Any]) -> CatchmentPointProvider:
        """
        Create a new provider configuration for a point.

        Args:
            point_id: ID of the catchment point
            provider_name: Name of the provider
            config: Configuration dict

        Returns:
            Created CatchmentPointProvider instance

        Raises:
            ValueError: If provider doesn't exist or config is invalid
        """
        provider = self.get_provider(provider_name)
        if not provider:
            raise ValueError(f"Provider '{provider_name}' not found")

        # Validate configuration
        required_fields = ['point_code']
        for field in required_fields:
            if field not in config:
                raise ValueError(f"Required field missing: {field}")

        # Create configuration
        provider_config = CatchmentPointProvider.objects.create(
            point_id=point_id,
            provider=provider,
            point_code=config['point_code'],
            config_override=config.get('config_override', {}),
            device_config=config.get('device_config', {}),
            priority=config.get('priority', 0)
        )

        # Clear cache
        cache_key = f"point_providers_{point_id}"
        cache.delete(cache_key)

        logger.info(f"Created provider config: {provider_config}")
        return provider_config

    def update_provider_config(self, config_id: int, updates: Dict[str, Any]) -> CatchmentPointProvider:
        """Update an existing provider configuration."""
        try:
            config = CatchmentPointProvider.objects.get(id=config_id)

            for field, value in updates.items():
                if hasattr(config, field):
                    setattr(config, field, value)

            config.save()

            # Clear cache
            cache_key = f"point_providers_{config.point_id}"
            cache.delete(cache_key)

            logger.info(f"Updated provider config: {config}")
            return config

        except CatchmentPointProvider.DoesNotExist:
            raise ValueError(f"Provider configuration {config_id} not found")

    def disable_provider_config(self, config_id: int) -> bool:
        """Disable a provider configuration."""
        try:
            config = CatchmentPointProvider.objects.get(id=config_id)
            config.is_active = False
            config.save()

            # Clear cache
            cache_key = f"point_providers_{config.point_id}"
            cache.delete(cache_key)

            logger.info(f"Disabled provider config: {config}")
            return True

        except CatchmentPointProvider.DoesNotExist:
            return False