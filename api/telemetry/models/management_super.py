"""Avanzados para Super Gestión de SmartHydro."""

from django.db import models
from api.telemetry.models.catchment_points import CatchmentPoint
from api.crm.models import Client
from api.core.models.utils import ModelApi


class SystemConfiguration(ModelApi):
    """Configuración global del sistema."""

    key = models.CharField(max_length=100, unique=True)
    value = models.JSONField()
    category = models.CharField(
        max_length=50,
        choices=[
            ("TELEMETRY", "Telemetría"),
            ("MQTT", "MQTT"),
            ("SECURITY", "Seguridad"),
            ("PERFORMANCE", "Performance"),
            ("NOTIFICATIONS", "Notificaciones"),
            ("REPORTING", "Reportes"),
        ],
    )
    is_encrypted = models.BooleanField(default=False)
    description = models.TextField(blank=True)

    class Meta:
        db_table = "core_systemconfiguration"
        verbose_name = "Configuración del Sistema"
        verbose_name_plural = "Configuraciones del Sistema"

    def __str__(self):
        return f"{self.category}: {self.key}"
