from django.apps import AppConfig


class AnalyticsConfig(AppConfig):
    default_auto_field = "django.db.models.AutoField"
    name = "api.analytics"
    label = "analytics"
    verbose_name = "API Analytics"
