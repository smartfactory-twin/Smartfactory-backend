"""Module 8 — Serializers des alertes, notifications et canaux."""
from rest_framework import serializers

from .models import Alerte, Notification, PreferenceNotification


class AlerteListSerializer(serializers.ModelSerializer):
    """Ligne de liste : de quoi trier, filtrer et afficher la table."""

    niveau_label = serializers.CharField(source='get_niveau_display', read_only=True)
    statut_label = serializers.CharField(source='get_statut_display', read_only=True)
    type_alerte_label = serializers.CharField(source='get_type_alerte_display', read_only=True)

    machine_nom = serializers.CharField(source='machine.nom', read_only=True)
    machine_identifiant = serializers.CharField(
        source='machine.identifiant_interne', read_only=True,
    )
    capteur_identifiant = serializers.CharField(source='capteur.identifiant', read_only=True)
    capteur_nom = serializers.CharField(source='capteur.nom', read_only=True)
    acquittee_par_nom = serializers.SerializerMethodField()

    class Meta:
        model = Alerte
        fields = [
            'id', 'reference', 'niveau', 'niveau_label', 'statut', 'statut_label',
            'type_alerte', 'type_alerte_label',
            'machine', 'machine_nom', 'machine_identifiant',
            'capteur', 'capteur_identifiant', 'capteur_nom',
            'valeur', 'seuil', 'unite', 'message',
            'nb_occurrences', 'date_declenchement', 'derniere_occurrence',
            'date_acquittement', 'acquittee_par_nom', 'date_resolution',
        ]
        read_only_fields = fields

    def get_acquittee_par_nom(self, obj):
        if not obj.acquittee_par_id:
            return None
        return f'{obj.acquittee_par.prenom} {obj.acquittee_par.nom}'.strip()


class AlerteDetailSerializer(AlerteListSerializer):
    """Détail d'une alerte (§12) : tout l'historique de traitement."""

    lecture = serializers.IntegerField(source='lecture_id', read_only=True, allow_null=True)
    lecture_valeur = serializers.SerializerMethodField()
    lecture_timestamp = serializers.SerializerMethodField()
    acquittee_par = serializers.IntegerField(
        source='acquittee_par_id', read_only=True, allow_null=True,
    )
    acquittable = serializers.SerializerMethodField()
    ratio_plage_libelle = serializers.SerializerMethodField()
    anomalie_ia_score = serializers.FloatField(read_only=True, allow_null=True)

    class Meta(AlerteListSerializer.Meta):
        fields = AlerteListSerializer.Meta.fields + [
            'lecture', 'lecture_valeur', 'lecture_timestamp',
            'depassement', 'ratio_plage_pct', 'ratio_plage_libelle',
            'derniere_valeur', 'commentaire_acquittement', 'acquittee_par',
            'message_resolution', 'est_ouverte', 'acquittable',
            'anomalie_ia_score',
        ]
        read_only_fields = fields

    def get_lecture_valeur(self, obj):
        return obj.lecture.valeur if obj.lecture_id else None

    def get_lecture_timestamp(self, obj):
        return obj.lecture.timestamp if obj.lecture_id else None

    def get_acquittable(self, obj):
        return obj.est_acquittable

    def get_ratio_plage_libelle(self, obj):
        return f'{obj.ratio_plage_pct:.1f} %'


class AcquittementSerializer(serializers.Serializer):
    """Acquittement (UC-29) : commentaire **obligatoire** (§13)."""

    commentaire = serializers.CharField(
        allow_blank=False, trim_whitespace=True,
        error_messages={
            'required': "Un commentaire est obligatoire pour acquitter une alerte.",
            'blank': "Un commentaire est obligatoire pour acquitter une alerte.",
        },
    )

    def validate_commentaire(self, value):
        value = (value or '').strip()
        if not value:
            raise serializers.ValidationError(
                "Un commentaire est obligatoire pour acquitter une alerte."
            )
        return value


class ResolutionSerializer(serializers.Serializer):
    """Résolution manuelle (ADMIN / TECHNICIEN)."""

    motif = serializers.CharField(required=False, allow_blank=True, default='')


class PreparerOtSerializer(serializers.Serializer):
    """Pré-remplissage d'un ordre de travail (§14).

    Le Module 9 (CMMS) n'est pas développé : cet objet n'est **qu'un
    récapitulatif des informations** que l'OT recevra. Aucun OT n'est créé.
    """


class NotificationSerializer(serializers.ModelSerializer):
    type_label = serializers.CharField(source='get_type_display', read_only=True)
    niveau_label = serializers.CharField(source='get_niveau_display', read_only=True)
    alerte_reference = serializers.CharField(source='alerte.reference', read_only=True)
    machine_nom = serializers.SerializerMethodField()
    machine_identifiant = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = [
            'id', 'type', 'type_label', 'titre', 'message', 'niveau', 'niveau_label',
            'lue', 'date_creation', 'date_lecture',
            'alerte', 'alerte_reference', 'machine_nom', 'machine_identifiant',
        ]
        read_only_fields = fields

    def get_machine_nom(self, obj):
        return obj.alerte.machine.nom if obj.alerte_id else None

    def get_machine_identifiant(self, obj):
        return obj.alerte.machine.identifiant_interne if obj.alerte_id else None


class PreferenceNotificationSerializer(serializers.ModelSerializer):
    """UC-28 — canaux de notification de l'utilisateur connecté."""

    adresse_email_effective = serializers.CharField(
        source='adresse_email', read_only=True,
    )
    email_possible = serializers.SerializerMethodField()
    sms_possible = serializers.SerializerMethodField()

    class Meta:
        model = PreferenceNotification
        fields = [
            'in_app', 'email', 'sms', 'email_destination',
            'niveau_min_email', 'adresse_email_effective',
            'email_possible', 'sms_possible',
        ]

    def get_email_possible(self, obj):
        from .notifications import NotificationService
        return NotificationService.smtp_configure()

    def get_sms_possible(self, obj):
        return False  # Twilio : architecture prête, non activée dans ce sprint.

    def validate_email(self, value):
        # Activer l'email alors qu'aucun SMTP n'est configuré est autorisé :
        # l'envoi sera simplement journalisé comme « non configuré » et
        # l'archivage de la preference n'échoue pas.
        return value

    def validate_sms(self, value):
        return value
