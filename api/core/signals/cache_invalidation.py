"""
Invalidación de caché para lookups estáticos frecuentes.

Se invalida automáticamente al crear, actualizar o eliminar instancias
de modelos cuyos listados completos se cachean en vistas API.
"""
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache

from api.core.models import Client, ProjectCatchments


@receiver([post_save, post_delete], sender=Client)
def invalidate_client_cache(sender, instance, **kwargs):
    """Borra la caché de clientes cuando hay cambios."""
    cache.delete("clients:all")


@receiver([post_save, post_delete], sender=ProjectCatchments)
def invalidate_project_cache(sender, instance, **kwargs):
    """Borra la caché de proyectos cuando hay cambios."""
    cache.delete("projects:all")
