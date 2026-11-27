from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.equipements.permissions import accessible_machine_ids


def scope_queryset_alerte(queryset, user):
    
    if getattr(user, 'role', None) == 'ADMIN':
        return queryset
    return queryset.filter(machine_id__in=list(accessible_machine_ids(user)))


class AlerteAccessPermission(BasePermission):
   
    message = "Votre rôle ne vous permet pas cette action sur les alertes."

    ROLES_AUTORISES = ('ADMIN', 'TECHNICIEN')

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if getattr(request.user, 'role', None) == 'ADMIN':
            return True
        if getattr(request.user, 'role', None) == 'TECHNICIEN':
            # Les actions métier du module (acquitter / résoudre / préparer un
            # OT) sont des POST ; la création et la suppression HTTP d'une
            # alerte n'existent pas (elle est générée, jamais supprimée).
            return request.method in (*SAFE_METHODS, 'POST')
        if getattr(request.user, 'role', None) == 'OPERATEUR':
            if getattr(view, 'action', None) == 'acquitter':
                return request.method == 'POST'
            return request.method in SAFE_METHODS
        return False


class NotificationAccessPermission(BasePermission):
    
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)


def notifications_queryset(queryset, user):
    
    return queryset.filter(utilisateur=user)
