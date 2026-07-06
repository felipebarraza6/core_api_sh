"""User models for void."""
from django.conf import settings
from django.db import models

from .base import VoidModel


class VoidUserProfile(VoidModel):
    """Perfil complementario del usuario para void.

    No reemplaza a settings.AUTH_USER_MODEL ni a api.core.User.
    Se usa para roles, permisos y preferencias del nuevo subsistema.
    """

    ROLE_CHOICES = [
        ("admin", "Administrador"),
        ("operator", "Operador"),
        ("client_admin", "Administrador de Cliente"),
        ("viewer", "Visualizador"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="void_profile",
        verbose_name="Usuario",
    )
    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default="viewer",
        verbose_name="Rol",
    )
    phone = models.CharField(
        max_length=120,
        blank=True,
        default="",
        verbose_name="Teléfono",
    )
    timezone = models.CharField(
        max_length=80,
        blank=True,
        default="America/Santiago",
        verbose_name="Zona horaria",
    )
    notification_preferences = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Preferencias de notificación",
        help_text='Ej: {"email": true, "sms": false, "whatsapp": false}',
    )
    legacy_user_id = models.PositiveIntegerField(
        blank=True,
        null=True,
        verbose_name="ID usuario legacy",
        help_text="ID del usuario en api.core.User para migración futura.",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Activo",
    )

    class Meta:
        verbose_name = "Perfil de usuario (void)"
        verbose_name_plural = "Perfiles de usuario (void)"
        indexes = [
            models.Index(fields=["role", "is_active"]),
            models.Index(fields=["legacy_user_id"]),
        ]

    def __str__(self):
        return f"{self.user} ({self.role})"
