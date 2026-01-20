"""
Dynamic Providers Module for SmartHydro API

This module provides a flexible architecture for telemetry providers,
allowing dynamic configuration and management of different IoT platforms.

Models available:
- TelemetryProvider: For data ingestion providers (Nettra, TData, etc.)
- CatchmentPointProvider: Association between points and telemetry providers
- MQTTProviderConfig: MQTT-specific configuration for providers
- PayloadParsingRule: Dynamic payload parsing rules
- CatchmentPointMQTT: Point-specific MQTT configuration
- ComplianceProvider: For regulatory compliance services (DGA, SMA, etc.)
- PointComplianceConfig: Association between points and compliance providers
- ManualComplianceRecord: Manual measurements for compliance
"""

# Global provider manager instance
_provider_manager = None


def get_provider_manager():
    """Get the global provider manager instance."""
    global _provider_manager
    if _provider_manager is None:
        from .manager import ProviderManager
        _provider_manager = ProviderManager()
    return _provider_manager