import os

from PIL import Image, UnidentifiedImageError

from django.conf import settings

from rest_framework import serializers
from django.utils import timezone
from .models import (
    Usine, Zone, LigneProduction, Machine, Document, Composant, Sensor, Reading,
    InspectionVisuelle, UserScope, OrdreTravail, MaintenanceRecurrente,
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
    derniere_valeur = serializers.FloatField(read_only=True, allow_null=True)
    derniere_unite = serializers.CharField(read_only=True, allow_null=True)
    derniere_lecture_at = serializers.DateTimeField(read_only=True, allow_null=True)

    class Meta:
        model = Machine
        fields = [
            'id', 'nom', 'identifiant_interne', 'numero_serie', 'type_equipement',
            'marque', 'modele', 'statut', 'date_installation',
            'derniere_valeur', 'derniere_unite', 'derniere_lecture_at',
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
            'modele', 'type_equipement', 'date_installation', 'position_sur_plan', 'statut',
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
        fields = ['id', 'nom', 'identifiant_interne', 'type_equipement', 'statut', 'statut_label', 'composants']


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

ALLOWED_MEDIA_CONTENT_TYPES = {
    '.jpg': {'image/jpeg', 'image/jpg'},
    '.jpeg': {'image/jpeg', 'image/jpg'},
    '.png': {'image/png'},
    '.webp': {'image/webp'},
}
ALLOWED_MEDIA_EXTENSIONS = set(ALLOWED_MEDIA_CONTENT_TYPES)


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
    image_annotee = serializers.SerializerMethodField()

    class Meta:
        model = InspectionVisuelle
        fields = [
            'id', 'machine', 'machine_nom', 'machine_identifiant', 'machine_statut',
            'ligne_nom', 'usine_nom', 'image', 'date_inspection',
            'media_type', 'image_annotee', 'annotations',
            'utilisateur', 'utilisateur_nom', 'statut_analyse', 'statut_analyse_label',
            'statut', 'defect_detected', 'defect_type', 'confidence', 'observation',
            'resultat_analyse', 'score_confiance', 'observations', 'erreur_message',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'date_inspection', 'utilisateur', 'statut_analyse', 'statut',
            'defect_detected', 'defect_type', 'confidence', 'observation',
            'resultat_analyse', 'score_confiance', 'erreur_message',
            'media_type', 'annotations',
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

    def get_image_annotee(self, obj):
        return self._abs_url(obj.image_annotee)

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

    image = serializers.FileField(required=True)

    class Meta:
        model = InspectionVisuelle
        fields = ['machine', 'image', 'observations']

    def validate_machine(self, machine):
        if not Machine.objects.filter(pk=machine.pk).exists():
            raise serializers.ValidationError('Machine introuvable.')
        return machine

    def validate_image(self, image):
        """Vérifie le format réel du média et bloque les extensions déguisées."""
        max_mb = getattr(settings, 'INSPECTION_IMAGE_MAX_MB', 20)
        if max_mb and image.size > max_mb * 1024 * 1024:
            raise serializers.ValidationError(
                f"Le fichier ne doit pas dépasser {max_mb} Mo."
            )
        extension = os.path.splitext(getattr(image, 'name', '') or '')[1].lower()
        if extension not in ALLOWED_MEDIA_EXTENSIONS:
            raise serializers.ValidationError(
                'Formats acceptés : JPG, PNG et WEBP.'
            )
        content_type = (getattr(image, 'content_type', '') or '').lower()
        if content_type and content_type not in ALLOWED_MEDIA_CONTENT_TYPES[extension]:
            raise serializers.ValidationError(
                'Le type MIME ne correspond pas au format du fichier.'
            )
        image.seek(0)
        try:
            with Image.open(image) as decoded:
                expected = {'.jpg': 'JPEG', '.jpeg': 'JPEG', '.png': 'PNG', '.webp': 'WEBP'}[extension]
                if decoded.format != expected:
                    raise serializers.ValidationError('Le contenu ne correspond pas à l’extension du fichier.')
                decoded.verify()
        except (UnidentifiedImageError, OSError, ValueError):
            raise serializers.ValidationError('Le fichier image est illisible ou invalide.')
        image.seek(0)
        return image

    def create(self, validated_data):
        validated_data['media_type'] = InspectionVisuelle.TypeMedia.IMAGE
        return super().create(validated_data)


class InspectionAnnotationSerializer(serializers.Serializer):
    """Valide l'image composée et les formes sauvées par l'éditeur canvas."""

    image = serializers.FileField()
    annotations = serializers.JSONField(required=False, default=list)

    def validate_image(self, image):
        extension = os.path.splitext(getattr(image, 'name', '') or '')[1].lower()
        if extension not in {'.jpg', '.jpeg', '.png', '.webp'}:
            raise serializers.ValidationError('L’image annotée doit être au format JPG, PNG ou WEBP.')
        max_mb = getattr(settings, 'INSPECTION_IMAGE_MAX_MB', 20)
        if max_mb and image.size > max_mb * 1024 * 1024:
            raise serializers.ValidationError(f"L'image annotée ne doit pas dépasser {max_mb} Mo.")
        try:
            with Image.open(image) as decoded:
                decoded.verify()
        except (UnidentifiedImageError, OSError, ValueError):
            raise serializers.ValidationError('Le fichier d’image annotée est illisible.')
        image.seek(0)
        return image

    def validate_annotations(self, value):
        if not isinstance(value, list) or len(value) > 100:
            raise serializers.ValidationError('Les annotations doivent être une liste de 100 éléments maximum.')
        supported = {'rectangle', 'circle', 'arrow', 'comment'}
        for annotation in value:
            if not isinstance(annotation, dict) or annotation.get('type') not in supported:
                raise serializers.ValidationError('Une annotation contient un type non reconnu.')
            if not all(isinstance(annotation.get(key), (int, float)) for key in ('x', 'y')):
                raise serializers.ValidationError('Chaque annotation doit avoir une position valide.')
            if annotation['type'] == 'comment' and len(str(annotation.get('text', ''))) > 500:
                raise serializers.ValidationError('Un commentaire d’annotation est limité à 500 caractères.')
        return value


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


class OrdreTravailSerializer(serializers.ModelSerializer):
    machine_id = serializers.PrimaryKeyRelatedField(source='machine', queryset=Machine.objects.all())
    machine_nom = serializers.CharField(source='machine.nom', read_only=True)
    type = serializers.ChoiceField(source='type_ordre', choices=OrdreTravail.Type.choices, required=False)
    historique = serializers.JSONField(read_only=True)
    rapport = serializers.JSONField(read_only=True, allow_null=True)

    class Meta:
        model = OrdreTravail
        fields = [
            'id', 'machine_id', 'machine_nom', 'type', 'priorite', 'titre',
            'assigne', 'statut', 'echeance', 'from_alert', 'historique',
            'rapport', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'historique', 'rapport', 'created_at', 'updated_at']

    def validate(self, attrs):
        next_status = attrs.get('statut')
        instance = self.instance
        request = self.context.get('request')
        if instance and next_status and next_status != instance.statut:
            order = list(OrdreTravail.Statut.values)
            if next_status not in order or order.index(next_status) != order.index(instance.statut) + 1:
                raise serializers.ValidationError({'statut': 'Le statut doit suivre l’étape suivante du workflow.'})
            if next_status in (OrdreTravail.Statut.VALIDE, OrdreTravail.Statut.CLOTURE) and getattr(request.user, 'role', None) != 'ADMIN':
                raise serializers.ValidationError({'statut': 'La validation et la clôture sont réservées à l’administrateur.'})
        return attrs

    def create(self, validated_data):
        from django.utils import timezone
        from datetime import timedelta

        assigne = validated_data.get('assigne', '').strip()
        validated_data['statut'] = OrdreTravail.Statut.ASSIGNE if assigne and assigne != '—' else OrdreTravail.Statut.CREE
        validated_data.setdefault('echeance', timezone.now() + timedelta(days=2 if validated_data.get('priorite') == OrdreTravail.Priorite.HAUTE else 7))
        obj = OrdreTravail.objects.create(**validated_data)
        obj.historique = [{'statut': obj.statut, 'date': obj.created_at.isoformat()}]
        obj.save(update_fields=['historique', 'updated_at'])
        return obj

    def update(self, instance, validated_data):
        next_status = validated_data.pop('statut', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if next_status and next_status != instance.statut:
            instance.statut = next_status
            instance.historique = [*instance.historique, {'statut': next_status, 'date': timezone.now().isoformat()}]
        instance.save()
        return instance


class MaintenanceRecurrenteSerializer(serializers.ModelSerializer):
    machine_id = serializers.PrimaryKeyRelatedField(source='machine', queryset=Machine.objects.all())
    machine_nom = serializers.CharField(source='machine.nom', read_only=True)

    class Meta:
        model = MaintenanceRecurrente
        fields = ['id', 'machine_id', 'machine_nom', 'titre', 'frequence_jours', 'date_debut', 'created_at']
        read_only_fields = ['id', 'machine_nom', 'created_at']

    def validate_frequence_jours(self, value):
        if value < 1:
            raise serializers.ValidationError('La fréquence doit être d’au moins un jour.')
        return value


class PieceInterventionSerializer(serializers.Serializer):
    ref = serializers.CharField(max_length=100)
    qte = serializers.IntegerField(min_value=1)
    cout = serializers.FloatField(min_value=0)


class RapportInterventionSerializer(serializers.Serializer):
    travaux = serializers.CharField()
    pieces = PieceInterventionSerializer(many=True, required=False)
    duree = serializers.FloatField(min_value=0)
    observations = serializers.CharField(required=False, allow_blank=True)
    signataire = serializers.CharField(max_length=200)
    signature_data_url = serializers.CharField(max_length=1_500_000, required=False, allow_blank=True)
