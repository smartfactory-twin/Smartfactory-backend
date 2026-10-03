import csv
import io
from django.utils.dateparse import parse_date
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend

from .models import Usine, Zone, LigneProduction, Machine, Document, Composant
from .permissions import IsAdminOrReadOnly, MachineAccessPermission
from .serializers import (
    UsineSerializer, ZoneSerializer, LigneProductionSerializer,
    ComposantSerializer, DocumentSerializer,
    MachineListSerializer, MachineDetailSerializer, MachineCreateUpdateSerializer,
)


class UsineViewSet(viewsets.ModelViewSet):
    queryset = Usine.objects.all()
    serializer_class = UsineSerializer
    permission_classes = [IsAdminOrReadOnly]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ['nom', 'adresse']


class ZoneViewSet(viewsets.ModelViewSet):
    queryset = Zone.objects.select_related('usine').all()
    serializer_class = ZoneSerializer
    permission_classes = [IsAdminOrReadOnly]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['usine']
    search_fields = ['nom']


class LigneProductionViewSet(viewsets.ModelViewSet):
    queryset = LigneProduction.objects.select_related('zone', 'zone__usine').all()
    serializer_class = LigneProductionSerializer
    permission_classes = [IsAdminOrReadOnly]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['zone', 'zone__usine']
    search_fields = ['nom']


class MachineViewSet(viewsets.ModelViewSet):
    queryset = Machine.objects.select_related(
        'ligne_production', 'ligne_production__zone', 'ligne_production__zone__usine'
    ).prefetch_related('composants', 'documents').all()
    permission_classes = [MachineAccessPermission]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['statut', 'ligne_production__zone', 'ligne_production__zone__usine']
    search_fields = ['nom', 'identifiant_interne', 'numero_serie']
    ordering_fields = ['nom', 'created_at', 'statut']

    def get_serializer_class(self):
        if self.action == 'list':
            return MachineListSerializer
        if self.action in ('create', 'update', 'partial_update'):
            return MachineCreateUpdateSerializer
        return MachineDetailSerializer

    @action(detail=False, methods=['post'], url_path='import_csv')
    def import_csv(self, request):
        file = request.FILES.get('file')
        if not file:
            return Response({'detail': 'No file provided.'}, status=status.HTTP_400_BAD_REQUEST)

        decoded = file.read().decode('utf-8-sig')
        reader = csv.DictReader(io.StringIO(decoded))
        created_count = 0
        errors = []
        valid_statuts = [s[0] for s in Machine.Statut.choices]

        for i, row in enumerate(reader, start=2):
            try:
                identifiant = row.get('identifiant_interne', '').strip()
                if not identifiant:
                    errors.append({'row': i, 'error': 'identifiant_interne manquant'})
                    continue
                if Machine.objects.filter(identifiant_interne=identifiant).exists():
                    errors.append({'row': i, 'error': f'identifiant_interne "{identifiant}" déjà utilisé'})
                    continue

                statut = row.get('statut', 'NORMAL').strip().upper()
                if statut not in valid_statuts:
                    errors.append({'row': i, 'error': f'statut "{statut}" invalide. Valeurs: {valid_statuts}'})
                    continue

                date_installation = None
                raw_date = row.get('date_installation', '').strip()
                if raw_date:
                    date_installation = parse_date(raw_date)
                    if date_installation is None:
                        errors.append({'row': i, 'error': f'date_installation "{raw_date}" invalide (format YYYY-MM-DD attendu)'})
                        continue

                ligne_production = None
                raw_ligne = row.get('ligne_production_id', '').strip()
                if raw_ligne:
                    try:
                        ligne_production = LigneProduction.objects.get(pk=int(raw_ligne))
                    except (LigneProduction.DoesNotExist, ValueError):
                        errors.append({'row': i, 'error': f'ligne_production_id "{raw_ligne}" introuvable'})
                        continue

                Machine.objects.create(
                    nom=row.get('nom', '').strip(),
                    identifiant_interne=identifiant,
                    numero_serie=row.get('numero_serie', '').strip(),
                    marque=row.get('marque', '').strip(),
                    modele=row.get('modele', '').strip(),
                    date_installation=date_installation,
                    statut=statut,
                    ligne_production=ligne_production,
                )
                created_count += 1
            except Exception as e:
                errors.append({'row': i, 'error': str(e)})

        return Response({'created': created_count, 'errors': errors}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='upload_document')
    def upload_document(self, request, pk=None):
        machine = self.get_object()
        nom = request.data.get('nom', 'Document')
        type_document = request.data.get('type_document', 'AUTRE')
        fichier = request.FILES.get('fichier')
        if not fichier:
            return Response({'detail': 'No file provided.'}, status=status.HTTP_400_BAD_REQUEST)
        doc = Document.objects.create(
            machine=machine,
            nom=nom,
            type_document=type_document,
            fichier=fichier,
        )
        return Response(DocumentSerializer(doc, context={'request': request}).data, status=status.HTTP_201_CREATED)


class ComposantViewSet(viewsets.ModelViewSet):
    queryset = Composant.objects.select_related('machine').all()
    serializer_class = ComposantSerializer
    permission_classes = [IsAdminOrReadOnly]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['machine']


class DocumentViewSet(viewsets.ModelViewSet):
    queryset = Document.objects.select_related('machine').all()
    serializer_class = DocumentSerializer
    permission_classes = [IsAdminOrReadOnly]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['machine']
