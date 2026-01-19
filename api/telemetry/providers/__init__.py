"""
Dynamic Providers Module for SmartHydro API

This module provides a flexible architecture for telemetry providers,
allowing dynamic configuration and management of different IoT platforms.
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