from rest_framework import serializers
from .models import Usine, Zone, LigneProduction, Machine, Document, Composant


class UsineSerializer(serializers.ModelSerializer):
    zones_count = serializers.SerializerMethodField()

    class Meta:
        model = Usine
        fields = '__all__'

    def get_zones_count(self, obj):
        return obj.zones.count()


class ZoneSerializer(serializers.ModelSerializer):
    usine_nom = serializers.CharField(source='usine.nom', read_only=True)

    class Meta:
        model = Zone
        fields = ['id', 'nom', 'usine', 'usine_nom', 'description']


class LigneProductionSerializer(serializers.ModelSerializer):
    zone_nom = serializers.CharField(source='zone.nom', read_only=True)
    usine_nom = serializers.CharField(source='zone.usine.nom', read_only=True)

    class Meta:
        model = LigneProduction
        fields = ['id', 'nom', 'zone', 'zone_nom', 'usine_nom', 'description']


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
        request = self.context.get('request')
        if obj.fichier and hasattr(obj.fichier, 'url'):
            if request:
                return request.build_absolute_uri(obj.fichier.url)
            return obj.fichier.url
        return None


class MachineListSerializer(serializers.ModelSerializer):
    ligne_production_nom = serializers.CharField(
        source='ligne_production.nom', read_only=True
    )
    zone_nom = serializers.SerializerMethodField()
    usine_nom = serializers.SerializerMethodField()
    photo = serializers.SerializerMethodField()

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
        request = self.context.get('request')
        if obj.photo and hasattr(obj.photo, 'url'):
            if request:
                return request.build_absolute_uri(obj.photo.url)
            return obj.photo.url
        return None


class MachineDetailSerializer(serializers.ModelSerializer):
    composants = ComposantSerializer(many=True, read_only=True)
    documents = DocumentSerializer(many=True, read_only=True)
    zone_nom = serializers.SerializerMethodField()
    usine_nom = serializers.SerializerMethodField()
    ligne_production_nom = serializers.CharField(
        source='ligne_production.nom', read_only=True
    )
    photo = serializers.SerializerMethodField()

    class Meta:
        model = Machine
        fields = '__all__'

    def get_zone_nom(self, obj):
        if obj.ligne_production and obj.ligne_production.zone:
            return obj.ligne_production.zone.nom
        return None

    def get_usine_nom(self, obj):
        if obj.ligne_production and obj.ligne_production.zone and obj.ligne_production.zone.usine:
            return obj.ligne_production.zone.usine.nom
        return None

    def get_photo(self, obj):
        request = self.context.get('request')
        if obj.photo and hasattr(obj.photo, 'url'):
            if request:
                return request.build_absolute_uri(obj.photo.url)
            return obj.photo.url
        return None


class MachineCreateUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Machine
        fields = [
            'nom', 'identifiant_interne', 'numero_serie', 'marque',
            'modele', 'date_installation', 'position_sur_plan', 'statut',
            'ligne_production', 'photo', 'description',
        ]
