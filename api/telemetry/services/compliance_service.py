"""
Compliance Service

Generic service for submitting telemetry data to regulatory compliance
providers (DGA, SMA, etc.) using dynamic configuration.
"""

import logging
import re
import json
from datetime import datetime
from typing import Optional, Dict, Any, Tuple, Union

import requests
from django.utils import timezone

from api.telemetry.providers.compliance_models import (
    ComplianceProvider,
    PointComplianceConfig,
    ManualComplianceRecord,
)
from api.telemetry.models import TelemetryRecord

logger = logging.getLogger(__name__)


class ComplianceService:
    """
    Generic service for submitting data to compliance providers.
    
    Handles authentication, payload building, and submission for
    any configured compliance provider (DGA, SMA, etc.)
    """

    def __init__(self):
        self._token_cache = {}  # Cache OAuth tokens by provider ID

    def submit_telemetry_record(
        self,
        record: TelemetryRecord,
        config: PointComplianceConfig
    ) -> Tuple[bool, str, str]:
        """
        Submit a telemetry record to a compliance provider.
        
        Args:
            record: TelemetryRecord to submit
            config: Point compliance configuration
            
        Returns:
            Tuple of (success, message, voucher)
        """
        return self._submit_record(record, config, 'telemetry')

    def submit_manual_record(
        self,
        record: ManualComplianceRecord
    ) -> Tuple[bool, str, str]:
        """
        Submit a manual compliance record.
        
        Args:
            record: ManualComplianceRecord to submit
            
        Returns:
            Tuple of (success, message, voucher)
        """
        return self._submit_record(record, record.config, 'manual')

    def _submit_record(
        self,
        record: Union[TelemetryRecord, ManualComplianceRecord],
        config: PointComplianceConfig,
        record_type: str
    ) -> Tuple[bool, str, str]:
        """
        Internal method to submit any type of record.
        """
        provider = config.provider

        try:
            # 1. Get authentication headers
            auth_headers = self._authenticate(provider, config)
            
            # 2. Build payload using template
            payload = self._build_payload(record, config, provider, record_type)
            
            if not payload:
                return False, "Failed to build payload", ""
            
            # 3. Build URL
            url = self._build_url(provider, config)
            
            # 4. Send request
            success, message, voucher = self._send_request(
                url, payload, auth_headers, provider
            )
            
            # 5. Record result
            if success:
                config.record_success()
            else:
                config.record_error(message)
            
            return success, message, voucher

        except Exception as exc:
            error_msg = f"Submission error: {exc}"
            logger.error(error_msg)
            config.record_error(error_msg)
            return False, error_msg, ""

    def _authenticate(
        self,
        provider: ComplianceProvider,
        config: PointComplianceConfig
    ) -> Dict[str, str]:
        """
        Authenticate with the provider and return headers.
        
        Uses credentials from config override if available,
        otherwise uses provider's default credentials.
        """
        credentials = config.get_effective_credentials()
        auth_method = provider.auth_method

        if auth_method == 'none':
            return {}

        elif auth_method == 'bearer':
            token = credentials.get('token', '')
            return {'Authorization': f'Bearer {token}'}

        elif auth_method == 'basic':
            import base64
            username = credentials.get('username', '')
            password = credentials.get('password', '')
            creds_b64 = base64.b64encode(f"{username}:{password}".encode()).decode()
            return {'Authorization': f'Basic {creds_b64}'}

        elif auth_method == 'api_key':
            key_header = credentials.get('header', 'X-API-Key')
            key_value = credentials.get('key', '')
            return {key_header: key_value}

        elif auth_method == 'oauth2':
            # Get token from auth endpoint
            token = self._get_oauth_token(provider, credentials)
            if token:
                return {'Authorization': f'Bearer {token}'}
            return {}

        elif auth_method == 'custom':
            # Custom auth: return credentials as headers
            headers = {}
            for key, value in credentials.items():
                if key.startswith('header_'):
                    header_name = key.replace('header_', '')
                    headers[header_name] = value
            return headers

        return {}

    def _get_oauth_token(
        self,
        provider: ComplianceProvider,
        credentials: Dict[str, Any]
    ) -> Optional[str]:
        """
        Get OAuth2 token from provider's auth endpoint.
        
        Uses cache to avoid requesting new tokens frequently.
        """
        cache_key = f"{provider.id}:{hash(json.dumps(credentials, sort_keys=True))}"
        
        # Check cache
        cached = self._token_cache.get(cache_key)
        if cached:
            token, expiry = cached
            if expiry > timezone.now():
                return token

        try:
            auth_url = f"{provider.base_url.rstrip('/')}{provider.auth_endpoint}"
            
            # Build auth payload
            username_field = credentials.get('username_field', 'usuario')
            password_field = credentials.get('password_field', 'password')
            
            auth_payload = {
                username_field: credentials.get('username', ''),
                password_field: credentials.get('password', ''),
            }

            response = requests.post(
                auth_url,
                json=auth_payload,
                headers={'Content-Type': 'application/json'},
                timeout=provider.timeout_seconds
            )
            response.raise_for_status()

            token_field = credentials.get('token_response_field', 'token')
            token = response.json().get(token_field)

            if token:
                # Cache for 50 minutes
                from datetime import timedelta
                expiry = timezone.now() + timedelta(minutes=50)
                self._token_cache[cache_key] = (token, expiry)
                return token

        except Exception as exc:
            logger.error(f"OAuth token error for {provider.name}: {exc}")

        return None

    def _build_payload(
        self,
        record: Union[TelemetryRecord, ManualComplianceRecord],
        config: PointComplianceConfig,
        provider: ComplianceProvider,
        record_type: str
    ) -> Optional[Dict[str, Any]]:
        """
        Build request payload using provider's template.
        
        Substitutes {config.*} and {record.*} variables with actual values.
        """
        template = provider.payload_template
        if not template:
            return {}

        try:
            # Build context for variable substitution
            context = {
                'config': config.config_data,
                'record': self._get_record_context(record, record_type),
            }

            # Process template recursively
            return self._process_template(template, context)

        except Exception as exc:
            logger.error(f"Payload build error: {exc}")
            return None

    def _get_record_context(
        self,
        record: Union[TelemetryRecord, ManualComplianceRecord],
        record_type: str
    ) -> Dict[str, Any]:
        """
        Build record context dictionary for template substitution.
        """
        if record_type == 'telemetry':
            return {
                'timestamp': record.timestamp,
                'data': record.data,
                'point_id': record.point_id,
            }
        else:  # manual
            return {
                'timestamp': record.measurement_timestamp,
                'data': record.data,
                'point_id': record.config.point_id,
            }

    def _process_template(
        self,
        template: Any,
        context: Dict[str, Any]
    ) -> Any:
        """
        Recursively process template, substituting variables.
        
        Supports:
        - {config.field_name} - Point configuration data
        - {record.data.field_name} - Record data field
        - {record.timestamp} - Record timestamp
        - {record.timestamp|format:%Y-%m-%d} - Formatted timestamp
        """
        if isinstance(template, str):
            return self._substitute_string(template, context)
        elif isinstance(template, dict):
            return {k: self._process_template(v, context) for k, v in template.items()}
        elif isinstance(template, list):
            return [self._process_template(item, context) for item in template]
        else:
            return template

    def _substitute_string(self, template_str: str, context: Dict[str, Any]) -> Any:
        """
        Substitute variables in a string template.
        """
        # Pattern: {path.to.value} or {path.to.value|format:%Y-%m-%d}
        pattern = r'\{([^}]+)\}'
        
        def replacer(match):
            expr = match.group(1)
            
            # Check for format filter
            if '|' in expr:
                path, filter_expr = expr.split('|', 1)
                value = self._resolve_path(path, context)
                return self._apply_filter(value, filter_expr)
            else:
                value = self._resolve_path(expr, context)
                return str(value) if value is not None else ''
        
        result = re.sub(pattern, replacer, template_str)
        
        # Try to parse as number if result looks numeric
        if result.replace('.', '').replace('-', '').isdigit():
            try:
                if '.' in result:
                    return float(result)
                return int(result)
            except ValueError:
                pass
        
        return result

    def _resolve_path(self, path: str, context: Dict[str, Any]) -> Any:
        """
        Resolve a dotted path like 'config.codigo_obra' in context.
        """
        parts = path.strip().split('.')
        value = context
        
        for part in parts:
            if isinstance(value, dict):
                value = value.get(part)
            elif hasattr(value, part):
                value = getattr(value, part)
            else:
                return None
            
            if value is None:
                return None
        
        return value

    def _apply_filter(self, value: Any, filter_expr: str) -> str:
        """
        Apply a filter to a value.
        
        Supported filters:
        - format:%Y-%m-%d - strftime format for datetime
        """
        if filter_expr.startswith('format:'):
            fmt = filter_expr[7:]
            if isinstance(value, datetime):
                return value.strftime(fmt)
            elif hasattr(value, 'strftime'):
                return value.strftime(fmt)
        
        return str(value)

    def _build_url(
        self,
        provider: ComplianceProvider,
        config: PointComplianceConfig
    ) -> str:
        """
        Build the submission URL from provider template and config data.
        """
        base_url = provider.base_url.rstrip('/')
        endpoint = provider.data_endpoint_template
        
        # Substitute config variables in endpoint
        context = {'config': config.config_data}
        endpoint = self._substitute_string(endpoint, context)
        
        return f"{base_url}{endpoint}"

    def _send_request(
        self,
        url: str,
        payload: Dict[str, Any],
        headers: Dict[str, str],
        provider: ComplianceProvider
    ) -> Tuple[bool, str, str]:
        """
        Send HTTP request to the compliance provider.
        
        Returns:
            Tuple of (success, message, voucher)
        """
        headers['Content-Type'] = 'application/json'
        headers['User-Agent'] = 'SmartHydro/2.0'

        try:
            logger.info(f"Sending to {provider.name}: {url}")
            logger.debug(f"Payload: {json.dumps(payload)[:500]}")

            response = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=provider.timeout_seconds
            )

            if response.status_code == 200:
                return self._parse_success_response(response, provider)
            else:
                return False, f"HTTP {response.status_code}: {response.text[:200]}", ""

        except requests.exceptions.Timeout:
            return False, f"Timeout after {provider.timeout_seconds}s", ""
        except requests.exceptions.RequestException as exc:
            return False, f"Request error: {exc}", ""
        except Exception as exc:
            return False, f"Unexpected error: {exc}", ""

    def _parse_success_response(
        self,
        response: requests.Response,
        provider: ComplianceProvider
    ) -> Tuple[bool, str, str]:
        """
        Parse successful response using provider's response_mapping.
        """
        try:
            resp_data = response.json()
            mapping = provider.response_mapping

            if not mapping:
                return True, "OK", ""

            # Check success condition
            success_field = mapping.get('success_field')
            success_value = mapping.get('success_value')
            
            if success_field:
                actual_value = self._resolve_path(success_field, resp_data)
                if actual_value != success_value:
                    msg = mapping.get('message_field', '')
                    if msg:
                        msg = self._resolve_path(msg, resp_data) or ""
                    return False, f"Provider error: {msg}", ""

            # Get voucher
            voucher_field = mapping.get('voucher_field', '')
            voucher = ""
            if voucher_field:
                voucher = str(self._resolve_path(voucher_field, resp_data) or "")

            # Get message
            message_field = mapping.get('message_field', '')
            message = "OK"
            if message_field:
                message = str(self._resolve_path(message_field, resp_data) or "OK")

            return True, message, voucher

        except Exception as exc:
            logger.warning(f"Response parse error: {exc}")
            return True, "OK (parse error)", ""


# Singleton instance
_compliance_service = None


def get_compliance_service() -> ComplianceService:
    """Get the global compliance service instance."""
    global _compliance_service
    if _compliance_service is None:
        _compliance_service = ComplianceService()
    return _compliance_service
