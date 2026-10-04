import os

from django.conf import settings

from rest_framework import serializers
from .models import (
    Usine, Zone, LigneProduction, Machine, Document, Composant, Sensor, Reading,
    InspectionVisuelle, UserScope,
)
from .readings_io import normalize_timestamp


class UsineSerializer(serializers.ModelSerializer):
    zones_count = serializers.SerializerMethodField()

    class Meta:
        model = Usine
        fields = ['id', 'nom', 'adresse', 'description', 'zones_count', 'created_at', 'updated_at']

    def get_zones_count(self, obj):
        return obj.zones.count()


class ZoneSerializer(serializers.ModelSerializer):
    usine_nom    = serializers.CharField(source='usine.nom', read_only=True)
    lignes_count = serializers.SerializerMethodField()

    class Meta:
        model = Zone
        fields = ['id', 'nom', 'usine', 'usine_nom', 'description', 'lignes_count']

    def get_lignes_count(self, obj):
        return obj.lignes.count()


class LigneProductionSerializer(serializers.ModelSerializer):
    zone_nom       = serializers.CharField(source='zone.nom', read_only=True)
    usine_nom      = serializers.CharField(source='zone.usine.nom', read_only=True)
    machines_count = serializers.SerializerMethodField()

    class Meta:
        model = LigneProduction
        fields = ['id', 'nom', 'zone', 'zone_nom', 'usine_nom', 'description', 'machines_count']

    def get_machines_count(self, obj):
        return obj.machines.count()


class ComposantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Composant
        fields = ['id', 'nom', 'machine', 'description', 'numero_piece']


class DocumentSerializer(serializers.ModelSerializer):
    fichier = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = ['id', 'nom', 'type_document', 'fichier', 'created_at', 'machine']

    def get_fichier(self, obj):
        if obj.fichier and hasattr(obj.fichier, 'url'):
            return obj.fichier.url
        return None


class MachineListSerializer(serializers.ModelSerializer):
    ligne_production_nom = serializers.CharField(source='ligne_production.nom', read_only=True)
    zone_nom             = serializers.SerializerMethodField()
    usine_nom            = serializers.SerializerMethodField()
    photo                = serializers.SerializerMethodField()

    class Meta:
        model = Machine
        fields = [
            'id', 'nom', 'identifiant_interne', 'numero_serie',
            'marque', 'modele', 'statut', 'date_installation',
            'ligne_production', 'ligne_production_nom',
            'zone_nom', 'usine_nom', 'photo',
        ]

    def get_zone_nom(self, obj):
        if obj.ligne_production and obj.ligne_production.zone:
            return obj.ligne_production.zone.nom
        return None

    def get_usine_nom(self, obj):
        if obj.ligne_production and obj.ligne_production.zone and obj.ligne_production.zone.usine:
            return obj.ligne_production.zone.usine.nom
        return None

    def get_photo(self, obj):
        if obj.photo and hasattr(obj.photo, 'url'):
            return obj.photo.url
        return None


class MachineDetailSerializer(MachineListSerializer):
    composants = ComposantSerializer(many=True, read_only=True)
    documents  = DocumentSerializer(many=True, read_only=True)
    zone       = serializers.SerializerMethodField()
    usine      = serializers.SerializerMethodField()
    ligne_nom  = serializers.CharField(source='ligne_production.nom', read_only=True, default=None)

    class Meta(MachineListSerializer.Meta):
        fields = MachineListSerializer.Meta.fields + [
            'position_sur_plan', 'description', 'composants', 'documents',
            'zone', 'usine', 'ligne_nom',
            'created_at', 'updated_at',
        ]

    def get_zone(self, obj):
        return obj.ligne_production.zone_id if obj.ligne_production_id else None

    def get_usine(self, obj):
        ligne = obj.ligne_production
        return ligne.zone.usine_id if ligne and ligne.zone_id else None


class MachineCreateUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Machine
        fields = [
            'id', 'nom', 'identifiant_interne', 'numero_serie', 'marque',
            'modele', 'date_installation', 'position_sur_plan', 'statut',
            'ligne_production', 'photo', 'description',
        ]
        read_only_fields = ['id']


