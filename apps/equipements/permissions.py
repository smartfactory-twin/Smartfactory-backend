from django.db.models import Q
from rest_framework.permissions import BasePermission, SAFE_METHODS


#  Périmètres d'accès 

def _actives_scopes(user):
    
    from .models import UserScope
    return UserScope.objects.filter(utilisateur=user).select_related(
        'usine', 'zone', 'ligne', 'machine'
    )


def scope_machine_q(scope):
   
    if scope.usine_id:
        return Q(ligne_production__zone__usine_id=scope.usine_id)
    if scope.zone_id:
        return Q(ligne_production__zone_id=scope.zone_id)
    if scope.ligne_id:
        return Q(ligne_production_id=scope.ligne_id)
    if scope.machine_id:
        return Q(pk=scope.machine_id)
    return Q(pk__in=[])


def accessible_machine_ids(user):
   
    from .models import Machine

    role = getattr(user, 'role', None)
    if role == 'ADMIN':
        return Machine.objects.values_list('id', flat=True)

    if not (user and user.is_authenticated):
        return Machine.objects.none().values_list('id', flat=True)

    q = Q(pk__in=[])

    for scope in _actives_scopes(user):
        if not scope.est_active():
            continue
        q |= scope_machine_q(scope)

    # `q` reste `Q(pk__in=[])` si aucune affectation n'est active : aucun accès.
    return Machine.objects.filter(q).values_list('id', flat=True)


def scope_queryset_machine(queryset, user):
    
    if getattr(user, 'role', None) == 'ADMIN':
        return queryset
    return queryset.filter(pk__in=list(accessible_machine_ids(user)))


def scope_queryset_sensor(queryset, user):
    
    if getattr(user, 'role', None) == 'ADMIN':
        return queryset
    return queryset.filter(machine_id__in=list(accessible_machine_ids(user)))


def scope_queryset_reading(queryset, user):
    
    if getattr(user, 'role', None) == 'ADMIN':
        return queryset
    return queryset.filter(sensor__machine_id__in=list(accessible_machine_ids(user)))


def scope_queryset_inspection(queryset, user):
    
    if getattr(user, 'role', None) == 'ADMIN':
        return queryset
    return queryset.filter(machine_id__in=list(accessible_machine_ids(user)))


def scope_queryset_machine_child(queryset, user):
    
    if getattr(user, 'role', None) == 'ADMIN':
        return queryset
    return queryset.filter(machine_id__in=list(accessible_machine_ids(user)))


class ScopedMachineAccess(BasePermission):
    
    message = "Vous n'avez pas accès à cette machine (hors périmètre d'affectation)."

    def has_object_permission(self, request, view, obj):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if getattr(user, 'role', None) == 'ADMIN':
            return True
        machine_id = resolve_machine_id(obj)
        if machine_id is None:
            return False
        return machine_id in set(accessible_machine_ids(user))


def resolve_machine_id(obj):
   
    model_name = obj.__class__.__name__
    if model_name == 'Machine':
        return obj.pk
    if model_name == 'Reading':
        return getattr(getattr(obj, 'sensor', None), 'machine_id', None)
    # Sensor, InspectionVisuelle, Composant, Document, ...
    return getattr(obj, 'machine_id', None)


class IsAdminOrReadOnly(BasePermission):
    
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in SAFE_METHODS:
            return True
        return request.user.role == 'ADMIN'


class MachineAccessPermission(BasePermission):
    
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
    
    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            getattr(request.user, 'role', None) == 'ADMIN'
        )


class WorkOrderRolePermission(BasePermission):
    
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in SAFE_METHODS:
            return True
        return getattr(request.user, 'role', None) in ('ADMIN', 'TECHNICIEN')

    def has_object_permission(self, request, view, obj):
        return self.has_permission(request, view)


class ReadingAccessPermission(BasePermission):
    
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
    
    TECHNICIEN_METHODS = (*SAFE_METHODS, 'POST', 'DELETE')

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

