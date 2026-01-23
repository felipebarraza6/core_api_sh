"""
Celery Tasks Package
Modern task queue system replacing traditional cronjobs
"""

# Import all task modules to ensure they are registered
from . import telemetry, alerts, reports, maintenance, monitoring, compliance_unified

__all__ = ['telemetry', 'alerts', 'reports', 'maintenance', 'monitoring', 'compliance_unified']