"""
Base Provider Handlers

Abstract base classes and utilities for implementing telemetry provider integrations.
"""

import logging
import requests
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from datetime import datetime

from django.conf import settings
from django.utils import timezone

from .models import TelemetryProvider, CatchmentPointProvider

logger = logging.getLogger(__name__)


class BaseProviderHandler(ABC):
    """
    Abstract base class for telemetry provider handlers.

    Each provider should implement a handler that extends this class
    to handle provider-specific logic.
    """

    # Must be set by subclasses
    provider_name: str = None
    supported_protocols: List[str] = []
    supported_variables: List[str] = []

    def __init__(self):
        if not self.provider_name:
            raise ValueError("provider_name must be set by subclass")

    @abstractmethod
    def fetch_data(self, provider_config: CatchmentPointProvider,
                  variable_type: str = None, **kwargs) -> Dict[str, Any]:
        """
        Fetch telemetry data from the provider.

        Args:
            provider_config: CatchmentPointProvider instance
            variable_type: Specific variable type to fetch (optional)
            **kwargs: Additional parameters

        Returns:
            Dict with standardized data format:
            {
                'timestamp': datetime,
                'value': float,
                'unit': str,
                'variable_type': str,
                'metadata': dict
            }
        """
        pass

    def supports_variable(self, variable_type: str) -> bool:
        """Check if handler supports a specific variable type."""
        return variable_type in self.supported_variables

    def supports_protocol(self, protocol: str) -> bool:
        """Check if handler supports a specific protocol."""
        return protocol in self.supported_protocols

    def test_connection(self, provider: TelemetryProvider) -> Dict[str, Any]:
        """Test basic connectivity to the provider."""
        try:
            response = requests.get(
                provider.base_url,
                headers=provider.get_auth_headers(),
                timeout=10
            )
            return {
                'success': response.status_code == 200,
                'status_code': response.status_code,
                'response_time': response.elapsed.total_seconds(),
                'message': f"HTTP {response.status_code}"
            }
        except requests.RequestException as e:
            return {
                'success': False,
                'error': str(e),
                'message': 'Connection failed'
            }

    def validate_config(self, config: Dict[str, Any]) -> bool:
        """Validate provider-specific configuration."""
        return True

    def get_supported_variables(self) -> List[str]:
        """Get list of supported variable types."""
        return self.supported_variables.copy()

    def normalize_data(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize provider-specific data to standard format.

        This is a convenience method that can be overridden by subclasses.
        """
        return raw_data


class APIProviderHandler(BaseProviderHandler):
    """
    Base handler for REST API providers.

    Provides common functionality for HTTP-based providers.
    """

    supported_protocols = ['api', 'http']

    def make_request(self, provider: TelemetryProvider, endpoint: str,
                    method: str = 'GET', data: Dict = None, **kwargs) -> requests.Response:
        """Make HTTP request with proper authentication and error handling."""

        url = provider.build_endpoint_url(**kwargs)
        headers = provider.get_auth_headers()
        headers.update({'Content-Type': 'application/json'})

        request_params = {
            'method': method,
            'url': url,
            'headers': headers,
            'timeout': provider.timeout_seconds,
        }

        if data and method in ['POST', 'PUT', 'PATCH']:
            request_params['json'] = data

        response = requests.request(**request_params)
        response.raise_for_status()

        return response

    def fetch_data(self, provider_config: CatchmentPointProvider,
                  variable_type: str = None, **kwargs) -> Dict[str, Any]:
        """Generic API data fetching."""

        provider = provider_config.provider

        try:
            # Build request payload
            payload = provider.build_request_payload(
                point_code=provider_config.point_code,
                variable_type=variable_type,
                **kwargs
            )

            # Make request
            response = self.make_request(
                provider,
                provider.endpoint_template,
                data=payload,
                point_code=provider_config.point_code,
                variable_type=variable_type
            )

            # Parse response
            data = response.json()

            # Apply response mapping if configured
            if provider.response_mapping:
                mapped_data = self._apply_mapping(data, provider.response_mapping)
            else:
                mapped_data = data

            # Normalize and return
            return self.normalize_data(mapped_data)

        except requests.RequestException as e:
            provider_config.record_error(str(e))
            raise
        except Exception as e:
            provider_config.record_error(f"Data parsing error: {str(e)}")
            raise

    def _apply_mapping(self, data: Dict, mapping: Dict) -> Dict:
        """Apply response mapping to transform API response."""
        result = {}

        for target_field, source_path in mapping.items():
            try:
                value = self._extract_value_by_path(data, source_path)
                result[target_field] = value
            except (KeyError, IndexError, TypeError):
                logger.warning(f"Could not extract {target_field} from path {source_path}")
                result[target_field] = None

        return result

    def _extract_value_by_path(self, data: Dict, path: str):
        """Extract value from nested dict using dot notation."""
        keys = path.split('.')
        current = data

        for key in keys:
            if isinstance(current, dict):
                current = current[key]
            elif isinstance(current, list) and key.isdigit():
                current = current[int(key)]
            else:
                raise KeyError(f"Invalid path: {path}")

        return current


class MQTTProviderHandler(BaseProviderHandler):
    """
    Base handler for MQTT-based providers.

    Provides common functionality for MQTT protocol providers.
    """

    supported_protocols = ['mqtt']

    def __init__(self):
        super().__init__()
        self.mqtt_client = None

    def connect(self, provider: TelemetryProvider):
        """Establish MQTT connection."""
        try:
            import paho.mqtt.client as mqtt

            self.mqtt_client = mqtt.Client()
            # Configure authentication
            auth_config = provider.auth_config
            if 'username' in auth_config:
                self.mqtt_client.username_pw_set(
                    auth_config['username'],
                    auth_config.get('password', '')
                )

            # Connect
            broker_url = provider.base_url.replace('mqtt://', '').replace('mqtts://', '')
            use_tls = provider.base_url.startswith('mqtts://')

            if use_tls:
                self.mqtt_client.tls_set()

            self.mqtt_client.connect(broker_url, 8883 if use_tls else 1883, 60)
            self.mqtt_client.loop_start()

        except ImportError:
            raise ImportError("paho-mqtt package is required for MQTT providers")
        except Exception as e:
            raise ConnectionError(f"MQTT connection failed: {e}")

    def fetch_data(self, provider_config: CatchmentPointProvider,
                  variable_type: str = None, **kwargs) -> Dict[str, Any]:
        """Fetch data via MQTT (simplified implementation)."""
        # This is a basic implementation - real MQTT handlers would be more complex
        # with subscriptions, message queues, etc.

        if not self.mqtt_client:
            self.connect(provider_config.provider)

        # For this example, we'll simulate MQTT data retrieval
        # In a real implementation, you'd subscribe to topics and wait for messages

        return {
            'timestamp': timezone.now(),
            'value': 0.0,  # Placeholder
            'unit': 'unknown',
            'variable_type': variable_type or 'unknown',
            'metadata': {'protocol': 'mqtt', 'status': 'simulated'}
        }


# Example provider implementations

class NettraHandler(APIProviderHandler):
    """Handler for Nettra IoT Platform."""

    provider_name = "nettra"
    supported_variables = ['CAUDAL', 'NIVEL', 'TOTALIZADO']

    def fetch_data(self, provider_config: CatchmentPointProvider,
                  variable_type: str = None, **kwargs) -> Dict[str, Any]:
        """Fetch data from Nettra API."""

        # Nettra-specific logic
        provider = provider_config.provider

        # Build Nettra-specific endpoint
        endpoint = f"/api/v1/devices/{provider_config.point_code}/data"

        if variable_type:
            endpoint += f"?variable={variable_type}"

        response = self.make_request(provider, endpoint)

        data = response.json()

        # Nettra-specific response parsing
        return {
            'timestamp': datetime.fromisoformat(data['timestamp'].replace('Z', '+00:00')),
            'value': float(data['value']),
            'unit': data.get('unit', 'unknown'),
            'variable_type': data.get('variable', variable_type),
            'metadata': {
                'device_id': data.get('device_id'),
                'sensor_id': data.get('sensor_id'),
                'quality': data.get('quality', 'unknown')
            }
        }


class TwinHandler(APIProviderHandler):
    """Handler for Twin Platform."""

    provider_name = "twin"
    supported_variables = ['CAUDAL', 'NIVEL', 'TOTALIZADO', 'CONDUCTIVIDAD']

    def fetch_data(self, provider_config: CatchmentPointProvider,
                  variable_type: str = None, **kwargs) -> Dict[str, Any]:
        """Fetch data from Twin API."""

        provider = provider_config.provider

        # Twin-specific endpoint
        endpoint = f"/api/data/{provider_config.point_code}"

        params = {}
        if variable_type:
            params['type'] = variable_type

        response = self.make_request(provider, endpoint, params=params)

        data = response.json()

        # Twin-specific response parsing
        return {
            'timestamp': datetime.fromisoformat(data['measurement_time']),
            'value': float(data['measurement_value']),
            'unit': data.get('unit', 'unknown'),
            'variable_type': data.get('measurement_type', variable_type),
            'metadata': {
                'station_id': data.get('station_id'),
                'sensor_type': data.get('sensor_type'),
                'data_quality': data.get('data_quality')
            }
        }


class NovusHandler(APIProviderHandler):
    """Handler for Novus Platform."""

    provider_name = "novus"
    supported_variables = ['CAUDAL', 'NIVEL', 'PRESION', 'TEMPERATURA']

    def fetch_data(self, provider_config: CatchmentPointProvider,
                  variable_type: str = None, **kwargs) -> Dict[str, Any]:
        """Fetch data from Novus API."""

        provider = provider_config.provider

        # Novus-specific endpoint
        endpoint = f"/api/sensors/{provider_config.point_code}/readings"

        response = self.make_request(provider, endpoint)

        readings = response.json()

        # Novus returns multiple readings, get the latest
        latest_reading = max(readings, key=lambda x: x['timestamp'])

        return {
            'timestamp': datetime.fromisoformat(latest_reading['timestamp']),
            'value': float(latest_reading['value']),
            'unit': latest_reading.get('unit', 'unknown'),
            'variable_type': latest_reading.get('parameter', variable_type),
            'metadata': {
                'sensor_id': latest_reading.get('sensor_id'),
                'location': latest_reading.get('location'),
                'status': latest_reading.get('status')
            }
        }