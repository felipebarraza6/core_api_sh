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

    profile_image = models.ImageField(
        upload_to='profile_images/',
        null=True,
        blank=True,
        verbose_name='Foto de perfil',
        help_text='Imagen de perfil del usuario.'
    )

    class Meta:
        verbose_name = 'Usuario'
        verbose_name_plural = 'Usuarios'

    def __str__(self):
        return self.email

    def get_short_name(self):
        return self.email
