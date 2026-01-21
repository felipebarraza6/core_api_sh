"""
Compliance App Configuration
"""

from django.apps import AppConfig


class ComplianceConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'api.compliance'
    verbose_name = 'Cumplimiento Normativo'