# ── Serializers hiérarchie imbriquée ──────────────────────────────────────────

class ComposantNestedSerializer(serializers.ModelSerializer):
    class Meta:
        model = Composant
        fields = ['id', 'nom', 'numero_piece', 'description']


class MachineNestedSerializer(serializers.ModelSerializer):
    composants = ComposantNestedSerializer(many=True, read_only=True)
    statut_label = serializers.CharField(source='get_statut_display', read_only=True)

    class Meta:
        model = Machine
        fields = ['id', 'nom', 'identifiant_interne', 'statut', 'statut_label', 'composants']


class LigneNestedSerializer(serializers.ModelSerializer):
    machines = MachineNestedSerializer(many=True, read_only=True)

    class Meta:
        model = LigneProduction
        fields = ['id', 'nom', 'machines']


class ZoneNestedSerializer(serializers.ModelSerializer):
    lignes = LigneNestedSerializer(many=True, read_only=True)

    class Meta:
        model = Zone
        fields = ['id', 'nom', 'lignes']


class UsineHierarchieSerializer(serializers.ModelSerializer):
    zones = ZoneNestedSerializer(many=True, read_only=True)

    class Meta:
        model = Usine
        fields = ['id', 'nom', 'adresse', 'zones']


# ── Capteurs & Lectures ─────────────────────────────────────────────────────────

class SensorSerializer(serializers.ModelSerializer):
    machine_nom = serializers.CharField(source='machine.nom', read_only=True)
    machine_identifiant = serializers.CharField(source='machine.identifiant_interne', read_only=True)

    class Meta:
        model = Sensor
        fields = [
            'id', 'identifiant', 'nom', 'type_capteur', 'machine',
            'machine_nom', 'machine_identifiant', 'unite', 'frequence_mesure',
            'seuil_min', 'seuil_max', 'actif', 'description', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate(self, attrs):
        # Fusionne avec l'instance existante pour valider aussi les PATCH partiels.
        instance = self.instance
        seuil_min = attrs.get('seuil_min', getattr(instance, 'seuil_min', None))
        seuil_max = attrs.get('seuil_max', getattr(instance, 'seuil_max', None))
        frequence = attrs.get('frequence_mesure', getattr(instance, 'frequence_mesure', None))

        if seuil_min is not None and seuil_max is not None and seuil_min >= seuil_max:
            raise serializers.ValidationError({
                'seuil_min': 'Le seuil minimum doit être inférieur au seuil maximum.',
                'seuil_max': 'Le seuil maximum doit être supérieur au seuil minimum.',
            })
        if frequence is not None and frequence <= 0:
            raise serializers.ValidationError({
                'frequence_mesure': 'La fréquence de mesure doit être supérieure à 0.'
            })
        return attrs


class SensorListSerializer(SensorSerializer):
    pass


class SensorDetailSerializer(SensorSerializer):
    class Meta(SensorSerializer.Meta):
        fields = SensorSerializer.Meta.fields


class FlexibleSensorField(serializers.PrimaryKeyRelatedField):
    """Accepte aussi bien l'ID numérique que l'identifiant unique du capteur."""

    def to_internal_value(self, data):
        queryset = self.get_queryset()
        try:
            return queryset.get(pk=data)
        except (Sensor.DoesNotExist, ValueError, TypeError):
            pass
        try:
            return queryset.get(identifiant=str(data).strip())
        except Sensor.DoesNotExist:
            self.fail('does_not_exist', pk_value=data)


class ReadingSerializer(serializers.ModelSerializer):
    sensor = FlexibleSensorField(queryset=Sensor.objects.all())
    sensor_identifiant = serializers.CharField(source='sensor.identifiant', read_only=True)
    value = serializers.SerializerMethodField()

    class Meta:
        model = Reading
        fields = [
            'id', 'sensor', 'sensor_identifiant', 'valeur', 'value', 'timestamp',
            'hors_plage', 'est_valide', 'interpolation', 'created_at'
        ]
        read_only_fields = ['id', 'hors_plage', 'est_valide', 'interpolation', 'created_at']
        extra_kwargs = {'valeur': {'required': False}}

    def get_value(self, obj):
        return obj.valeur

    def to_internal_value(self, data):
        # Alias `value` (spécification IoT) → `valeur`.
        if hasattr(data, 'copy'):
            data = data.copy()
        else:
            data = dict(data)
        if 'valeur' not in data and 'value' in data:
            data['valeur'] = data['value']
        return super().to_internal_value(data)

    def validate_timestamp(self, value):
        # RULE 3 : normalisation UTC.
        try:
            return normalize_timestamp(value)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc))

    def validate(self, attrs):
        if self.instance is None and attrs.get('valeur') is None:
            raise serializers.ValidationError({'value': 'Les champs value (ou valeur) sont requis.'})
        return attrs


