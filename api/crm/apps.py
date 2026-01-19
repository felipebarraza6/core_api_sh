from django.apps import AppConfig


class CrmConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'api.crm'
    verbose_name = "CRM - Gestión de Clientes y Proyectos"

    def ready(self):
        import api.crm.signals
