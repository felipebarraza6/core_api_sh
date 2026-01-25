from django.apps import AppConfig

class DynamicRegistryConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'api.dynamic_registry'
    verbose_name = "Registro Dinámico de Módulos"