# ── Module 4 — Inspections visuelles ──────────────────────────────────────────

ALLOWED_IMAGE_CONTENT_TYPES = {'image/jpeg', 'image/jpg', 'image/png'}
ALLOWED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png'}


class InspectionVisuelleSerializer(serializers.ModelSerializer):
    """Serializer de lecture : expose la machine, l'utilisateur et le résultat."""

    machine_nom = serializers.CharField(source='machine.nom', read_only=True)
    machine_identifiant = serializers.CharField(
        source='machine.identifiant_interne', read_only=True
    )
    machine_statut = serializers.CharField(source='machine.statut', read_only=True)
    ligne_nom = serializers.SerializerMethodField()
    usine_nom = serializers.SerializerMethodField()
    utilisateur_nom = serializers.SerializerMethodField()
    statut_analyse_label = serializers.CharField(
        source='get_statut_analyse_display', read_only=True
    )
    statut = serializers.CharField(source='statut_analyse', read_only=True)
    image = serializers.SerializerMethodField()

    class Meta:
        model = InspectionVisuelle
        fields = [
            'id', 'machine', 'machine_nom', 'machine_identifiant', 'machine_statut',
            'ligne_nom', 'usine_nom', 'image', 'date_inspection',
            'utilisateur', 'utilisateur_nom', 'statut_analyse', 'statut_analyse_label',
            'statut', 'defect_detected', 'defect_type', 'confidence', 'observation',
            'resultat_analyse', 'score_confiance', 'observations', 'erreur_message',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'date_inspection', 'utilisateur', 'statut_analyse', 'statut',
            'defect_detected', 'defect_type', 'confidence', 'observation',
            'resultat_analyse', 'score_confiance', 'erreur_message',
            'created_at', 'updated_at',
        ]

    def _abs_url(self, file_field):
        if file_field and hasattr(file_field, 'url'):
            request = self.context.get('request')
            url = file_field.url
            return request.build_absolute_uri(url) if request else url
        return None

    def get_image(self, obj):
        return self._abs_url(obj.image)

    def get_ligne_nom(self, obj):
        if obj.machine and obj.machine.ligne_production:
            return obj.machine.ligne_production.nom
        return None

    def get_usine_nom(self, obj):
        machine = obj.machine
        if (machine and machine.ligne_production and machine.ligne_production.zone
                and machine.ligne_production.zone.usine):
            return machine.ligne_production.zone.usine.nom
        return None

    def get_utilisateur_nom(self, obj):
        if obj.utilisateur:
            return f'{obj.utilisateur.prenom} {obj.utilisateur.nom}'.strip()
        return None


