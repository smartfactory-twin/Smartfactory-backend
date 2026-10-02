from rest_framework.permissions import BasePermission
from .models import User


class IsAdminRole(BasePermission):
    """Autorise uniquement les Administrateurs."""
    message = 'Accès réservé aux Administrateurs.'

    def has_permission(self, request, view):
        return (
            request.user and
            request.user.is_authenticated and
            request.user.role == User.Role.ADMIN
        )


class IsAdminOrTechnician(BasePermission):
    """Autorise les Administrateurs et les Techniciens Terrain."""
    message = 'Accès réservé aux Administrateurs et Techniciens.'

    def has_permission(self, request, view):
        return (
            request.user and
            request.user.is_authenticated and
            request.user.role in [User.Role.ADMIN, User.Role.TECHNICIAN]
        )


class IsAnyRole(BasePermission):
    """Autorise tous les rôles (Admin, Technicien, Opérateur) — juste connecté."""
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated
