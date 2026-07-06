"""MQTT configuration models for void."""
from django.db import models

from .base import VoidModel


class MqttTopicConfig(VoidModel):
    """Configuración de topics MQTT para un proveedor.

    Permite que el equipo de hardware publique a topics definidos desde la UI
    y que void se suscriba/escuche esos topics.
    """

    QOS_CHOICES = [
        (0, "At most once (0)"),
        (1, "At least once (1)"),
        (2, "Exactly once (2)"),
    ]

    provider = models.ForeignKey(
        "void.Provider",
        on_delete=models.CASCADE,
        related_name="mqtt_topics",
        verbose_name="Proveedor",
    )
    name = models.CharField(
        max_length=200,
        verbose_name="Nombre",
    )
    topic_template = models.CharField(
        max_length=500,
        verbose_name="Template de topic",
        help_text="Variables: {external_id}, {variable}, {point_code}. Ej: devices/{external_id}/{variable}",
    )
    qos = models.IntegerField(
        choices=QOS_CHOICES,
        default=1,
        verbose_name="QoS",
    )
    payload_parser = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Parser de payload",
        help_text='Ej: {"value_field": "v", "timestamp_field": "ts", "unit_field": "u"}',
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Activo",
        db_index=True,
    )

    class Meta:
        verbose_name = "Topic MQTT"
        verbose_name_plural = "Topics MQTT"
        ordering = ["provider", "name"]

    def __str__(self):
        return f"{self.provider} | {self.topic_template}"
