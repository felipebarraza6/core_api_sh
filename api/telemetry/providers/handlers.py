"""
Base Provider Handlers

Abstract base classes and utilities for implementing telemetry provider integrations.
"""

import logging
import requests
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from datetime import datetime
import time

from django.conf import settings
from django.utils import timezone

from api.core.models.utils import ModelApi
from .metrics import TELEMETRY_FETCH_TOTAL, TELEMETRY_FETCH_DURATION
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


class DynamicAPIHandler:
    """
    Handler dinámico que usa la configuración del TelemetryProvider.

    Este handler reemplaza los handlers hardcodeados (TwinHandler, NettraHandler,
    NovusHandler) con uno genérico que lee toda su configuración desde la BD.

    La configuración se define en:
    - TelemetryProvider.endpoint_template: Template de URL con {variables}
    - TelemetryProvider.request_template: Template de payload JSON
    - TelemetryProvider.response_mapping: Mapeo de campos de respuesta
    - TelemetryProvider.auth_config: Configuración de autenticación
    """

    def __init__(self, provider: TelemetryProvider):
        """
        Inicializa el handler con la configuración del proveedor.

        Args:
            provider: Instancia de TelemetryProvider con la configuración
        """
        self.provider = provider
        self.provider_name = provider.name

    def fetch_data(
        self,
        provider_config: CatchmentPointProvider,
        variable_type: str = None,
        token: str = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Obtiene datos usando la configuración dinámica del proveedor.

        Args:
            provider_config: Configuración del punto con el proveedor
            variable_type: Tipo de variable a obtener
            token: Token de autenticación/dispositivo (override/legacy)
            **kwargs: Parámetros adicionales

        Returns:
            Dict con formato estandarizado
        """
        try:
            # 1. Resolver Autenticación (incluyendo flujos de login previo)
            auth_token = self._resolve_auth_token(provider_config, token)

            # 2. Construir URL con template
            url = self._build_url(provider_config, variable_type, token)

            # 3. Obtener headers de autenticación
            headers = self._get_auth_headers(provider_config, auth_token)
            headers['Content-Type'] = 'application/json'

            # 4. Construir payload si es necesario
            payload = self._build_payload(provider_config, variable_type, token)

            # 5. Hacer request
            method = self.provider.request_template.get('method', 'GET') \
                if isinstance(self.provider.request_template, dict) else 'GET'

            request_params = {
                'method': method,
                'url': url,
                'headers': headers,
                'timeout': self.provider.timeout_seconds,
            }

            if payload and method in ['POST', 'PUT', 'PATCH']:
                request_params['json'] = payload

            logger.debug(f"[{self.provider_name}] Request: {method} {url}")
            
            start_time = time.time()
            try:
                response = requests.request(**request_params)
                response.raise_for_status()
                
                # Record success metrics
                duration = time.time() - start_time
                TELEMETRY_FETCH_DURATION.labels(provider=self.provider_name).observe(duration)
                TELEMETRY_FETCH_TOTAL.labels(provider=self.provider_name, status='success').inc()

                data = response.json()
            except Exception as e:
                # Record error metrics
                duration = time.time() - start_time
                TELEMETRY_FETCH_DURATION.labels(provider=self.provider_name).observe(duration)
                TELEMETRY_FETCH_TOTAL.labels(provider=self.provider_name, status='error').inc()
                raise e

            logger.debug(f"[{self.provider_name}] Response: {data}")

            # Aplicar mapeo de respuesta
            return self._parse_response(data, variable_type)

        except requests.RequestException as e:
            logger.error(f"[{self.provider_name}] Request error: {e}")
            if provider_config:
                provider_config.record_error(str(e))
            raise
        except Exception as e:
            logger.error(f"[{self.provider_name}] Error: {e}")
            raise

    def _resolve_auth_token(
        self,
        provider_config: CatchmentPointProvider,
        passed_token: str
    ) -> str:
        """
        Resuelve el token de autenticación.
        Maneja casos especiales como login previo (caso TWIN).
        """
        # Caso especial: Login previo requerido (configurado en auth_config)
        if self.provider.auth_config.get('login_url'):
            return self._perform_login_auth()
        
        # Caso por defecto: usar token pasado o configurado
        return passed_token

    def _perform_login_auth(self) -> str:
        """Realiza login para obtener token (e.g., TWIN) con caché simple."""
        # TODO: Implementar caché real (Redis) para no hacer login en cada request
        # Por ahora usamos una variable de clase o caché de Django si es posible
        from django.core.cache import cache
        
        cache_key = f"provider_auth_token_{self.provider.name}"
        cached_token = cache.get(cache_key)
        if cached_token:
            return cached_token

        config = self.provider.auth_config
        login_url = f"{self.provider.base_url.rstrip('/')}{config['login_url']}"
        
        # Payload de login
        payload = {
            k: v for k, v in config.items() 
            if k in ['username', 'password', 'email']
        }
        
        try:
            response = requests.post(login_url, json=payload, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            # Extraer token (assumes standard 'token' key or configurable)
            token_key = config.get('token_key', 'token')
            token = data.get(token_key)
            
            if token:
                # Cachear por 5 minutos (o menos que la expiración real)
                cache.set(cache_key, token, 300)
                return token
        except Exception as e:
            logger.error(f"Login failed for {self.provider.name}: {e}")
            raise

        raise ValueError(f"Could not retrieve token from login for {self.provider.name}")

    def _build_url(
        self,
        provider_config: CatchmentPointProvider,
        variable_type: str,
        token: str
    ) -> str:
        """Construye la URL usando el template del proveedor."""
        template = self.provider.endpoint_template

        # Variables disponibles para el template
        template_vars = {
            'point_code': provider_config.point_code if provider_config else '',
            'device_id': provider_config.point_code if provider_config else '', # Alias
            'variable': variable_type or '',
            'variable_type': variable_type or '', # Alias
            'token': token or '',
        }

        # Agregar variables del device_config
        if provider_config and provider_config.device_config:
            template_vars.update(provider_config.device_config)

        # Formatear template
        try:
            endpoint = template.format(**template_vars)
        except KeyError as e:
            logger.warning(f"Missing template variable: {e}")
            endpoint = template

        return f"{self.provider.base_url.rstrip('/')}{endpoint}"

    def _get_auth_headers(
        self,
        provider_config: CatchmentPointProvider,
        token: str
    ) -> Dict[str, str]:
        """Obtiene los headers de autenticación."""
        # Usar configuración base del proveedor
        headers = self.provider.get_auth_headers()

        # Override con configuración específica del punto
        if provider_config and provider_config.config_override:
            override = provider_config.config_override

            if 'token' in override:
                headers['Authorization'] = f"Bearer {override['token']}"
            elif 'api_key' in override:
                key_name = override.get('header', 'X-API-Key')
                headers[key_name] = override['api_key']

        # Override con token pasado como parámetro
        if token:
            if self.provider.auth_method == 'bearer':
                headers['Authorization'] = f"Bearer {token}"
            elif self.provider.auth_method == 'api_key':
                key_name = self.provider.auth_config.get('header', 'authorization')
                headers[key_name] = token
            # Para métodos sin auth (none), no agregamos header aunque haya token
            # (el token podría usarse en la URL)

        return headers

    def _build_payload(
        self,
        provider_config: CatchmentPointProvider,
        variable_type: str,
        token: str
    ) -> Optional[Dict]:
        """Construye el payload usando el template del proveedor."""
        if not self.provider.request_template:
            return None

        template = self.provider.request_template.copy()

        # Remover 'method' si existe (no es parte del payload)
        template.pop('method', None)

        if not template:
            return None

        # Variables para el template
        template_vars = {
            'point_code': provider_config.point_code if provider_config else '',
            'variable': variable_type or '',
            'token': token or '',
        }

        # Formatear valores del template
        return self._format_dict_template(template, template_vars)

    def _format_dict_template(
        self,
        template: Dict,
        variables: Dict
    ) -> Dict:
        """Formatea recursivamente un dict con variables."""
        result = {}
        for key, value in template.items():
            if isinstance(value, str):
                try:
                    result[key] = value.format(**variables)
                except KeyError:
                    result[key] = value
            elif isinstance(value, dict):
                result[key] = self._format_dict_template(value, variables)
            else:
                result[key] = value
        return result

    def _parse_response(
        self,
        data: Any,
        variable_type: str
    ) -> Dict[str, Any]:
        """Parsea la respuesta usando el mapeo del proveedor."""
        mapping = self.provider.response_mapping

        if not mapping:
            # Sin mapeo, intentar formato genérico
            return self._parse_generic_response(data, variable_type)

        result = {
            'timestamp': None,
            'value': None,
            'unit': 'unknown',
            'variable_type': variable_type,
            'metadata': {}
        }

        # Extraer campos según mapeo
        for target_field, source_path in mapping.items():
            try:
                value = self._extract_by_path(data, source_path)
                if target_field == 'timestamp' and value:
                    result['timestamp'] = self._parse_timestamp(value)
                elif target_field == 'value' and value is not None:
                    result['value'] = float(value)
                elif target_field in result:
                    result[target_field] = value
                else:
                    result['metadata'][target_field] = value
            except (KeyError, IndexError, TypeError, ValueError) as e:
                logger.debug(f"Could not extract {target_field}: {e}")

        return result

    def _parse_generic_response(
        self,
        data: Any,
        variable_type: str
    ) -> Dict[str, Any]:
        """Parseo genérico cuando no hay mapeo definido."""
        result = {
            'timestamp': None,
            'value': None,
            'unit': 'unknown',
            'variable_type': variable_type,
            'metadata': {}
        }

        # Si es una lista, tomar el último elemento
        if isinstance(data, list) and data:
            data = data[-1]

        if isinstance(data, dict):
            # Prioridad 1: Si hay variable específica como key (e.g. Twin: {"pc": [...]})
            if variable_type and variable_type in data:
                var_data = data[variable_type]
                
                # Recursión simple si el valor es lista/dict
                if isinstance(var_data, list) and var_data:
                    # Asumimos formato time-series, tomamos el último
                    var_data = var_data[-1] 
                
                if isinstance(var_data, dict):
                    # Búsqueda anidada en la estructura interna
                    for ts_field in ['timestamp', 'time', 'datetime', 'date_time', 'ts']:
                        if ts_field in var_data:
                            result['timestamp'] = self._parse_timestamp(var_data[ts_field])
                            break
                    
                    for val_field in ['value', 'val', 'measurement']:
                        if val_field in var_data:
                            try:
                                result['value'] = float(var_data[val_field])
                            except (ValueError, TypeError):
                                pass
                            break
                # Si es valor escalar
                elif var_data is not None:
                    try:
                        result['value'] = float(var_data)
                    except (ValueError, TypeError):
                        pass
                
                # Si encontramos valor, retornamos (o continuamos para buscar timestamp global si no estaba en nested)
                if result['value'] is not None:
                     return result

            # Prioridad 2: Buscar campos comunes en la raíz del dict
            for ts_field in ['timestamp', 'time', 'datetime', 'date_time', 'ts']:
                if ts_field in data:
                    result['timestamp'] = self._parse_timestamp(data[ts_field])
                    break
            
            for val_field in ['value', 'val', 'measurement', 'reading']:
                if val_field in data:
                    try:
                        result['value'] = float(data[val_field])
                    except (ValueError, TypeError):
                         pass
                    break

        return result



    def _extract_by_path(self, data: Any, path: str) -> Any:
        """Extrae un valor usando notación de puntos (soporta indices)."""
        # Reemplazar placeholders comunes si es necesario
        keys = path.split('.')
        current = data

        for key in keys:
            if current is None:
                return None
                
            if isinstance(current, dict):
                # Intentar match exacto primero
                if key in current:
                    current = current[key]
                # Soporte para keys numéricas en dicts (raro pero posible)
                elif key.isdigit() and int(key) in current:
                    current = current[int(key)]
                else:
                    raise KeyError(f"Key {key} not found in {current.keys()}")
            
            elif isinstance(current, list):
                if key.isdigit():
                    idx = int(key)
                    if 0 <= idx < len(current):
                        current = current[idx]
                    else:
                        raise IndexError(f"Index {idx} out of range (len={len(current)})")
                elif key in ['-1', 'last']:
                    if current:
                        current = current[-1]
                    else:
                        raise IndexError("List is empty")
                else:
                    raise KeyError(f"Invalid list index: {key}")
            else:
                 # Si llegamos aquí y hay más keys, es un error (scalar value)
                raise KeyError(f"Cannot navigate path '{key}' on scalar value {current}")

        return current

    def _parse_timestamp(self, value: Any) -> Optional[datetime]:
        """Parsea un timestamp en varios formatos."""
        if value is None:
            return None

        if isinstance(value, datetime):
            return value

        if isinstance(value, (int, float)):
            # Unix timestamp (segundos o milisegundos)
            if value > 1e12:  # Milisegundos
                return datetime.fromtimestamp(value / 1000)
            return datetime.fromtimestamp(value)

        if isinstance(value, str):
            # Intentar varios formatos
            formats = [
                "%Y-%m-%dT%H:%M:%S.%fZ",
                "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%dT%H:%M:%S.%f",
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d %H:%M:%S",
            ]
            for fmt in formats:
                try:
                    return datetime.strptime(value.replace('+00:00', 'Z'), fmt)
                except ValueError:
                    continue

            # ISO format con timezone
            try:
                return datetime.fromisoformat(value.replace('Z', '+00:00'))
            except ValueError:
                pass

        logger.warning(f"Could not parse timestamp: {value}")
        return None

    def test_connection(self) -> Dict[str, Any]:
        """Prueba la conexión con el proveedor."""
        try:
            response = requests.get(
                self.provider.base_url,
                headers=self.provider.get_auth_headers(),
                timeout=10
            )
            return {
                'success': response.status_code in [200, 401, 403],
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


def get_dynamic_handler(provider_name: str) -> Optional[DynamicAPIHandler]:
    """
    Factory function para obtener un handler dinámico.

    Args:
        provider_name: Nombre del proveedor (e.g., 'twin', 'nettra', 'novus')

    Returns:
        DynamicAPIHandler configurado o None si no existe el proveedor
    """
    try:
        provider = TelemetryProvider.objects.get(
            name=provider_name.lower(),
            is_active=True
        )
        return DynamicAPIHandler(provider)
    except TelemetryProvider.DoesNotExist:
        logger.warning(f"Provider not found: {provider_name}")
        return None


# Handlers legacy removidos. Todo el procesamiento se realiza vía DynamicAPIHandler o DynamicMQTTHandler.

# Import dynamic MQTT handler
from .mqtt_handler import DynamicMQTTHandler