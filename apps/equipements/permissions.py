from rest_framework.permissions import BasePermission, SAFE_METHODS


class IsAdminOrReadOnly(BasePermission):
    """SAFE_METHODS pour tous les authentifiés, écriture ADMIN seulement."""
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in SAFE_METHODS:
            return True
        return request.user.role == 'ADMIN'


class MachineAccessPermission(BasePermission):
    """ADMIN tout, TECHNICIEN tout, OPERATEUR SAFE_METHODS seulement."""
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        role = request.user.role
        if role == 'ADMIN':
            return True
        if role == 'TECHNICIEN':
            return True
        if role == 'OPERATEUR':
            return request.method in SAFE_METHODS
        return False