class InspectionCreateSerializer(serializers.ModelSerializer):
    """Serializer de création : machine + image (multipart)."""

    class Meta:
        model = InspectionVisuelle
        fields = ['machine', 'image', 'observations']

    def validate_machine(self, machine):
        if not Machine.objects.filter(pk=machine.pk).exists():
            raise serializers.ValidationError('Machine introuvable.')
        return machine

    def validate_image(self, image):
        # Taille maximale configurable.
        max_mb = getattr(settings, 'INSPECTION_IMAGE_MAX_MB', 5)
        if max_mb and image.size > max_mb * 1024 * 1024:
            raise serializers.ValidationError(
                f"L'image ne doit pas dépasser {max_mb} Mo."
            )

        # Type MIME (le champ ImageField de DRF a déjà validé qu'il s'agit
        # d'une image réelle via Pillow ; on restreint en plus les formats).
        content_type = (getattr(image, 'content_type', '') or '').lower()
        if content_type and content_type not in ALLOWED_IMAGE_CONTENT_TYPES:
            raise serializers.ValidationError(
                "Format d'image non supporté. Formats acceptés : JPG, JPEG, PNG."
            )

        # Extension du fichier.
        name = getattr(image, 'name', '') or ''
        extension = os.path.splitext(name)[1].lower()
        if extension and extension not in ALLOWED_IMAGE_EXTENSIONS:
            raise serializers.ValidationError(
                "Extension d'image non supportée. Utilisez .jpg, .jpeg ou .png."
            )
        return image


# ── Périmètres d'accès (UserScope) ─────────────────────────────────────────────

