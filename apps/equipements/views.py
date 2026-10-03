import csv
import io
from django.utils.dateparse import parse_date
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend

from .models import Usine, Zone, LigneProduction, Machine, Document, Composant, Sensor, Reading, InspectionVisuelle
from .permissions import (
    IsAdminOrReadOnly, MachineAccessPermission, IsAdminRole, ReadingAccessPermission,
    InspectionAccessPermission,
)
from .serializers import (
    UsineSerializer, UsineHierarchieSerializer,
    ZoneSerializer, LigneProductionSerializer,
    ComposantSerializer, DocumentSerializer,
    MachineListSerializer, MachineDetailSerializer, MachineCreateUpdateSerializer,
    SensorSerializer, SensorListSerializer, SensorDetailSerializer, ReadingSerializer,
    InspectionVisuelleSerializer, InspectionCreateSerializer,
)
from .csv_hierarchy import (
    validate_and_parse_hierarchy_csv,
    execute_hierarchy_import,
    export_hierarchy_csv,
)
from .readings_io import (
    import_readings_from_csv,
    import_readings_from_json,
    apply_preprocessing,
    preprocess_readings,
)
from .sensors_io import import_sensors_from_csv
from .vision_ai import get_vision_service


class UsineViewSet(viewsets.ModelViewSet):
    queryset = Usine.objects.all()
    serializer_class = UsineSerializer
    permission_classes = [IsAdminOrReadOnly]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ['nom', 'adresse']
    ordering_fields = ['nom', 'created_at']

    @action(detail=True, methods=['get'], url_path='hierarchie',
            permission_classes=[IsAuthenticated])
    def hierarchie(self, request, pk=None):
        """Retourne l'arbre complet : usine → zones → lignes → machines → composants."""
        usine = self.get_object()
        serializer = UsineHierarchieSerializer(usine)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='export_csv',
            permission_classes=[IsAdminRole])
    def export_csv(self, request):
        """Export complet de la hiérarchie Usine → Zone → Ligne → Machine → Composant en CSV."""
        return export_hierarchy_csv()

    @action(detail=False, methods=['post'], url_path='preview_csv',
            permission_classes=[IsAdminRole])
    def preview_csv(self, request):
        """Prévisualisation et validation du fichier CSV de hiérarchie avant import."""
        file = request.FILES.get('file')
        if not file:
            return Response({'detail': 'Aucun fichier fourni.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            result = validate_and_parse_hierarchy_csv(file)
            return Response(result, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'detail': f'Erreur de lecture du fichier CSV: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'], url_path='import_csv',
            permission_classes=[IsAdminRole])
    def import_csv(self, request):
        """Importation effective des données validées du CSV de hiérarchie."""
        file = request.FILES.get('file')
        if not file:
            return Response({'detail': 'Aucun fichier fourni.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            result = validate_and_parse_hierarchy_csv(file)
            if not result['valid_rows']:
                return Response({
                    'detail': 'Aucune ligne valide à importer.',
                    'errors': result['errors'],
                    'summary': result['summary']
                }, status=status.HTTP_400_BAD_REQUEST)

            stats = execute_hierarchy_import(result['valid_rows'])
            return Response({
                'message': 'Importation réussie',
                'summary': result['summary'],
                'stats': stats,
                'errors': result['errors'],
                'valid_count': result['valid_rows_count'],
                'invalid_count': result['invalid_rows_count'],
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'detail': f'Erreur lors de l’importation: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)


class ZoneViewSet(viewsets.ModelViewSet):
    queryset = Zone.objects.select_related('usine').all()
    serializer_class = ZoneSerializer
    permission_classes = [IsAdminOrReadOnly]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['usine']
    search_fields = ['nom']
    ordering_fields = ['nom']


class LigneProductionViewSet(viewsets.ModelViewSet):
    queryset = LigneProduction.objects.select_related('zone', 'zone__usine').all()
    serializer_class = LigneProductionSerializer
    permission_classes = [IsAdminOrReadOnly]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['zone', 'zone__usine']
    search_fields = ['nom']
    ordering_fields = ['nom']


class MachineViewSet(viewsets.ModelViewSet):
    queryset = Machine.objects.select_related(
        'ligne_production',
        'ligne_production__zone',
        'ligne_production__zone__usine'
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

    # ── Composants inline ─────────────────────────────────────────────────────

    @action(detail=True, methods=['get'], url_path='composants',
            permission_classes=[IsAuthenticated])
    def list_composants(self, request, pk=None):
        """GET /api/equipements/machines/{id}/composants/"""
        machine = self.get_object()
        qs = machine.composants.all()
        serializer = ComposantSerializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='composants/add',
            permission_classes=[IsAdminOrReadOnly])
    def add_composant(self, request, pk=None):
        """POST /api/equipements/machines/{id}/composants/add/"""
        machine = self.get_object()
        data = request.data.copy()
        data['machine'] = machine.id
        serializer = ComposantSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    # ── Import CSV ────────────────────────────────────────────────────────────

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
                nom = row.get('nom', '').strip()
                if not nom:
                    errors.append({'row': i, 'field': 'nom', 'message': 'nom est requis'})
                    continue

                identifiant = row.get('identifiant_interne', '').strip()
                if not identifiant:
                    errors.append({'row': i, 'field': 'identifiant_interne', 'message': 'identifiant_interne est requis'})
                    continue
                if Machine.objects.filter(identifiant_interne=identifiant).exists():
                    errors.append({'row': i, 'field': 'identifiant_interne',
                                   'message': f'identifiant_interne "{identifiant}" déjà utilisé'})
                    continue

                statut = row.get('statut', 'NORMAL').strip().upper()
                if statut not in valid_statuts:
                    errors.append({'row': i, 'field': 'statut',
                                   'message': f'statut "{statut}" invalide. Valeurs acceptées: {valid_statuts}'})
                    continue

                date_installation = None
                raw_date = row.get('date_installation', '').strip()
                if raw_date:
                    date_installation = parse_date(raw_date)
                    if date_installation is None:
                        errors.append({'row': i, 'field': 'date_installation',
                                       'message': f'"{raw_date}" invalide, format attendu: YYYY-MM-DD'})
                        continue

                ligne_production = None
                raw_ligne = row.get('ligne_production_id', '').strip()
                if raw_ligne:
                    try:
                        ligne_production = LigneProduction.objects.get(pk=int(raw_ligne))
                    except (LigneProduction.DoesNotExist, ValueError):
                        errors.append({'row': i, 'field': 'ligne_production_id',
                                       'message': f'ligne_production_id "{raw_ligne}" introuvable'})
                        continue

                Machine.objects.create(
                    nom=nom,
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
                errors.append({'row': i, 'field': '__all__', 'message': str(e)})

        return Response({'created': created_count, 'errors': errors}, status=status.HTTP_200_OK)

    # ── Upload document ───────────────────────────────────────────────────────

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
        return Response(DocumentSerializer(doc).data, status=status.HTTP_201_CREATED)


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


# ── Capteurs ────────────────────────────────────────────────────────────────────

class SensorViewSet(viewsets.ModelViewSet):
    queryset = Sensor.objects.select_related('machine', 'machine__ligne_production',
                                             'machine__ligne_production__zone',
                                             'machine__ligne_production__zone__usine').all()
    permission_classes = [MachineAccessPermission]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['machine', 'type_capteur', 'actif']
    search_fields = ['identifiant', 'nom', 'machine__nom', 'machine__identifiant_interne']
    ordering_fields = ['nom', 'identifiant', 'created_at']

    def get_serializer_class(self):
        if self.action == 'list':
            return SensorListSerializer
        if self.action in ('create', 'update', 'partial_update', 'retrieve'):
            return SensorDetailSerializer
        return SensorSerializer

    @action(detail=False, methods=['post'], url_path='preview_csv',
            permission_classes=[IsAdminRole])
    def preview_csv(self, request):
        """UC-08 : valide un CSV de capteurs sans rien insérer.

        Colonnes attendues : sensor_id, name, machine_identifiant, type, unit,
        frequency_seconds, threshold_min, threshold_max, active, description.
        """
        file = request.FILES.get('file')
        if not file:
            return Response({'detail': 'Aucun fichier fourni.'},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            report = import_sensors_from_csv(file, dry_run=True)
        except Exception as e:
            return Response({'detail': f'Erreur de lecture du CSV : {str(e)}'},
                            status=status.HTTP_400_BAD_REQUEST)
        return Response(report, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='import_csv',
            permission_classes=[IsAdminRole])
    def import_csv(self, request):
        """UC-08 : crée des capteurs depuis un CSV (jamais de mesures)."""
        file = request.FILES.get('file')
        if not file:
            return Response({'detail': 'Aucun fichier fourni.'},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            report = import_sensors_from_csv(file)
        except Exception as e:
            return Response({'detail': f"Erreur lors de l'import CSV : {str(e)}"},
                            status=status.HTTP_400_BAD_REQUEST)
        return Response(report, status=status.HTTP_200_OK)


# ── Lectures ────────────────────────────────────────────────────────────────────

class ReadingViewSet(viewsets.ModelViewSet):
    queryset = Reading.objects.select_related('sensor', 'sensor__machine').all()
    serializer_class = ReadingSerializer
    permission_classes = [ReadingAccessPermission]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['sensor', 'sensor__machine']
    ordering_fields = ['timestamp', 'valeur']
    ordering = ['-timestamp']

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reading = serializer.save()
        # UC-10, RULE 1 : marquer comme hors plage sans supprimer la donnée.
        apply_preprocessing(reading)
        return Response(self.get_serializer(reading).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'], url_path='preview_csv',
            permission_classes=[ReadingAccessPermission])
    def preview_csv(self, request):
        """Valide un CSV de mesures sans rien insérer (prévisualisation)."""
        file = request.FILES.get('file')
        if not file:
            return Response({'detail': 'Aucun fichier fourni.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            report = import_readings_from_csv(file, dry_run=True)
        except Exception as e:
            return Response({'detail': f'Erreur de lecture du CSV : {str(e)}'},
                            status=status.HTTP_400_BAD_REQUEST)
        return Response(report, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='import_csv',
            permission_classes=[ReadingAccessPermission])
    def import_csv(self, request):
        """Importe un CSV de mesures (sensor_id, timestamp, value)."""
        file = request.FILES.get('file')
        if not file:
            return Response({'detail': 'Aucun fichier fourni.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            report = import_readings_from_csv(file)
        except Exception as e:
            return Response({'detail': f"Erreur lors de l'import CSV : {str(e)}"},
                            status=status.HTTP_400_BAD_REQUEST)
        return Response(report, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='preview_json',
            permission_classes=[ReadingAccessPermission])
    def preview_json(self, request):
        """Valide un tableau JSON de mesures sans rien insérer."""
        data = request.data
        if not isinstance(data, list):
            return Response({'detail': 'Un tableau JSON est requis.'},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            report = import_readings_from_json(data, dry_run=True)
        except Exception as e:
            return Response({'detail': f'Erreur de lecture du JSON : {str(e)}'},
                            status=status.HTTP_400_BAD_REQUEST)
        return Response(report, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='import_json',
            permission_classes=[ReadingAccessPermission])
    def import_json(self, request):
        """Importe un tableau JSON de mesures."""
        data = request.data
        if not isinstance(data, list):
            return Response({'detail': 'Un tableau JSON est requis.'},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            report = import_readings_from_json(data)
        except Exception as e:
            return Response({'detail': f"Erreur lors de l'import JSON : {str(e)}"},
                            status=status.HTTP_400_BAD_REQUEST)
        return Response(report, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='preprocess',
            permission_classes=[ReadingAccessPermission])
    def preprocess(self, request):
        """UC-10 : applique les règles de prétraitement (hors plage + interpolation).

        Body optionnel : ``{"sensor": "TEMP-001"}``. Sans capteur, toutes les
        mesures sont prétraitées.
        """
        sensor_ref = (
            request.data.get('sensor')
            or request.data.get('sensor_id')
            or request.data.get('identifiant')
        )

        sensor = None
        if sensor_ref not in (None, ''):
            sensor = Sensor.objects.filter(identifiant=str(sensor_ref)).first()
            if sensor is None:
                try:
                    sensor = Sensor.objects.filter(pk=int(sensor_ref)).first()
                except (TypeError, ValueError):
                    sensor = None
            if sensor is None:
                return Response({'detail': f'Capteur introuvable : {sensor_ref}'},
                                status=status.HTTP_404_NOT_FOUND)

        return Response(preprocess_readings(sensor), status=status.HTTP_200_OK)


# ── Module 4 — Inspections visuelles par IA ─────────────────────────────────────

class InspectionVisuelleViewSet(viewsets.ModelViewSet):
    """CRUD des inspections visuelles + action d'analyse IA.

    - POST   /api/inspections/            crée une inspection (machine + image)
    - GET    /api/inspections/            historique (filtrable/paginé)
    - GET    /api/inspections/{id}/       détail
    - POST   /api/inspections/{id}/analyze/  lance l'analyse IA
    - PATCH  /api/inspections/{id}/       met à jour les observations (ADMIN)
    - DELETE /api/inspections/{id}/       supprime (ADMIN)
    """

    queryset = InspectionVisuelle.objects.select_related(
        'machine',
        'machine__ligne_production',
        'machine__ligne_production__zone',
        'machine__ligne_production__zone__usine',
        'utilisateur',
    ).all()
    permission_classes = [InspectionAccessPermission]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['machine', 'statut_analyse', 'utilisateur']
    search_fields = ['machine__nom', 'machine__identifiant_interne']
    ordering_fields = ['date_inspection', 'score_confiance']
    ordering = ['-date_inspection']

    def get_serializer_class(self):
        if self.action == 'create':
            return InspectionCreateSerializer
        return InspectionVisuelleSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        inspection = serializer.save(utilisateur=request.user)
        out = InspectionVisuelleSerializer(inspection, context={'request': request})
        return Response(out.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='analyze',
            permission_classes=[InspectionAccessPermission])
    def analyze(self, request, pk=None):
        """Lance l'analyse IA de l'image d'une inspection (module 4)."""
        inspection = self.get_object()
        inspection.statut_analyse = InspectionVisuelle.StatutAnalyse.EN_ANALYSE
        inspection.erreur_message = ''
        inspection.save(update_fields=['statut_analyse', 'erreur_message', 'updated_at'])

        try:
            service = get_vision_service()
            result = service.analyze_image(inspection.image)
            if not isinstance(result, dict):
                raise ValueError("Résultat d'analyse invalide.")
        except Exception as exc:  # service indisponible / erreur inattendue
            inspection.statut_analyse = InspectionVisuelle.StatutAnalyse.ERREUR
            inspection.erreur_message = f"Erreur lors de l'analyse : {exc}"
            inspection.save(update_fields=['statut_analyse', 'erreur_message', 'updated_at'])
            out = InspectionVisuelleSerializer(inspection, context={'request': request})
            return Response(
                {'detail': inspection.erreur_message, 'inspection': out.data},
                status=status.HTTP_400_BAD_REQUEST,
            )

        inspection.resultat_analyse = result
        inspection.score_confiance = result.get('confidence')
        inspection.statut_analyse = InspectionVisuelle.StatutAnalyse.TERMINEE
        inspection.save(update_fields=[
            'resultat_analyse', 'score_confiance', 'statut_analyse', 'updated_at',
        ])
        out = InspectionVisuelleSerializer(inspection, context={'request': request})
        return Response(out.data, status=status.HTTP_200_OK)

