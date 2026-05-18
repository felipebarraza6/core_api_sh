"""
User Scope / Permission Layer for Chatbot
==========================================

Este módulo centraliza la lógica de filtrado por usuario para el chatbot.
Garantiza que un usuario solo pueda consultar datos de los puntos donde es
owner_user o users_viewers.

Staff / superusers ven todo el sistema.
"""

import logging
from typing import List, Optional, Set
from django.db.models import Q

logger = logging.getLogger(__name__)


def get_allowed_point_ids(user) -> Set[int]:
    """
    Retorna el set de IDs de CatchmentPoint que el usuario puede ver.

    - Staff / superusers: retornan set vacío como señal de "sin restricción".
    - Usuarios normales: puntos donde es owner_user o users_viewers.
    """
    if user.is_staff or user.is_superuser:
        return set()  # vacío = sin restricción

    from api.core.models import CatchmentPoint
    ids = CatchmentPoint.objects.filter(
        Q(owner_user=user) | Q(users_viewers=user)
    ).values_list("id", flat=True)
    return set(ids)


def get_allowed_clients(user) -> List[str]:
    """Retorna lista de nombres de clientes asociados al usuario."""
    if user.is_staff or user.is_superuser:
        return []

    from api.core.models import CatchmentPoint
    clients = CatchmentPoint.objects.filter(
        Q(owner_user=user) | Q(users_viewers=user)
    ).select_related("project__client").values_list(
        "project__client__name", flat=True
    ).distinct()
    return [c for c in clients if c]


def filter_points_by_user(queryset, allowed_ids: Set[int]):
    """Filtra un queryset de CatchmentPoint por IDs permitidos."""
    if not allowed_ids:
        return queryset
    return queryset.filter(id__in=allowed_ids)


def is_point_allowed(point_id: int, allowed_ids: Set[int]) -> bool:
    """Verifica si un punto específico está permitido para el usuario."""
    if not allowed_ids:
        return True
    return point_id in allowed_ids


def is_client_allowed(client_name: str, user) -> bool:
    """
    Verifica si el usuario tiene al menos un punto del cliente.
    Staff siempre True.
    """
    if user.is_staff or user.is_superuser:
        return True

    allowed_clients = get_allowed_clients(user)
    if not allowed_clients:
        return False

    return any(
        client_name.lower() in allowed.lower() or allowed.lower() in client_name.lower()
        for allowed in allowed_clients
    )
