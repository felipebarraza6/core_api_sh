"""Suscripciones de notificaciones push (Web Push / navegador y app móvil)."""

from django.db import models
from django.conf import settings

from .utils import ModelApi


class WebPushSubscription(ModelApi):
    """
    Una suscripción push por dispositivo/navegador.

    - channel_type='WEB': se usa Web Push estándar (VAPID + service worker).
      `endpoint` es la URL del servicio push (FCM/APNs del navegador),
      `p256dh`/`auth` son las clakes de cifrado del endpoint.
    - channel_type='FCM': pensada para app móvil nativa; `endpoint` guarda el
      device token y `p256dh`/`auth` quedan vacíos. El envío FCM se agrega
      aparte (ver docs/WEB_PUSH.md), el modelo ya lo soporta.

    Una fila por dispositivo. Si el usuario tiene varios dispositivos,
    tiene varias filas.
    """

    WEB = "WEB"
    FCM = "FCM"
    CHANNEL_CHOICES = [
        (WEB, "Navegador (Web Push)"),
        (FCM, "App móvil (FCM)"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="push_subscriptions",
        verbose_name="Usuario",
        db_index=True,
    )
    channel_type = models.CharField(
        max_length=20,
        choices=CHANNEL_CHOICES,
        default=WEB,
        verbose_name="Canal",
    )
    endpoint = models.URLField(
        max_length=1000,
        unique=True,
        verbose_name="Endpoint / device token",
    )
    p256dh = models.CharField(
        max_length=200,
        blank=True,
        default="",
        verbose_name="Clave pública ECDH (p256dh)",
    )
    auth = models.CharField(
        max_length=200,
        blank=True,
        default="",
        verbose_name="Clave de autenticación (auth)",
    )
    user_agent = models.CharField(
        max_length=300,
        blank=True,
        default="",
        verbose_name="User agent",
        help_text="Solo diagnóstico: navegador/ SO desde el que se suscribió.",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Activa",
        help_text="Se pone en False si el proveedor de push responde 404/410 "
                  "(suscripción revocada o expirada).",
    )
    last_seen_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Última vez que se usó",
    )

    class Meta:
        verbose_name = "Suscripción push"
        verbose_name_plural = "Suscripciones push"
        ordering = ["-created"]
        indexes = [
            models.Index(
                fields=["user", "is_active"],
                name="ik_pushsub_user_active_idx",
            ),
        ]

    def __str__(self):
        estado = "activa" if self.is_active else "inactiva"
        return f"[{self.channel_type}] {self.user} ({estado})"
