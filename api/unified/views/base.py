"""
Base ViewSet y Mixins para API v4.

Proporciona funcionalidad común para todos los ViewSets de la API unificada.
"""

from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from django.db.models import Q


class BaseViewSet(viewsets.ModelViewSet):
    """
    ViewSet base con funcionalidad común para API v4.

    Características:
    - Filtrado automático por usuario (para modelos con owner_user)
    - Respuestas estandarizadas
    - Logging de acciones
    """

    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """
        Filtra queryset basado en permisos del usuario.
        Staff puede ver todo, usuarios normales solo lo suyo.
        """
        queryset = super().get_queryset()
        user = self.request.user

        if user.is_staff:
            return queryset

        # Detectar si el modelo tiene owner_user o users_viewers
        model = queryset.model

        if hasattr(model, 'owner_user'):
            if hasattr(model, 'users_viewers'):
                return queryset.filter(
                    Q(owner_user=user) | Q(users_viewers=user)
                ).distinct()
            return queryset.filter(owner_user=user)

        return queryset

    def get_serializer_class(self):
        """
        Retorna serializer según la acción.
        Subclases deben definir:
        - serializer_class (default)
        - serializer_class_list (opcional, para list)
        - serializer_class_detail (opcional, para retrieve)
        - serializer_class_create (opcional, para create/update)
        """
        if self.action == 'list' and hasattr(self, 'serializer_class_list'):
            return self.serializer_class_list

        if self.action == 'retrieve' and hasattr(self, 'serializer_class_detail'):
            return self.serializer_class_detail

        if self.action in ['create', 'update', 'partial_update']:
            if hasattr(self, 'serializer_class_create'):
                return self.serializer_class_create

        return super().get_serializer_class()

    def success_response(self, data, message=None, status_code=status.HTTP_200_OK):
        """Respuesta exitosa estandarizada."""
        response_data = {
            "success": True,
            "data": data,
        }
        if message:
            response_data["message"] = message
        return Response(response_data, status=status_code)

    def error_response(self, message, errors=None, status_code=status.HTTP_400_BAD_REQUEST):
        """Respuesta de error estandarizada."""
        response_data = {
            "success": False,
            "message": message,
        }
        if errors:
            response_data["errors"] = errors
        return Response(response_data, status=status_code)


class ReadOnlyBaseViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet base de solo lectura.
    """

    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """Filtrado por permisos."""
        queryset = super().get_queryset()
        user = self.request.user

        if user.is_staff:
            return queryset

        model = queryset.model

        if hasattr(model, 'owner_user'):
            if hasattr(model, 'users_viewers'):
                return queryset.filter(
                    Q(owner_user=user) | Q(users_viewers=user)
                ).distinct()
            return queryset.filter(owner_user=user)

        return queryset
