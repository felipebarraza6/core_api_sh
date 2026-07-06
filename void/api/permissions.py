"""Permissions for void API."""
from rest_framework import permissions

from void.models import PointPermission


class VoidRolePermission(permissions.BasePermission):
    """Base permission that checks VoidUserProfile role.

    - admin/operator: full access.
    - client_admin/viewer: object-level access depends on PointObjectPermission.
    """

    ADMIN_ROLES = {"admin", "operator"}
    WRITE_ROLES = {"admin", "operator", "client_admin"}

    def _get_role(self, request):
        profile = getattr(request.user, "void_profile", None)
        if profile is None:
            return None
        return profile.role

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        role = self._get_role(request)
        if role in self.ADMIN_ROLES:
            return True
        if request.method in permissions.SAFE_METHODS:
            return role in {"client_admin", "viewer"}
        return role in self.WRITE_ROLES

    def has_object_permission(self, request, view, obj):
        role = self._get_role(request)
        if role in self.ADMIN_ROLES:
            return True
        return False


class PointObjectPermission(VoidRolePermission):
    """Object-level permission for Point-related resources.

    Admin/operator: all points.
    Client_admin/viewer: only points in groups where the user has permission.
    """

    def has_object_permission(self, request, view, obj):
        role = self._get_role(request)
        if role in self.ADMIN_ROLES:
            return True

        point = self._resolve_point(obj)
        if point is None:
            return False

        # Allowed actions depend on permission level.
        required = "change" if request.method not in permissions.SAFE_METHODS else "view"
        if role == "client_admin":
            required = "change"

        return self._has_point_permission(request.user, point, required)

    def _resolve_point(self, obj):
        if isinstance(obj, type("Point", (), {})) and hasattr(obj, "device"):
            return obj
        if hasattr(obj, "point"):
            return obj.point
        if hasattr(obj, "points"):
            # PointGroup: not object-level, handled by queryset filtering.
            return None
        return None

    def _has_point_permission(self, user, point, required):
        profile = getattr(user, "void_profile", None)
        if profile is None:
            return False

        groups = point.groups.all()
        permissions_qs = PointPermission.objects.filter(
            user=profile,
            group__in=groups,
        )
        levels = set(permissions_qs.values_list("permission", flat=True))

        if required == "view":
            return bool(levels & {"view", "change", "admin"})
        if required == "change":
            return bool(levels & {"change", "admin"})
        return "admin" in levels
