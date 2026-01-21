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
from .handlers import BaseProviderHandler, DynamicAPIHandler, get_dynamic_handler
from api.core import metrics

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
        """Load handlers for all active providers."""
        self._handlers = {}

        # Create appropriate handler for each active provider
        for name, provider in self._providers.items():
            try:
                if provider.provider_type == 'mqtt':
                    # Use DynamicMQTTHandler for MQTT providers
                    from .handlers import DynamicMQTTHandler
                    self._handlers[name] = DynamicMQTTHandler(provider)
                    logger.debug(f"Loaded MQTT dynamic handler for: {name}")
                else:
                    # Use DynamicAPIHandler for API providers (REST, HTTP, etc.)
                    self._handlers[name] = DynamicAPIHandler(provider)
                    logger.debug(f"Loaded API dynamic handler for: {name}")
            except Exception as e:
                logger.error(f"Failed to create handler for {name}: {e}")

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

    def fetch_data(
        self,
        service: str,
        token: str,
        variable: str,
        point_id: Optional[int] = None,
        max_retries: int = 3,
        backoff_factor: int = 2
    ) -> Dict[str, Any]:
        """
        Obtiene datos de telemetría usando el sistema dinámico.

        Este método es el punto de entrada principal y reemplaza
        la función get_data_with_retry del sistema legacy.

        Args:
            service: Nombre del servicio (TWIN, NETTRA, NOVUS)
            token: Token de autenticación del dispositivo
            variable: Nombre de la variable a obtener
            point_id: ID del punto de captación (opcional)
            max_retries: Número máximo de reintentos
            backoff_factor: Factor de backoff exponencial

        Returns:
            Dict con formato: {"value": float, "date_time": str}
        """
        import time
        from datetime import datetime

        # Mapeo legacy service -> nombre de proveedor dinámico
        legacy_service_map = {
            'TWIN': 'twin',
            'NETTRA': 'nettra',
            'NOVUS': 'novus',
        }

        # Normalizar nombre del proveedor
        provider_name = legacy_service_map.get(service, service.lower())

        if point_id:
            result = self._fetch_via_dynamic_provider(
                point_id, provider_name, variable, max_retries, backoff_factor
            )
            if result is not None:
                return result

        # Si no hay point_id, no podemos usar el sistema dinámico
        # Retornar error indicando que se requiere point_id
        logger.error(
            f"No point_id provided for {service}/{variable}. "
            f"Dynamic provider system requires point_id to function."
        )
        return {'value': 0, 'date_time': None}

    def _fetch_via_dynamic_provider(
        self,
        point_id: int,
        provider_name: str,
        variable: str,
        max_retries: int,
        backoff_factor: int
    ) -> Optional[Dict[str, Any]]:
        """
        Intenta obtener datos usando el sistema de proveedores dinámico.
        """
        import time
        from datetime import datetime

        try:
            # Buscar configuración de proveedor para este punto
            provider_config = CatchmentPointProvider.objects.filter(
                point_id=point_id,
                provider__name=provider_name,
                is_active=True
            ).select_related('provider').first()

            if not provider_config:
                logger.debug(
                    f"No dynamic provider config for point {point_id}, "
                    f"provider {provider_name}"
                )
                return None

            handler = self.get_handler(provider_name)
            if not handler:
                logger.warning(f"No handler registered for provider: {provider_name}")
                return None

            # Fetch con retry
            for attempt in range(max_retries):
                try:
                    data = handler.fetch_data(
                        provider_config,
                        variable_type=variable
                    )

                    if data and data.get('value') is not None:
                        provider_config.record_success()
                        
                        # Prometheus: Ingestión exitosa
                        point = provider_config.point
                        project = point.project
                        client = project.client if project else None
                        
                        metrics.telemetry_ingestion_total.labels(
                            point_id=str(point.id),
                            point_name=str(point.title),
                            project=str(project.name if project else "Sin Proyecto"),
                            client=str(client.name if client else "Sin Cliente"),
                            # Prioritize dynamic frequency (FK) over legacy frecuency (Char)
                            frequency=str(point.frequency.minutes if point.frequency else dict(point.FRECUENCY_OPTIONS).get(point.frecuency, "Desconocida")),
                            provider=str(provider_name),
                            protocol=str(provider_config.provider.provider_type).upper()
                        ).inc()

                        # Convertir al formato legacy para compatibilidad
                        return {
                            'value': data.get('value', 0),
                            'date_time': self._format_timestamp(data.get('timestamp'))
                        }

                except Exception as exc:
                    logger.warning(
                        f"Dynamic provider attempt {attempt + 1}/{max_retries} "
                        f"failed for {provider_name}: {exc}"
                    )
                    
                    # Prometheus: Error de ingestión
                    point = provider_config.point
                    project = point.project
                    client = project.client if project else None
                    
                    metrics.telemetry_ingestion_errors.labels(
                        point_id=str(point.id),
                        point_name=str(point.title),
                        project=str(project.name if project else "Sin Proyecto"),
                        client=str(client.name if client else "Sin Cliente"),
                        error_type=str(type(exc).__name__),
                        protocol=str(provider_config.provider.provider_type).upper()
                    ).inc()

                    if attempt < max_retries - 1:
                        time.sleep(backoff_factor ** attempt)

            provider_config.record_error("Max retries exceeded")
            return None

        except Exception as exc:
            logger.error(f"Dynamic provider error: {exc}")
            return None


    def _format_timestamp(self, timestamp) -> Optional[str]:
        """Formatea un timestamp al formato esperado por el sistema."""
        from datetime import datetime

        if timestamp is None:
            return None

        if isinstance(timestamp, str):
            return timestamp

        if isinstance(timestamp, datetime):
            return timestamp.strftime("%Y-%m-%dT%H:%M:%S")

        return None


# Singleton para uso global
_provider_manager: Optional[ProviderManager] = None


def get_provider_manager() -> ProviderManager:
    """Obtiene la instancia singleton del ProviderManager."""
    global _provider_manager
    if _provider_manager is None:
        _provider_manager = ProviderManager()
    return _provider_manager


def get_data_with_provider(
    service: str,
    token: str,
    variable: str,
    point_id: Optional[int] = None,
    max_retries: int = 3,
    backoff_factor: int = 2
) -> Dict[str, Any]:
    """
    Función de conveniencia para obtener datos usando el ProviderManager.

    Este es el reemplazo directo de get_data_with_retry en telemetry.py
    """
    manager = get_provider_manager()
    return manager.fetch_data(
        service=service,
        token=token,
        variable=variable,
        point_id=point_id,
        max_retries=max_retries,
        backoff_factor=backoff_factor
    )