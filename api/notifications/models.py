"""
Notifications Models
"""

from django.db import models
from api.core.models.utils import ModelApi
from api.core.models.users import User


class Notification(ModelApi):
    """Notification Model (renamed from NotificationsCatchment)."""

    point_catchment = models.ForeignKey(
        "telemetry.CatchmentPoint",
        related_name="notifications_list",
        on_delete=models.CASCADE,
        verbose_name="Punto de captacion",
    )
    title = models.CharField(max_length=300, verbose_name="Titulo")
    message = models.CharField(max_length=1300, verbose_name="Mensaje")

    VARIABLES_CHOICES = [
        ("NIVEL", "nivel"),
        ("CAUDAL", "caudal"),
        ("CAUDAL PROMEDIO", "caudal_promedio((diff/3600)*1000)"),
        ("TOTALIZADO", "totalizado"),
        ("TODOS", "todos"),
    ]
    TYPE_NOTIFICATION_CHOICES = [
        ("INFO", "Informativo"),
        ("WARNING", "Advertencia"),
        ("ALERT", "Alerta"),
        ("CRITICAL", "Crítico"),
        ("SUPPORT", "Soporte"),
    ]
    TYPE_ALERT_CHOICES = [
        ("MAX", "mas"),
        ("MIN", "menos"),
        ("EQUALS", "igual"),
    ]

    type_variable = models.CharField(
        max_length=300,
        choices=VARIABLES_CHOICES,
        verbose_name="Tipo variable",
        blank=True,
        null=True,
    )

    value = models.IntegerField(default=0, verbose_name="Valor")
    type_alert = models.CharField(
        max_length=300,
        choices=TYPE_ALERT_CHOICES,
        verbose_name="Tipo de alerta",
        blank=True,
        null=True,
    )

    type_notification = models.CharField(
        max_length=50,
        choices=TYPE_NOTIFICATION_CHOICES,
        verbose_name="Tipo de notificación",
    )

    start_date = models.DateField(blank=True, null=True, verbose_name="Fecha inicio")
    end_date = models.DateField(blank=True, null=True, verbose_name="Fecha fin")

    is_periodic = models.BooleanField(default=False, verbose_name="Cada registro")
    is_active = models.BooleanField(default=True, verbose_name="Activo")

    is_read = models.BooleanField(default=False, verbose_name="Leido")
    is_response = models.BooleanField(default=False, verbose_name="Respuesta")
    is_wait = models.BooleanField(default=False, verbose_name="Espera")
    is_finish = models.BooleanField(default=False, verbose_name="Finalizado")

    class Meta:
        db_table = "core_notificationscatchment"
        verbose_name = "Notificación"
        verbose_name_plural = "Notificaciones"

    def __str__(self):
        return f"{self.title} - {self.point_catchment}"


class NotificationResponse(ModelApi):
    """Notification Response Model (renamed from ResponseNotificationsCatchment)."""

    notification = models.ForeignKey(
        Notification,
        related_name="responses_list",
        on_delete=models.CASCADE,
        verbose_name="Notificación",
    )
    user = models.ForeignKey(
        User, related_name="responses_list", on_delete=models.CASCADE, verbose_name="Usuario"
    )
    response = models.CharField(max_length=1300, verbose_name="Respuesta")

    class Meta:
        db_table = "core_responsenotificationscatchment"
        verbose_name = "Respuesta de notificación"
        verbose_name_plural = "Respuestas de notificaciones"

    def __str__(self):
        return f"Response to {self.notification.title}"
