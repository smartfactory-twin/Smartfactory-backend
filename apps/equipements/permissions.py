from django.db.models import Q
from rest_framework.permissions import BasePermission, SAFE_METHODS


# ── Périmètres d'accès (UserScope) ─────────────────────────────────────────────

def _actives_scopes(user):
    """Affectations actives d'un utilisateur, en eager-loadant les cibles."""
    from .models import UserScope
    return UserScope.objects.filter(utilisateur=user).select_related(
        'usine', 'zone', 'ligne', 'machine'
    )


def scope_machine_q(scope):
    """`Q` couvrant les machines ouvertes par UNE affectation.

    Une affectation `usine` / `zone` ouvre tout le sous-arbre descendant ;
    une affectation `ligne` ouvre les machines de la ligne ; une affectation
    `machine` ouvre cette machine seule.
    """
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
    """IDs des machines accessibles par `user` selon ses affectations.

    * `ADMIN` : accès global (toutes les machines).
    * `OPERATEUR` : union des machines couvertes par ses affectations actives.
      Une affectation portant sur une Usine / Zone / Ligne ouvre tout le
      sous-arbre descendant ; une affectation sur une Machine ouvre cette
      machine seule.
    * `TECHNICIEN` : même règle, mais il peut cumuler plusieurs périmètres
      (une affectation par atelier / ligne / machine).

    **Aucune affectation active → aucun accès**, pour tout rôle non ADMIN
    (fail-closed). Seuls les administrateurs ont un accès global.
    L'accès transversal historique du technicien sans affectation a été
    supprimé : l'UI et l'API doivent rester cohérentes.

    Les affectations expirées (`actif=False`, `date_fin` dépassée) sont ignorées.
    """
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
    """Restreint un queryset de Machine au périmètre de `user`."""
    if getattr(user, 'role', None) == 'ADMIN':
        return queryset
    return queryset.filter(pk__in=list(accessible_machine_ids(user)))


def scope_queryset_sensor(queryset, user):
    """Restreint un queryset de Sensor au périmètre de `user`."""
    if getattr(user, 'role', None) == 'ADMIN':
        return queryset
    return queryset.filter(machine_id__in=list(accessible_machine_ids(user)))


def scope_queryset_reading(queryset, user):
    """Restreint un queryset de Reading au périmètre de `user`."""
    if getattr(user, 'role', None) == 'ADMIN':
        return queryset
    return queryset.filter(sensor__machine_id__in=list(accessible_machine_ids(user)))


def scope_queryset_inspection(queryset, user):
    """Restreint un queryset d'InspectionVisuelle au périmètre de `user`."""
    if getattr(user, 'role', None) == 'ADMIN':
        return queryset
    return queryset.filter(machine_id__in=list(accessible_machine_ids(user)))


def scope_queryset_machine_child(queryset, user):
    """Restreint un queryset dont l'objet appartient à une machine.

    Utilisé pour `Composant` et `Document` (FK `machine` directe), afin
    qu'un opérateur ne puisse pas lire la fiche technique d'une machine
    hors de son périmètre.
    """
    if getattr(user, 'role', None) == 'ADMIN':
        return queryset
    return queryset.filter(machine_id__in=list(accessible_machine_ids(user)))


class ScopedMachineAccess(BasePermission):
    """Garde objet : refuse l'accès à une machine hors périmètre.

    Complète le filtrage de queryset pour les actions `detail` (retrieve,
    update, delete, actions) : sans cela, `GET /machines/{id}/` resterait
    accessible pour une machine non autorisée.
    """

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
    """Machine concernée par un objet, quel que soit le modèle.

    Gère Machine, Sensor, Reading, InspectionVisuelle, Composant, Document.
    """
    model_name = obj.__class__.__name__
    if model_name == 'Machine':
        return obj.pk
    if model_name == 'Reading':
        return getattr(getattr(obj, 'sensor', None), 'machine_id', None)
    # Sensor, InspectionVisuelle, Composant, Document, ...
    return getattr(obj, 'machine_id', None)


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

