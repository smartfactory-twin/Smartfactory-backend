"""Module 8 — API Alertes & Notifications (UC-26 → UC-29).

Endpoints exposés :

    GET    /api/alertes/                      liste filtrable / triable / paginée
    GET    /api/alertes/statistiques/         compteurs par niveau / statut
    GET    /api/alertes/compteur/             alertes actives + critiques (badge)
    GET    /api/alertes/{id}/                 détail
    POST   /api/alertes/{id}/acquitter/       acquittement (commentaire obligatoire)
    POST   /api/alertes/{id}/resoudre/        résolution manuelle
    POST   /api/alertes/{id}/preparer-ot/     pré-remplissage d'un OT (Module 9)

    GET    /api/notifications/                mes notifications
    POST   /api/notifications/tout-lire/      tout marquer comme lu
    GET    /api/notifications/compteur/       nombre de notifications non lues
    POST   /api/notifications/{id}/lire/      marquer une notification comme lue

    GET    /api/canaux-notification/mien/     mes canaux (UC-28)
    PATCH  /api/canaux-notification/mien/     activer / désactiver un canal

Toutes les lectures sont filtrées côté backend par le périmètre `UserScope`.
"""
from django.db.models import Case, Count, IntegerField, Value, When
from django.utils import timezone
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend

from .models import Alerte, Notification, PreferenceNotification
from .permissions import (
    AlerteAccessPermission,
    NotificationAccessPermission,
    notifications_queryset,
    scope_queryset_alerte,
)
from .serializers import (
    AcquittementSerializer,
    AlerteDetailSerializer,
    AlerteListSerializer,
    NotificationSerializer,
    PreferenceNotificationSerializer,
    ResolutionSerializer,
)

# Gravité décroissante : sert au tri par niveau (CRITIQUE d'abord).
GRAVITE_NIVEAU = {
    Alerte.Niveau.CRITIQUE: 0,
    Alerte.Niveau.MAJEURE: 1,
    Alerte.Niveau.MINEURE: 2,
    Alerte.Niveau.INFORMATION: 3,
}


class AlerteOrderingFilter(filters.OrderingFilter):
    """Tri par niveau selon la **gravité**, et non selon l'ordre alphabétique."""

    ordering_fields = ['date_declenchement', 'niveau', 'statut', 'valeur', 'machine__nom']
    ordering = ['-date_declenchement']

    def filter_queryset(self, request, queryset, view):
        params = request.query_params.get(self.ordering_param)
        if not params or 'niveau' not in [p.lstrip('-') for p in params.split(',')]:
            return super().filter_queryset(request, queryset, view)

        queryset = queryset.annotate(
            gravite=Case(
                *[When(niveau=niveau, then=Value(rang))
                  for niveau, rang in GRAVITE_NIVEAU.items()],
                default=Value(99),
                output_field=IntegerField(),
            ),
        )
        autres = [p for p in params.split(',') if p.lstrip('-') != 'niveau']
        tri_niveau = 'gravite' if params.split(',')[0].lstrip('-') == 'niveau' else '-gravite'
        return queryset.order_by(*(autres + [tri_niveau]))


