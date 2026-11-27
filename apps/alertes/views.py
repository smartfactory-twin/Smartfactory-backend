from datetime import datetime, timedelta

from django.db.models import Case, Count, IntegerField, Q, Value, When
from django.db.models.functions import TruncDate
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
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


class AlertesParMachineView(APIView):
    permission_classes = [AlerteAccessPermission]

    def get(self, request):
        allowed = {'date_debut', 'date_fin', 'limit'}
        if set(request.query_params) - allowed:
            raise ValidationError({'detail': 'Paramètre de requête non autorisé.'})
        try:
            start = datetime.fromisoformat(request.query_params['date_debut'].replace('Z', '+00:00'))
            end = datetime.fromisoformat(request.query_params['date_fin'].replace('Z', '+00:00'))
            limit = int(request.query_params.get('limit', 20))
        except (KeyError, TypeError, ValueError):
            raise ValidationError({'detail': 'date_debut et date_fin ISO-8601 ainsi qu’un limit entier sont requis.'})
        if timezone.is_naive(start) or timezone.is_naive(end) or start >= end:
            raise ValidationError({'detail': 'La période doit être horodatée avec fuseau et date_debut < date_fin.'})
        if end - start > timedelta(days=366):
            raise ValidationError({'detail': 'La période ne peut pas dépasser 366 jours.'})
        if not 1 <= limit <= 100:
            raise ValidationError({'limit': 'La limite doit être comprise entre 1 et 100.'})

        rows = scope_queryset_alerte(Alerte.objects.all(), request.user).filter(
            date_declenchement__gte=start, date_declenchement__lt=end,
        ).values(
            'machine_id', 'machine__nom', 'machine__identifiant_interne',
        ).annotate(total=Count('id')).order_by('-total', 'machine__nom', 'machine_id')
        total_groups = rows.count()
        results = list(rows[:limit])
        return Response({
            'results': [{
                'machine_id': row['machine_id'],
                'machine': row['machine__nom'],
                'identifiant_interne': row['machine__identifiant_interne'],
                'alert_count': row['total'],
            } for row in results],
            'count': total_groups,
            'truncated': total_groups > limit,
            'period': {'date_debut': start, 'date_fin': end},
        })


class AlerteViewSet(viewsets.ReadOnlyModelViewSet):
    
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
      
        return scope_queryset_alerte(super().get_queryset(), self.request.user)

    def get_serializer_class(self):
        return AlerteDetailSerializer if self.action == 'retrieve' else AlerteListSerializer

    @action(detail=False, methods=['get'], url_path='tableau-de-bord')
    def tableau_de_bord(self, request):
        base = scope_queryset_alerte(Alerte.objects.all(), request.user)
        active = Q(statut=Alerte.Statut.ACTIVE)
        totals = base.aggregate(
            actives=Count('id', filter=active),
            machines_en_alerte=Count('machine_id', filter=active, distinct=True),
            critiques=Count('id', filter=active & Q(niveau=Alerte.Niveau.CRITIQUE)),
        )
        par_niveau = {
            row['niveau']: row['total']
            for row in base.values('niveau').annotate(total=Count('id'))
        }

        start_raw = request.query_params.get('date_declenchement__gte')
        end_raw = request.query_params.get('date_declenchement__lte')
        par_jour = []
        if bool(start_raw) != bool(end_raw):
            raise ValidationError('Les deux bornes de période sont requises.')
        if start_raw and end_raw:
            start = parse_datetime(start_raw)
            end = parse_datetime(end_raw)
            if start is None or end is None:
                raise ValidationError('La période demandée est invalide.')
            if timezone.is_naive(start):
                start = timezone.make_aware(start)
            if timezone.is_naive(end):
                end = timezone.make_aware(end)
            if start >= end:
                raise ValidationError('La période demandée est invalide.')
            if end - start > timedelta(days=8):
                raise ValidationError('La période ne peut pas dépasser 8 jours.')
            par_jour = [
                {'date': row['jour'].isoformat(), 'total': row['total']}
                for row in base.filter(
                    date_declenchement__gte=start,
                    date_declenchement__lte=end,
                ).annotate(jour=TruncDate('date_declenchement'))
                .values('jour').annotate(total=Count('id')).order_by('jour')
            ]

        return Response({**totals, 'par_niveau': par_niveau, 'par_jour': par_jour})

    #  Acquittement (UC-29) ──────────────────────────────────────────────
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

    #  Résolution manuelle 
    @action(detail=True, methods=['post'], url_path='resoudre')
    def resoudre(self, request, pk=None):
        
        alerte = self.get_object()
        serializer = ResolutionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if not alerte.resoudre(serializer.validated_data.get('motif') or 'Résolue manuellement.'):
            return Response(
                {'detail': 'Cette alerte est déjà résolue.'},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(AlerteDetailSerializer(alerte).data, status=status.HTTP_200_OK)

    #  Préparation d'un ordre de travail 
    @action(detail=True, methods=['post'], url_path='preparer-ot')
    def preparer_ot(self, request, pk=None):
        
        alerte = self.get_object()
        from apps.equipements.models import OrdreTravail
        from apps.equipements.serializers import OrdreTravailSerializer

        ordre = OrdreTravail.objects.filter(from_alert=alerte.pk).first()
        if ordre is None:
            priorite = {
                Alerte.Niveau.CRITIQUE: OrdreTravail.Priorite.HAUTE,
                Alerte.Niveau.MAJEURE: OrdreTravail.Priorite.MOYENNE,
                Alerte.Niveau.MINEURE: OrdreTravail.Priorite.BASSE,
            }.get(alerte.niveau, OrdreTravail.Priorite.MOYENNE)
            ordre = OrdreTravail.objects.create(
                machine=alerte.machine,
                type_ordre=OrdreTravail.Type.CORRECTIVE,
                priorite=priorite,
                titre=f'{alerte.reference} — {alerte.machine.nom}: {alerte.message}',
                from_alert=alerte.pk,
                cree_par=request.user,
            )
            ordre.historique = [{
                'statut': ordre.statut,
                'date': ordre.created_at.isoformat(),
                'source': f'alerte {alerte.reference}',
            }]
            ordre.save(update_fields=['historique', 'updated_at'])
        return Response({
            'ordre': OrdreTravailSerializer(ordre).data,
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
            'module_9_disponible': True,
            'message': f'Ordre de travail OT-{ordre.pk} créé ou déjà associé à cette alerte.',
        }, status=status.HTTP_200_OK)

    #  Compteurs (badge / tableau de bord) 
    @action(detail=False, methods=['get'], url_path='statistiques')
    def statistiques(self, request):
        """Compteurs par niveau et par statut, périmètre `UserScope` inclus."""
        queryset = self.filter_queryset(self.get_queryset())
        actives = queryset.filter(statut=Alerte.Statut.ACTIVE)

        return Response({
            'total': queryset.count(),
            'actives': actives.count(),
            # Compteur UC-11 : machines distinctes portant au moins une alerte active.
            'machines_en_alerte': actives.values('machine_id').distinct().count(),
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
       
        notification = self.get_object()
        notification.marquer_lue()
        return Response(NotificationSerializer(notification).data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='tout-lire')
    def tout_lire(self, request):
        
        non_lues = self.get_queryset().filter(lue=False)
        total = non_lues.count()
        non_lues.update(lue=True, date_lecture=timezone.now())
        return Response({'mises_a_jour': total}, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='compteur')
    def compteur(self, request):
        
        return Response({'non_lues': self.get_queryset().filter(lue=False).count()})


class MonCanauxNotificationView(APIView):
    

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
