import logging
from rest_framework.response import Response
from rest_framework.decorators import api_view
from rest_framework.decorators import action

from rest_framework import status
from rest_framework import mixins, viewsets, status


from rest_framework import generics

# Filters
from django_filters import rest_framework as filters
from rest_framework.filters import SearchFilter, OrderingFilter

# Permissions
from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError

from rest_framework.permissions import (
    AllowAny,
    IsAuthenticated
)

from api.core.permissions import IsAccountOwner

# Models
from api.core.models import User

# Serializers
from api.core.serializers.users import UserProfile, UserLoginSerializer, UserModelSerializer, UserSignUpSerializer, UserAvatarUploadSerializer

from drf_spectacular.utils import extend_schema, extend_schema_view

logger = logging.getLogger(__name__)


@extend_schema_view(
    list=extend_schema(summary="Listar usuarios", description="Lista de usuarios verificados del sistema. Solo staff."),
    retrieve=extend_schema(summary="Detalle de usuario", description="Perfil completo de un usuario. Requiere ser el dueño o staff."),
    update=extend_schema(summary="Actualizar usuario"),
    partial_update=extend_schema(summary="Actualizar parcialmente usuario"),
    destroy=extend_schema(summary="Eliminar usuario"),
)
class UserViewSet(mixins.RetrieveModelMixin,
                  mixins.UpdateModelMixin,
                  mixins.ListModelMixin,
                  mixins.DestroyModelMixin,
                  viewsets.GenericViewSet,):

    def get_permissions(self):
        """Assign permissions based on action."""
        if self.action in ['login']:
            permissions = [AllowAny]
        elif self.action in ['retrieve']:
            permissions = [IsAuthenticated, IsAccountOwner]
        else:
            permissions = [IsAuthenticated]
        return [p() for p in permissions]

    filter_backends = (filters.DjangoFilterBackend, SearchFilter, OrderingFilter)
    queryset = User.objects.filter(is_verified=True)
    serializer_class = UserModelSerializer
    lookup_field = 'username'
    search_fields = ['username', 'email', 'first_name', 'last_name']
    ordering_fields = ['username', 'email', 'date_joined']

    @extend_schema(summary="Login legacy", description="Autenticación con email y password. Devuelve token + perfil completo.")
    @action(detail=False, methods=['post'])
    def login(self, request):
        """User sign in."""
        serializer = UserLoginSerializer(
            data=request.data)
        serializer.is_valid(raise_exception=True)
        user, token = serializer.save()
        data = {
            'success': True,
            'message': 'Login exitoso',
            'user': UserProfile(user, context={'user': user}).data,
            'access_token': token
        }
        response = Response(data, status=status.HTTP_200_OK)
        response['Authorization'] = f'Bearer {token}'
        return response

    @extend_schema(summary="Registro de usuario", description="Crear nueva cuenta de usuario. Auth: público.")
    @action(detail=False, methods=['post'])
    def signup(self, request):
        serializer = UserSignUpSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        data = UserModelSerializer(user).data
        return Response(data, status=status.HTTP_201_CREATED)

    @extend_schema(summary="Perfil propio", description="Devuelve el perfil del usuario autenticado.")
    @action(detail=False, methods=['get'], url_path='me')
    def me(self, request):
        """Devuelve el perfil del usuario autenticado."""
        user = request.user
        data = {
            'user': UserProfile(user, context={'user': user}).data,
        }
        return Response(data)

    @extend_schema(summary="Cambiar contraseña", description="Requiere current_password y new_password.")
    @action(detail=False, methods=['post'], url_path='change-password')
    def change_password(self, request):
        """Cambio de contraseña para usuario autenticado."""
        user = request.user
        current_password = request.data.get('current_password')
        new_password = request.data.get('new_password')

        if not current_password or not new_password:
            return Response(
                {'error': 'Se requieren current_password y new_password.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not user.check_password(current_password):
            return Response(
                {'error': 'La contraseña actual es incorrecta.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            password_validation.validate_password(new_password, user)
        except ValidationError as e:
            return Response(
                {'error': ' '.join(e.messages)},
                status=status.HTTP_400_BAD_REQUEST
            )

        user.set_password(new_password)
        user.save(update_fields=['password'])

        return Response({'success': True, 'message': 'Contraseña actualizada correctamente.'})

    @extend_schema(summary="Subir foto de perfil", description="Sube o actualiza la foto de perfil del usuario autenticado. Body: multipart/form-data con el campo 'profile_image'.")
    @action(detail=False, methods=['post'], url_path='me/avatar')
    def upload_avatar(self, request):
        """Sube o actualiza la foto de perfil del usuario autenticado."""
        user = request.user
        serializer = UserAvatarUploadSerializer(user, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(
                {'success': False, 'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        serializer.save()
        return Response(
            {
                'success': True,
                'message': 'Foto de perfil actualizada correctamente.',
                'profile_image': serializer.instance.profile_image.url if serializer.instance.profile_image else None,
            },
            status=status.HTTP_200_OK
        )

    def retrieve(self, request, *args, **kwargs):
        """Add extra data to the response."""
        response = super().retrieve(request, *args, **kwargs)
        user = self.get_object()
        logger.debug(f"User retrieve: {user.email} (ID: {user.id})")
        data = {
            'user': UserProfile(user, context={'user': user}).data,
        }
        response.data = data
        return response
