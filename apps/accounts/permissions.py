from rest_framework.permissions import BasePermission
from django.contrib.auth import get_user_model

User = get_user_model()


class IsAdmin(BasePermission):
    """Autorise uniquement les Administrateurs (rôle ADMIN)."""
    message = 'Accès réservé aux Administrateurs.'

    def has_permission(self, request, view):
        return (
            request.user and
            request.user.is_authenticated and
            request.user.role == User.Role.ADMIN
        )
