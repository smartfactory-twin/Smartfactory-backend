"""Module 8 — Alertes & Notifications (UC-26 à UC-29).

Aucun seuil n'est stocké ici : les règles d'alerte s'appuient **exclusivement**
sur `Sensor.seuil_min` / `Sensor.seuil_max` (Module 3), qui restent la source de
vérité et sont déjà éditables via l'API capteurs.

Trois objets :

* `Alerte`               — l'évènement de dépassement de seuil (historisé) ;
* `Notification`         — la notification In-App de l'utilisateur ;
* `PreferenceNotification` — les canaux de notification choisis (UC-28).
"""
from django.db import models


# ── UC-27 — Niveaux d'alerte ─────────────────────────────────────────────────
# L'ordre de ce tuple définit la gravité croissante : il sert à comparer deux
# niveaux (escalade d'une alerte ouverte).
ORDRE_NIVEAUX = ('INFORMATION', 'MINEURE', 'MAJEURE', 'CRITIQUE')


class Alerte(models.Model):
    """Une alerte déclenchée par une mesure hors plage.

    **Jamais supprimée** (l'historique fait partie du module) : la levée se
    passe par `resoudre()`, qui conserve la ligne et ses horodatages.
    """

    class Niveau(models.TextChoices):
        INFORMATION = 'INFORMATION', 'Information'
        MINEURE = 'MINEURE', 'Mineure'
        MAJEURE = 'MAJEURE', 'Majeure'
        CRITIQUE = 'CRITIQUE', 'Critique'

    class Statut(models.TextChoices):
        ACTIVE = 'ACTIVE', 'Active'
        ACKNOWLEDGED = 'ACKNOWLEDGED', 'Acquittée'
        RESOLVED = 'RESOLVED', 'Résolue'

    class TypeAlerte(models.TextChoices):
        SEUIL_MIN = 'SEUIL_MIN', 'Seuil minimum dépassé'
        SEUIL_MAX = 'SEUIL_MAX', 'Seuil maximum dépassé'
        # Réservé : aucun code ne produit ce type dans ce sprint. La colonne
        # `anomalie_ia_score` + ce type préparent l'intégration IA future
        # (UC-26 « seuil sur le score d'anomalie ») sans aucun modèle IA.
        ANOMALIE_IA = 'ANOMALIE_IA', 'Anomalie IA (réservé)'

    reference = models.CharField(
        max_length=20, unique=True, null=True, blank=True, editable=False,
        verbose_name="Référence",
    )
    machine = models.ForeignKey(
        'equipements.Machine', on_delete=models.CASCADE,
        related_name='alertes', verbose_name="Machine",
    )
    capteur = models.ForeignKey(
        'equipements.Sensor', on_delete=models.CASCADE,
        related_name='alertes', verbose_name="Capteur",
    )
    lecture = models.ForeignKey(
        'equipements.Reading', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='alertes',
        verbose_name="Mesure à l'origine",
    )

    type_alerte = models.CharField(
        max_length=20, choices=TypeAlerte.choices,
        default=TypeAlerte.SEUIL_MAX, verbose_name="Type d'alerte",
    )
    niveau = models.CharField(
        max_length=20, choices=Niveau.choices,
        default=Niveau.MINEURE, verbose_name="Niveau",
    )
    statut = models.CharField(
        max_length=20, choices=Statut.choices,
        default=Statut.ACTIVE, verbose_name="Statut",
    )

    # ── Mesure / seuil au moment du déclenchement ───────────────────────────
    valeur = models.FloatField(verbose_name="Valeur mesurée")
    seuil = models.FloatField(verbose_name="Seuil concerné")
    unite = models.CharField(max_length=50, blank=True, default='', verbose_name="Unité")
    depassement = models.FloatField(
        default=0.0,
        verbose_name="Dépassement (valeur − seuil)",
        help_text="Écart absolu entre la valeur mesurée et le seuil franchi.",
    )
    ratio_plage_pct = models.FloatField(
        default=0.0,
        verbose_name="Dépassement en % de la plage du capteur",
        help_text="(valeur − seuil) / (seuil_max − seuil_min) × 100.",
    )
    message = models.TextField(verbose_name="Message")
    # Réservé à l'intégration IA future : toujours `null` dans ce sprint.
    anomalie_ia_score = models.FloatField(
        null=True, blank=True, verbose_name="Score d'anomalie IA (réservé)",
    )

    # ── Anti-duplication ────────────────────────────────────────────────────
    nb_occurrences = models.PositiveIntegerField(
        default=1, verbose_name="Nombre d'occurrences",
    )
    derniere_valeur = models.FloatField(
        default=0.0, verbose_name="Dernière valeur mesurée",
    )
    derniere_occurrence = models.DateTimeField(verbose_name="Dernière occurrence")

    date_declenchement = models.DateTimeField(verbose_name="Déclenchée le")

    # ── Acquittement (UC-29) ────────────────────────────────────────────────
    date_acquittement = models.DateTimeField(null=True, blank=True, verbose_name="Acquittée le")
    acquittee_par = models.ForeignKey(
        'accounts.Utilisateur', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='alertes_acquittees',
        verbose_name="Acquittée par",
    )
    commentaire_acquittement = models.TextField(
        blank=True, default='', verbose_name="Commentaire d'acquittement",
    )

    # ── Résolution ──────────────────────────────────────────────────────────
    date_resolution = models.DateTimeField(null=True, blank=True, verbose_name="Résolue le")
    message_resolution = models.TextField(blank=True, default='', verbose_name="Motif de résolution")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Alerte"
        verbose_name_plural = "Alertes"
        ordering = ['-date_declenchement', '-pk']
        indexes = [
            models.Index(fields=['statut', '-date_declenchement'], name='alerte_statut_date_idx'),
            models.Index(fields=['machine', 'statut'], name='alerte_machine_statut_idx'),
            models.Index(fields=['capteur', 'statut'], name='alerte_capteur_statut_idx'),
            models.Index(fields=['niveau'], name='alerte_niveau_idx'),
        ]
        constraints = [
            # Anti-duplication : au plus UNE alerte ouverte par capteur et par
            # direction de dépassement. C'est la garantie au niveau base de
            # données ; le moteur la respecte également côté Python.
            models.UniqueConstraint(
                fields=['capteur', 'type_alerte'],
                condition=models.Q(statut__in=['ACTIVE', 'ACKNOWLEDGED']),
                name='alerte_unique_ouverte_par_capteur',
            ),
        ]

    def __str__(self):
        return f'{self.reference or f"AL-{self.pk}"} — {self.machine_id} — {self.get_niveau_display()}'

    # ── Sauvegarde ──────────────────────────────────────────────────────────
    def save(self, *args, **kwargs):
        """Attribue la référence `AL-000123` après l'INSERT (pk nécessaire)."""
        if not self.reference and self.pk is None:
            super().save(*args, **kwargs)
            self.reference = f'AL-{self.pk:06d}'
            Alerte.objects.filter(pk=self.pk).update(reference=self.reference)
        else:
            super().save(*args, **kwargs)

    # ── Aides ───────────────────────────────────────────────────────────────
    @property
    def est_ouverte(self):
        """Une alerte reste « ouverte » jusqu'à sa résolution."""
        return self.statut in (self.Statut.ACTIVE, self.Statut.ACKNOWLEDGED)

    @property
    def est_acquittable(self):
        return self.statut == self.Statut.ACTIVE

    @property
    def niveau_gravite(self):
        return ORDRE_NIVEAUX.index(self.niveau)

    def acquitter(self, utilisateur, commentaire):
        """Passage en ACKNOWLEDGED. Le commentaire est obligatoire (§13)."""
        from django.utils import timezone

        commentaire = (commentaire or '').strip()
        if not commentaire:
            raise ValueError('Un commentaire est obligatoire pour acquitter une alerte.')

        self.acquittee_par = utilisateur
        self.commentaire_acquittement = commentaire
        self.date_acquittement = timezone.now()
        self.statut = self.Statut.ACKNOWLEDGED
        self.save(update_fields=[
            'acquittee_par', 'commentaire_acquittement', 'date_acquittement',
            'statut', 'updated_at',
        ])

    def resoudre(self, motif=''):
        """Clôture de l'alerte (retour à la normale ou action manuelle)."""
        from django.utils import timezone

        if self.statut == self.Statut.RESOLVED:
            return False
        self.statut = self.Statut.RESOLVED
        self.date_resolution = timezone.now()
        self.message_resolution = motif or ''
        self.save(update_fields=['statut', 'date_resolution', 'message_resolution', 'updated_at'])
        return True