class UserScopeSerializer(serializers.ModelSerializer):
    """Affectation d'un utilisateur à un périmètre de la hiérarchie.

    Expose une lecture « chemin » (`libelle`) ainsi que les machines
    réellement ouvertes par *cette* affectation, pour que le frontend
    n'ait aucune logique d'accès à recalculer.
    """

    utilisateur_nom = serializers.SerializerMethodField()
    niveau           = serializers.SerializerMethodField()
    libelle          = serializers.SerializerMethodField()

    # Les 4 niveaux cibles sont optionnels : c'est `validate()` qui impose
    # qu'exactement UN soit renseigné (les drf ModelSerializer ne déduisent pas
    # `required=False` depuis `blank=True` sur ces FK, d'où la déclaration ici).
    usine = serializers.PrimaryKeyRelatedField(
        queryset=Usine.objects.all(), required=False, allow_null=True)
    zone = serializers.PrimaryKeyRelatedField(
        queryset=Zone.objects.all(), required=False, allow_null=True)
    ligne = serializers.PrimaryKeyRelatedField(
        queryset=LigneProduction.objects.all(), required=False, allow_null=True)
    machine = serializers.PrimaryKeyRelatedField(
        queryset=Machine.objects.all(), required=False, allow_null=True)

    usine_nom             = serializers.CharField(source='usine.nom', read_only=True, default=None)
    zone_nom              = serializers.CharField(source='zone.nom', read_only=True, default=None)
    ligne_nom             = serializers.CharField(source='ligne.nom', read_only=True, default=None)
    ligne_zone_nom        = serializers.CharField(source='ligne.zone.nom', read_only=True, default=None)
    ligne_zone_usine_nom  = serializers.CharField(source='ligne.zone.usine.nom', read_only=True, default=None)
    machine_nom           = serializers.CharField(source='machine.nom', read_only=True, default=None)
    machine_identifiant   = serializers.CharField(source='machine.identifiant_interne', read_only=True, default=None)

    machines_accessibles      = serializers.SerializerMethodField()
    nb_machines_accessibles   = serializers.SerializerMethodField()
    cible_ids                 = serializers.SerializerMethodField()
    est_active                = serializers.SerializerMethodField()

    class Meta:
        model = UserScope
        fields = [
            'id', 'utilisateur', 'utilisateur_nom', 'niveau', 'libelle',
            'usine', 'usine_nom',
            'zone', 'zone_nom',
            'ligne', 'ligne_nom', 'ligne_zone_nom', 'ligne_zone_usine_nom',
            'machine', 'machine_nom', 'machine_identifiant',
            'actif', 'est_active', 'date_debut', 'date_fin',
            'machines_accessibles', 'nb_machines_accessibles', 'cible_ids',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']

    def get_utilisateur_nom(self, obj):
        return f'{obj.utilisateur.prenom} {obj.utilisateur.nom}'.strip()

    def get_niveau(self, obj):
        for niveau in ('usine', 'zone', 'ligne', 'machine'):
            if getattr(obj, f'{niveau}_id'):
                return niveau
        return None

    def get_libelle(self, obj):
        """Chemin lisible : « Usine → Zone → Ligne » ou « Machine »."""
        if obj.machine_id:
            return obj.machine.nom
        if obj.ligne_id:
            return f'{obj.ligne.zone.usine.nom} → {obj.ligne.zone.nom} → {obj.ligne.nom}'
        if obj.zone_id:
            return f'{obj.zone.usine.nom} → {obj.zone.nom}'
        if obj.usine_id:
            return obj.usine.nom
        return '—'

    def _machines(self, obj):
        """Machines ouvertes par CETTE affectation (source : scope_machine_q)."""
        from .permissions import scope_machine_q
        return Machine.objects.filter(scope_machine_q(obj)).order_by('nom', 'id')

    def get_machines_accessibles(self, obj):
        return [
            {
                'id': m.id,
                'nom': m.nom,
                'identifiant_interne': m.identifiant_interne,
                'statut': m.statut,
            }
            for m in self._machines(obj)
        ]

    def get_nb_machines_accessibles(self, obj):
        return self._machines(obj).count()

    def get_cible_ids(self, obj):
        """IDs de la chaîne Usine → Zone → Ligne de la cible de l'affectation.

        Permet au frontend de pré-remplir le sélecteur hiérarchique sans
        refaire la remontée d hierarchie (utile pour modifier une affectation
        ciblant une machine, qui n'expose pas directement sa ligne).
        """
        ligne = None
        if obj.ligne_id:
            ligne = obj.ligne
        elif obj.machine_id:
            ligne = obj.machine.ligne_production

        zone = ligne.zone if ligne else (obj.zone if obj.zone_id else None)
        usine = zone.usine if zone else (obj.usine if obj.usine_id else None)
        return {
            'usine': usine.id if usine else None,
            'zone': zone.id if zone else None,
            'ligne': ligne.id if ligne else None,
            'machine': obj.machine_id,
        }

    def get_est_active(self, obj):
        return obj.est_active()

    def validate(self, attrs):
        """Refuse toute combinaison incohérente (contrôle serveur)."""
        base = {
            'usine': attrs.get('usine', getattr(self.instance, 'usine', None)),
            'zone': attrs.get('zone', getattr(self.instance, 'zone', None)),
            'ligne': attrs.get('ligne', getattr(self.instance, 'ligne', None)),
            'machine': attrs.get('machine', getattr(self.instance, 'machine', None)),
        }
        cibles = [k for k, v in base.items() if v is not None]
        if len(cibles) != 1:
            raise serializers.ValidationError(
                "Une affectation doit cibler exactement un niveau : "
                "usine, zone, ligne de production ou machine."
            )
        return attrs


class UserScopeBulkCreateSerializer(serializers.Serializer):
    """Payload `perimetres` envoyé à la création d'un utilisateur.

    Format : [{ "usine": 1 }, { "zone": 2 }, { "ligne": 3 }, { "machine": 4 }]
    """

    perimetres = UserScopeSerializer(many=True, required=False)

    def create(self, validated_data):
        raise NotImplementedError  # usage interne uniquement


class MonPerimetreSerializer(serializers.Serializer):
    """Vue résolue du périmètre de l'utilisateur *courant*.

    S'appuie directement sur `scope_queryset_machine()` / `accessible_machine_ids()` :
    le backend reste l'unique source de vérité, le frontend ne fait que l'afficher.
    """

    def to_representation(self, user):
        from .permissions import scope_queryset_machine

        machines = scope_queryset_machine(
            Machine.objects.select_related('ligne_production').all(), user
        ).order_by('nom', 'id')

        return {
            'role': user.role,
            'role_label': user.get_role_display(),
            'acces_global': user.role == 'ADMIN',
            'nb_machines_accessibles': machines.count(),
            'machines': [
                {
                    'id': m.id,
                    'nom': m.nom,
                    'identifiant_interne': m.identifiant_interne,
                    'statut': m.statut,
                    'ligne': m.ligne_production_id,
                    'ligne_nom': (
                        m.ligne_production.nom if m.ligne_production_id else None
                    ),
                }
                for m in machines
            ],
            'affectations': UserScopeSerializer(
                user.scopes.select_related('usine', 'zone', 'ligne', 'machine'), many=True
            ).data,
        }
