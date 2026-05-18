"""User permissions."""

# Django REST Framework
from rest_framework.permissions import BasePermission, IsAdminUser

class IsAccountOwner(BasePermission):
	"""Allow access only to objects owned by the requestiong user."""

	def has_object_permission(self, request, view, obj):
		"""Check obj and user are the same."""
		return request.user == obj


class IsStaffOrSuperUser(BasePermission):
    """Allow access only to staff members or superusers."""

    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            (request.user.is_staff or request.user.is_superuser)
        )