class Notification(models.Model):
    """Notification In-App d'un utilisateur (UC-28)."""

    class Type(models.TextChoices):
        ALERTE_CREEE = 'ALERTE_CREEE', 'Alerte créée'
        ESCALADE = 'ESCALADE', 'Alerte aggravée'
        RETOUR_NORMALE = 'RETOUR_NORMALE', 'Retour à la normale'
        INFO = 'INFO', 'Information'

    utilisateur = models.ForeignKey(
        'accounts.Utilisateur', on_delete=models.CASCADE,
        related_name='notifications', verbose_name="Utilisateur",
    )
    alerte = models.ForeignKey(
        Alerte, on_delete=models.CASCADE, null=True, blank=True,
        related_name='notifications', verbose_name="Alerte",
    )
    type = models.CharField(
        max_length=20, choices=Type.choices,
        default=Type.ALERTE_CREEE, verbose_name="Type",
    )
    titre = models.CharField(max_length=200, verbose_name="Titre")
    message = models.TextField(blank=True, default='', verbose_name="Message")
    niveau = models.CharField(
        max_length=20, choices=Alerte.Niveau.choices,
        default=Alerte.Niveau.INFORMATION, verbose_name="Niveau",
    )
    lue = models.BooleanField(default=False, verbose_name="Lue")
    date_creation = models.DateTimeField(auto_now_add=True)
    date_lecture = models.DateTimeField(null=True, blank=True, verbose_name="Lue le")

    class Meta:
        verbose_name = "Notification"
        verbose_name_plural = "Notifications"
        ordering = ['-date_creation', '-pk']
        indexes = [
            models.Index(fields=['utilisateur', 'lue'], name='notif_user_lue_idx'),
        ]
        constraints = [
            # Anti-spam : une seule notification par utilisateur, alerte et type.
            models.UniqueConstraint(
                fields=['utilisateur', 'alerte', 'type'],
                name='notification_unique_par_alerte_type',
            ),
        ]

    def __str__(self):
        return f'{self.titre} → {self.utilisateur_id}'

    def marquer_lue(self):
        from django.utils import timezone

        if self.lue:
            return False
        self.lue = True
        self.date_lecture = timezone.now()
        self.save(update_fields=['lue', 'date_lecture'])
        return True


