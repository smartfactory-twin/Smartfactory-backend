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
    """
    ADMIN     : toutes les opérations (CRUD complet)
    TECHNICIEN: lecture (GET) + modification (PATCH/PUT) uniquement
    OPERATEUR : lecture seule (GET, HEAD, OPTIONS)
    """
    TECHNICIEN_METHODS = (*SAFE_METHODS, 'PUT', 'PATCH')

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        role = request.user.role
        if role == 'ADMIN':
            return True
        if role == 'TECHNICIEN':
            return request.method in self.TECHNICIEN_METHODS
        if role == 'OPERATEUR':
            return request.method in SAFE_METHODS
        return False


class IsAdminRole(BasePermission):
    """Accès réservé exclusivement aux administrateurs (ADMIN)."""
    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            getattr(request.user, 'role', None) == 'ADMIN'
        )


class ReadingAccessPermission(BasePermission):
    """
    Mesures de capteurs (Module 3).
    ADMIN     : toutes les opérations (CRUD + import).
    TECHNICIEN: lecture + ingestion/import (POST, PUT, PATCH).
    OPERATEUR : lecture seule (GET, HEAD, OPTIONS).
    """
    TECHNICIEN_METHODS = (*SAFE_METHODS, 'POST', 'PUT', 'PATCH')

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        role = getattr(request.user, 'role', None)
        if role == 'ADMIN':
            return True
        if role == 'TECHNICIEN':
            return request.method in self.TECHNICIEN_METHODS
        if role == 'OPERATEUR':
            return request.method in SAFE_METHODS
        return False


class InspectionAccessPermission(BasePermission):
    """
    Inspections visuelles par IA (Module 4).
    ADMIN     : toutes les opérations (création, analyse, suppression).
    TECHNICIEN: lecture + création + analyse (POST), pas de suppression.
    OPERATEUR : lecture seule (GET, HEAD, OPTIONS).

    L'action POST `analyze` étant une méthode POST, elle est couverte pour
    ADMIN et TECHNICIEN ; la suppression (DELETE) reste réservée à ADMIN.
    """
    TECHNICIEN_METHODS = (*SAFE_METHODS, 'POST')

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        role = getattr(request.user, 'role', None)
        if role == 'ADMIN':
            return True
        if role == 'TECHNICIEN':
            return request.method in self.TECHNICIEN_METHODS
        if role == 'OPERATEUR':
            return request.method in SAFE_METHODS
        return False