class AlerteViewSet(viewsets.ReadOnlyModelViewSet):
    """Consultation et traitement des alertes.

    Une alerte n'est ni créée ni supprimée par l'API : elle naît de
    l'ingestion d'une mesure (UC-26) et son historique est conservé.
    """

    queryset = Alerte.objects.select_related(
        'machine', 'capteur', 'lecture', 'acquittee_par',
    ).all()
    permission_classes = [AlerteAccessPermission]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, AlerteOrderingFilter]
    filterset_fields = {
        'niveau': ['exact'],
        'statut': ['exact'],
        'type_alerte': ['exact'],
        'machine': ['exact'],
        'capteur': ['exact'],
        'date_declenchement': ['gte', 'lte', 'date'],
    }
    search_fields = ['reference', 'message', 'machine__nom', 'machine__identifiant_interne',
                     'capteur__identifiant', 'capteur__nom']

    def get_queryset(self):
        """Filtrage par périmètre `UserScope` — la source de vérité reste le backend."""
        return scope_queryset_alerte(super().get_queryset(), self.request.user)

    def get_serializer_class(self):
        return AlerteDetailSerializer if self.action == 'retrieve' else AlerteListSerializer

    # ── Acquittement (UC-29) ──────────────────────────────────────────────
    @action(detail=True, methods=['post'], url_path='acquitter')
    def acquitter(self, request, pk=None):
        """Acquitte l'alerte. Un commentaire est **obligatoire** (§13)."""
        alerte = self.get_object()

        if not alerte.est_acquittable:
            return Response(
                {'detail': "Cette alerte n'est plus active : elle a déjà été traitée."},
                status=status.HTTP_409_CONFLICT,
            )

        serializer = AcquittementSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            alerte.acquitter(request.user, serializer.validated_data['commentaire'])
        except ValueError as exc:
            return Response({'commentaire': [str(exc)]}, status=status.HTTP_400_BAD_REQUEST)

        return Response(AlerteDetailSerializer(alerte).data, status=status.HTTP_200_OK)

    # ── Résolution manuelle ────────────────────────────────────────────────
    @action(detail=True, methods=['post'], url_path='resoudre')
    def resoudre(self, request, pk=None):
        """Clôture manuelle (le retour à la normale est fait par le moteur)."""
        alerte = self.get_object()
        serializer = ResolutionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if not alerte.resoudre(serializer.validated_data.get('motif') or 'Résolue manuellement.'):
            return Response(
                {'detail': 'Cette alerte est déjà résolue.'},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(AlerteDetailSerializer(alerte).data, status=status.HTTP_200_OK)

    # ── Préparation d'un ordre de travail (§14) ────────────────────────────
    @action(detail=True, methods=['post'], url_path='preparer-ot')
    def preparer_ot(self, request, pk=None):
        """Renvoie les informations pré-remplies d'un futur ordre de travail.

        Le Module 9 (CMMS) n'est pas développé : **rien n'est créé ni
        enregistré**, seul le récapitulatif repris par l'IHM est renvoyé.
        """
        alerte = self.get_object()
        return Response({
            'alerte_id': alerte.pk,
            'reference': alerte.reference,
            'machine': alerte.machine_id,
            'machine_nom': alerte.machine.nom,
            'machine_identifiant': alerte.machine.identifiant_interne,
            'capteur': alerte.capteur_id,
            'capteur_identifiant': alerte.capteur.identifiant,
            'type_alerte': alerte.type_alerte,
            'type_alerte_label': alerte.get_type_alerte_display(),
            'niveau': alerte.niveau,
            'niveau_label': alerte.get_niveau_display(),
            # Priorité proposée : dérivée du niveau, sans CMMS.
            'priorite_proposee': {
                Alerte.Niveau.CRITIQUE: 'P1',
                Alerte.Niveau.MAJEURE: 'P2',
                Alerte.Niveau.MINEURE: 'P3',
            }.get(alerte.niveau, 'P3'),
            'valeur': alerte.valeur,
            'seuil': alerte.seuil,
            'unite': alerte.unite,
            'depassement': alerte.depassement,
            'date_declenchement': alerte.date_declenchement,
            'description': (
                f'{alerte.message} Mesure {alerte.valeur} {alerte.unite} pour un seuil '
                f'de {alerte.seuil} {alerte.unite} '
                f'(dépassement de {alerte.depassement:.2f}).'
            ),
            'module_9_disponible': False,
            'message': (
                "Le Module 9 (CMMS) n'est pas encore développé : ces informations "
                "seront reprises à l'identique lors de sa livraison."
            ),
        }, status=status.HTTP_200_OK)

    # ── Compteurs (badge / tableau de bord) ────────────────────────────────
    @action(detail=False, methods=['get'], url_path='statistiques')
    def statistiques(self, request):
        """Compteurs par niveau et par statut, périmètre `UserScope` inclus."""
        queryset = self.filter_queryset(self.get_queryset())
        actives = queryset.filter(statut=Alerte.Statut.ACTIVE)

        return Response({
            'total': queryset.count(),
            'actives': actives.count(),
            'acquittees': queryset.filter(statut=Alerte.Statut.ACKNOWLEDGED).count(),
            'resolues': queryset.filter(statut=Alerte.Statut.RESOLVED).count(),
            'critiques': actives.filter(niveau=Alerte.Niveau.CRITIQUE).count(),
            'par_statut': {
                row['statut']: row['total']
                for row in queryset.values('statut').annotate(total=Count('id'))
            },
            'par_niveau': {
                row['niveau']: row['total']
                for row in queryset.values('niveau').annotate(total=Count('id'))
            },
            'periode': {
                'depuis': request.query_params.get('date_declenchement__gte'),
                'jusqu_a': request.query_params.get('date_declenchement__lte'),
            },
        })


class AlerteCompteurView(APIView):
    """Compteur léger d'alertes actives (badge de navigation)."""

    permission_classes = [AlerteAccessPermission]

    def get(self, request):
        actives = scope_queryset_alerte(Alerte.objects.all(), request.user).filter(
            statut=Alerte.Statut.ACTIVE,
        )
        return Response({
            'actives': actives.count(),
            'critiques': actives.filter(niveau=Alerte.Niveau.CRITIQUE).count(),
        })


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    """Notifications In-App de l'utilisateur connecté (UC-28)."""

    queryset = Notification.objects.select_related('alerte', 'alerte__machine').all()
    serializer_class = NotificationSerializer
    permission_classes = [NotificationAccessPermission]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['lue', 'niveau', 'type', 'alerte']
    search_fields = ['titre', 'message', 'alerte__reference']
    ordering_fields = ['date_creation', 'niveau']
    ordering = ['-date_creation']

    def get_queryset(self):
        return notifications_queryset(super().get_queryset(), self.request.user)

    @action(detail=True, methods=['post'], url_path='lire')
    def lire(self, request, pk=None):
        """Marque une notification comme lue (idempotent)."""
        notification = self.get_object()
        notification.marquer_lue()
        return Response(NotificationSerializer(notification).data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='tout-lire')
    def tout_lire(self, request):
        """Marque toutes les notifications de l'utilisateur comme lues."""
        non_lues = self.get_queryset().filter(lue=False)
        total = non_lues.count()
        non_lues.update(lue=True, date_lecture=timezone.now())
        return Response({'mises_a_jour': total}, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='compteur')
    def compteur(self, request):
        """Nombre de notifications non lues (badge de la cloche)."""
        return Response({'non_lues': self.get_queryset().filter(lue=False).count()})


class MonCanauxNotificationView(APIView):
    """UC-28 — canaux de notification de l'utilisateur connecté."""

    permission_classes = [IsAuthenticated]

    def _preference(self, user):
        preference, _ = PreferenceNotification.objects.get_or_create(utilisateur=user)
        return preference

    def get(self, request):
        return Response(
            PreferenceNotificationSerializer(self._preference(request.user)).data,
            status=status.HTTP_200_OK,
        )

    def patch(self, request):
        preference = self._preference(request.user)
        serializer = PreferenceNotificationSerializer(
            preference, data=request.data, partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        preference.refresh_from_db()
        return Response(
            PreferenceNotificationSerializer(preference).data,
            status=status.HTTP_200_OK,
        )