class PreferenceNotification(models.Model):
    """Canaux de notification choisis par l'utilisateur (UC-28).

    Les clés globales (`ALERTE_NOTIFICATIONS_*`) restent prioritaires :
    une préférence ne peut pas activer un canal coupé par la configuration.
    """

    utilisateur = models.OneToOneField(
        'accounts.Utilisateur', on_delete=models.CASCADE,
        related_name='preference_notification', verbose_name="Utilisateur",
    )
    in_app = models.BooleanField(default=True, verbose_name="Notifications In-App")
    email = models.BooleanField(
        default=False, verbose_name="Notifications par email",
        help_text="Ignoré si aucun SMTP n'est configuré dans l'environnement.",
    )
    sms = models.BooleanField(
        default=False, verbose_name="Notifications par SMS (Twilio)",
        help_text="Canal préparé mais non activé : Twilio est optionnel.",
    )
    email_destination = models.EmailField(
        blank=True, default='', verbose_name="Adresse email de destination",
        help_text="Vide → l'email de l'utilisateur est utilisé.",
    )
    niveau_min_email = models.CharField(
        max_length=20, choices=Alerte.Niveau.choices,
        default=Alerte.Niveau.MAJEURE, verbose_name="Niveau minimum pour l'email",
    )

    class Meta:
        verbose_name = "Préférence de notification"
        verbose_name_plural = "Préférences de notification"

    def __str__(self):
        return f'Canaux de {self.utilisateur_id}'

    @property
    def adresse_email(self):
        return self.email_destination or getattr(self.utilisateur, 'email', '') or ''
