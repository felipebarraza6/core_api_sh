"""Auth views for void API."""
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from void.api.serializers import VoidUserProfileSerializer
from void.models import PointPermission

User = get_user_model()


class CurrentUserView(APIView):
    """Retorna el usuario autenticado con rol, permisos y puntos accesibles."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        profile = getattr(request.user, "void_profile", None)
        if profile is None:
            return Response(
                {"error": "Usuario no tiene perfil void"},
                status=status.HTTP_403_FORBIDDEN,
            )

        accessible_point_ids = self._get_accessible_point_ids(profile)
        data = VoidUserProfileSerializer(profile).data
        data["accessible_point_ids"] = accessible_point_ids
        return Response(data)

    def _get_accessible_point_ids(self, profile):
        if profile.role in {"admin", "operator"}:
            return None  # all points
        return list(
            PointPermission.objects.filter(
                user=profile,
                permission__in={"view", "change", "admin"},
            )
            .values_list("group__points__id", flat=True)
            .distinct()
        )


class ChangePasswordView(APIView):
    """Cambio de password propio."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        old_password = request.data.get("old_password")
        new_password = request.data.get("new_password")

        if not old_password or not new_password:
            return Response(
                {"error": "old_password y new_password son requeridos"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = request.user
        if not user.check_password(old_password):
            return Response(
                {"error": "Password actual incorrecto"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            validate_password(new_password, user)
        except Exception as exc:
            return Response(
                {"error": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.set_password(new_password)
        user.save(update_fields=["password"])
        return Response({"status": "ok"})
