"""User Model."""

# Django
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator

# Utils
from .utils import ModelApi


class User(ModelApi, AbstractUser):

    email = models.EmailField(
        'email address',
        unique=True,
        error_messages={
            'unique': 'El usuario ya existe.'
        }
    )

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username', 'first_name', 'last_name']
    txt_password = models.CharField(
        max_length=1200,
        blank=True,
        null=True,
        default='',
        help_text='DEPRECATED: No usar. Mantener vacío. Las contraseñas se hashean automáticamente.'
    )

    is_verified = models.BooleanField(
        default=True,
        help_text='Se establece en verdadero cuando el usuario ha verificado su dirección de correo electrónico'
    )

    is_client_admin = models.BooleanField(
        default=False,
        help_text='Administrador de clientes. Puede editar datos asociados a sus clientes asignados.'
    )

    notify_email = models.BooleanField(
        default=True,
        help_text='Si está activo, el usuario recibe correos del subsistema de tickets (menciones, SLA, etc.).'
    )

    # ── Preferencias de notificación push (in-app + navegador/app móvil) ─────
    # `notify_push` es el interruptor general. Los tres flags de abajo son
    # filtros por tipo de evento; sólo tienen efecto si `notify_push` es True.
    # El permiso real lo otorga el navegador/ sistema operativo: aunque estos
    # flags estén en True, si el usuario no dio permiso no llega nada.
    notify_push = models.BooleanField(
        default=True,
        verbose_name='Recibir notificaciones push',
        help_text='Interruptor general de notificaciones push (navegador / app móvil).',
    )
    push_tickets = models.BooleanField(
        default=True,
        verbose_name='Push de tickets',
        help_text='Notificar respuestas, cambios de estado y menciones en tickets.',
    )
    push_alerts = models.BooleanField(
        default=True,
        verbose_name='Push de alertas',
        help_text='Notificar alertas de telemetría de los puntos propios / visibles.',
    )
    push_announcements = models.BooleanField(
        default=True,
        verbose_name='Push de avisos',
        help_text='Notificar avisos y anuncios generales del sistema.',
    )

    profile_image = models.ImageField(
        upload_to='profile_images/',
        null=True,
        blank=True,
        verbose_name='Foto de perfil',
        help_text='Imagen de perfil del usuario.'
    )

    recibir_reporte = models.BooleanField(
        default=False,
        verbose_name='Recibir reporte semanal',
        help_text='Si está activo, el usuario (owner) recibe el reporte semanal automáticamente con todos sus puntos.'
    )

    reporte_cc_emails = models.TextField(
        blank=True,
        default='',
        verbose_name='CC reporte semanal',
        help_text='Emails adicionales (separados por coma) que reciben copia del reporte semanal.'
    )

    class Meta:
        verbose_name = 'Usuario'
        verbose_name_plural = 'Usuarios'

    def __str__(self):
        return self.email

    def get_short_name(self):
        return self.email
