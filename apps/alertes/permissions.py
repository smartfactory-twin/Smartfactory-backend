"""Module 8 — Permissions et filtrage par périmètre `UserScope`.

Le filtrage n'est **que** du filtrage de queryset : il s'appuie sur
`equipements.permissions.accessible_machine_ids()`, c'est-à-dire sur le
`UserScope`, source de vérité unique. Aucune seconde règle d'accès n'est
introduite ici.

Le frontend filtre également l'affichage, mais la sécurité réelle est ici :
une alerte hors périmètre renvoie 404 sur `/alertes/{id}/` (le queryset est
filtré) et n'apparaît jamais dans `/alertes/`.
"""
from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.equipements.permissions import accessible_machine_ids


def scope_queryset_alerte(queryset, user):
    """Restreint un queryset d'`Alerte` au périmètre de `user`."""
    if getattr(user, 'role', None) == 'ADMIN':
        return queryset
    return queryset.filter(machine_id__in=list(accessible_machine_ids(user)))


class AlerteAccessPermission(BasePermission):
    """Alertes (UC-29).

    ADMIN     : lecture + acquittement + résolution + préparation d'OT.
    TECHNICIEN: lecture + acquittement + résolution + préparation d'OT.
    OPERATEUR : **lecture seule** (consultation), aucune écriture.

    Les seuils des capteurs — les « règles d'alerte » au sens de l'UC-26 —
    ne sont pas modifiables ici : ils restent gérés par `SensorViewSet`
    (ADMIN en écriture, cf. `MachineAccessPermission`).
    """

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
            return request.method in SAFE_METHODS
        return False


class NotificationAccessPermission(BasePermission):
    """Les notifications sont strictement personnelles (In-App)."""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)


def notifications_queryset(queryset, user):
    """Un utilisateur ne voit que ses propres notifications."""
    return queryset.filter(utilisateur=user)
