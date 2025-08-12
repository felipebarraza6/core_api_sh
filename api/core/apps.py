"""App Config"""
from django.apps import AppConfig


class CoreAppConfig(AppConfig):
    """AppConfig"""
    name = 'api.core'
    verbose_name = 'core'

    def ready(self):
        import api.core.signals
