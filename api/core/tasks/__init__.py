"""
Celery Tasks Package
Modern task queue system replacing traditional cronjobs
"""

# Import all task modules to ensure they are registered
from . import telemetry, dga, alerts, reports, maintenance, monitoring

__all__ = ['telemetry', 'dga', 'alerts', 'reports', 'maintenance', 'monitoring']