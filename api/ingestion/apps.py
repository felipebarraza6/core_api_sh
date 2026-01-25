from django.apps import AppConfig

class IngestionConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'api.ingestion'
    verbose_name = 'Gestor de Ingesta y Protocolos'
