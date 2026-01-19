import os
import django
from django.conf import settings

if not settings.configured:
    settings.configure(
        INSTALLED_APPS=[
            'django.contrib.contenttypes',
            'django.contrib.auth',
            'api.core',
            'api.telemetry',
            'api.telemetry.providers',
        ],
        DATABASES={'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}},
        SECRET_KEY='test_key',
    )
    django.setup()

import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime
import json

from api.telemetry.providers.handlers import DynamicAPIHandler
# We can't import models directly if they are not migrated, but we can mock them
# or just use the imported classes if django.setup() worked.
from api.telemetry.providers.models import TelemetryProvider, CatchmentPointProvider

class TestDynamicAPIHandler(unittest.TestCase):
    def setUp(self):
        # Mock Provider
        self.provider = MagicMock(spec=TelemetryProvider)
        self.provider.name = 'test_provider'
        self.provider.base_url = 'https://api.test.com'
        self.provider.timeout_seconds = 30
        self.provider.auth_method = 'none'
        self.provider.auth_config = {}
        self.provider.endpoint_template = '/data/{point_code}/{variable}'
        self.provider.request_template = {}
        self.provider.response_mapping = {}

        # Mock Point Config
        self.point_config = MagicMock(spec=CatchmentPointProvider)
        self.point_config.point_code = 'DEVICE_001'
        self.point_config.config_override = {}
        self.point_config.provider = self.provider

        self.handler = DynamicAPIHandler(self.provider)

    def test_build_url_simple(self):
        url = self.handler._build_url(self.point_config, 'temp', None)
        self.assertEqual(url, 'https://api.test.com/data/DEVICE_001/temp')

    def test_nettra_config(self):
        # NETTRA Case
        self.provider.endpoint_template = '/v2/things/{point_code}/resources/{variable}'
        url = self.handler._build_url(self.point_config, 'temp', 'TOKEN_123')
        # Note: NETTRA puts token in point_code usually, or URL. 
        # If point_code is the token:
        self.assertEqual(url, 'https://api.test.com/v2/things/DEVICE_001/resources/temp')

    def test_novus_auth(self):
        # NOVUS Case
        self.provider.auth_method = 'api_key'
        self.provider.auth_config = {'header': 'authorization'}
        self.provider.get_auth_headers.return_value = {}  # Fix: Return dict, not Mock
        self.point_config.config_override = {'token': 'SECRET_TOKEN'}
        
        # Test auth header resolution
        headers = self.handler._get_auth_headers(self.point_config, 'RUNTIME_TOKEN')
        # Runtime token should override if passed
        self.assertEqual(headers['authorization'], 'RUNTIME_TOKEN')

    def test_twin_response_parsing(self):
        # TWIN Case: {"variable": [{"ts": 123, "value": 10}]}
        ts_ms = 1609459200000 # 2021-01-01 00:00:00 UTC
        data = {
            "temp": [
                {"ts": ts_ms, "value": 25.5}
            ]
        }
        # Generic parser should handle this
        result = self.handler._parse_generic_response(data, "temp")
        self.assertEqual(result['value'], 25.5)
        # Verify year matches local interpretation
        expected_year = datetime.fromtimestamp(ts_ms/1000).year
        self.assertEqual(result['timestamp'].year, expected_year)

    def test_response_mapping_nested(self):
        # NOVUS Case: {"result": [{"time": "...", "value": 10}]}
        self.provider.response_mapping = {
            'value': 'result.0.value',
            'timestamp': 'result.0.time'
        }
        data = {
            "result": [
                {"time": "2021-01-01T00:00:00Z", "value": 12.5}
            ]
        }
        result = self.handler._parse_response(data, 'temp')
        self.assertEqual(result['value'], 12.5)
        self.assertEqual(result['timestamp'].year, 2021)

    def test_login_flow(self):
        # TWIN Login Flow
        self.provider.auth_config = {
            'login_url': '/login',
            'username': 'user',
            'password': 'pass',
            'token_key': 'token'
        }
        
        with patch('requests.post') as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {'token': 'LOGIN_TOKEN'}
            
            # Resolve token
            token = self.handler._resolve_auth_token(self.point_config, None)
            
            self.assertEqual(token, 'LOGIN_TOKEN')
            mock_post.assert_called_once()
            self.assertIn('/login', mock_post.call_args[0][0])

if __name__ == '__main__':
    unittest.main()
