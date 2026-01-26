"""User permissions."""

# Django REST Framework
from rest_framework.permissions import BasePermission
from django.contrib.auth.models import Group

def get_user_permissions(user):
    """Retrieve all permissions for a user from their groups."""
    if user.is_superuser:
        return set()

    permissions = set()
    for group in user.groups.all():
        for permission in group.permissions.all():
            permissions.add(f"{permission.content_type.app_label}.{permission.codename}")
    return permissions

class HasPermission(BasePermission):
    """
    Custom permission to check for action-specific permissions.
    """
    def has_permission(self, request, view):
        if request.user.is_superuser:
            return True

        required_permissions = getattr(view, 'required_permissions', [])
        if not required_permissions:
            return True

        user_permissions = get_user_permissions(request.user)
        return any(p in user_permissions for p in required_permissions)

class IsAccountOwner(BasePermission):
    """Allow access only to objects owned by the requesting user."""

    def has_object_permission(self, request, view, obj):
        """Check obj and user are the same."""
        return request.user == obj