from django.db import models


class Usine(models.Model):
    nom = models.CharField(max_length=200)
    adresse = models.CharField(max_length=300, blank=True, default='')
    description = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Usine'
        verbose_name_plural = 'Usines'
        ordering = ['nom']

    def __str__(self):
        return self.nom


class Zone(models.Model):
    nom = models.CharField(max_length=200)
    usine = models.ForeignKey(Usine, on_delete=models.CASCADE, related_name='zones')
    description = models.TextField(blank=True, default='')

    class Meta:
        verbose_name = 'Zone'
        verbose_name_plural = 'Zones'
        ordering = ['nom']

    def __str__(self):
        return f'{self.nom} — {self.usine.nom}'


class LigneProduction(models.Model):
    nom = models.CharField(max_length=200)
    zone = models.ForeignKey(Zone, on_delete=models.CASCADE, related_name='lignes')
    description = models.TextField(blank=True, default='')

    class Meta:
        verbose_name = 'Ligne de production'
        verbose_name_plural = 'Lignes de production'
        ordering = ['nom']

    def __str__(self):
        return f'{self.nom} — {self.zone.nom}'


class Machine(models.Model):
    class Statut(models.TextChoices):
        NORMAL = 'NORMAL', 'Normal'
        DEGRADE = 'DEGRADE', 'Dégradé'
        CRITIQUE = 'CRITIQUE', 'Critique'
        HORS_LIGNE = 'HORS_LIGNE', 'Hors ligne'

    nom = models.CharField(max_length=200)
    identifiant_interne = models.CharField(max_length=100, unique=True)
    numero_serie = models.CharField(max_length=100, blank=True, default='')
    marque = models.CharField(max_length=100, blank=True, default='')
    modele = models.CharField(max_length=100, blank=True, default='')
    date_installation = models.DateField(null=True, blank=True)
    position_sur_plan = models.CharField(max_length=200, blank=True, default='')
    statut = models.CharField(
        max_length=20,
        choices=Statut.choices,
        default=Statut.NORMAL
    )
    ligne_production = models.ForeignKey(
        LigneProduction,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='machines'
    )
    photo = models.ImageField(
        upload_to='machines/photos/',
        null=True,
        blank=True
    )
    description = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Machine'
        verbose_name_plural = 'Machines'
        ordering = ['nom']

    def __str__(self):
        return f'{self.nom} ({self.identifiant_interne})'

    @property
    def zone(self):
        return self.ligne_production.zone if self.ligne_production else None

    @property
    def usine(self):
        return self.ligne_production.zone.usine if self.ligne_production and self.ligne_production.zone else None


class Document(models.Model):
    class TypeDocument(models.TextChoices):
        MANUEL = 'MANUEL', 'Manuel'
        FICHE_TECHNIQUE = 'FICHE_TECHNIQUE', 'Fiche technique'
        AUTRE = 'AUTRE', 'Autre'

    machine = models.ForeignKey(Machine, on_delete=models.CASCADE, related_name='documents')
    nom = models.CharField(max_length=200)
    type_document = models.CharField(
        max_length=20,
        choices=TypeDocument.choices,
        default=TypeDocument.AUTRE
    )
    fichier = models.FileField(upload_to='machines/documents/')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Document'
        verbose_name_plural = 'Documents'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.nom} — {self.machine.nom}'


class Composant(models.Model):
    nom = models.CharField(max_length=200)
    machine = models.ForeignKey(Machine, on_delete=models.CASCADE, related_name='composants')
    description = models.TextField(blank=True, default='')
    numero_piece = models.CharField(max_length=100, blank=True, default='')

    class Meta:
        verbose_name = 'Composant'
        verbose_name_plural = 'Composants'
        ordering = ['nom']

    def __str__(self):
        return f'{self.nom} — {self.machine.nom}'


class Sensor(models.Model):
    class SensorType(models.TextChoices):
        TEMPERATURE = 'TEMPERATURE', 'Température'
        VIBRATION = 'VIBRATION', 'Vibration'
        PRESSION = 'PRESSION', 'Pression'
        COURANT = 'COURANT', 'Courant'
        VITESSE_RPM = 'VITESSE_RPM', 'Vitesse (RPM)'
        DEBIT = 'DEBIT', 'Débit'
        NIVEAU_SONORE = 'NIVEAU_SONORE', 'Niveau sonore'

    identifiant = models.CharField(max_length=100, unique=True, verbose_name="Identifiant unique")
    nom = models.CharField(max_length=200, verbose_name="Nom du capteur")
    type_capteur = models.CharField(
        max_length=30,
        choices=SensorType.choices,
        verbose_name="Type de capteur"
    )
    machine = models.ForeignKey(
        Machine,
        on_delete=models.CASCADE,
        related_name='capteurs',
        verbose_name="Machine associée"
    )
    unite = models.CharField(max_length=50, verbose_name="Unité de mesure")
    frequence_mesure = models.IntegerField(
        verbose_name="Fréquence de mesure (secondes)",
        help_text="Fréquence en secondes"
    )
    seuil_min = models.FloatField(verbose_name="Seuil minimum")
    seuil_max = models.FloatField(verbose_name="Seuil maximum")
    actif = models.BooleanField(default=True, verbose_name="Actif")
    description = models.TextField(blank=True, default='', verbose_name="Description")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Capteur'
        verbose_name_plural = 'Capteurs'
        ordering = ['nom']

    def __str__(self):
        return f'{self.nom} ({self.identifiant}) - {self.machine.nom}'

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.seuil_min >= self.seuil_max:
            raise ValidationError("Le seuil minimum doit être inférieur au seuil maximum.")
        if self.frequence_mesure <= 0:
            raise ValidationError("La fréquence de mesure doit être supérieure à 0.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)


class Reading(models.Model):
    sensor = models.ForeignKey(
        Sensor,
        on_delete=models.CASCADE,
        related_name='lectures',
        verbose_name="Capteur"
    )
    valeur = models.FloatField(verbose_name="Valeur mesurée")
    timestamp = models.DateTimeField(verbose_name="Date et heure")
    created_at = models.DateTimeField(auto_now_add=True)
    # Champs pour le prétraitement
    hors_plage = models.BooleanField(default=False, verbose_name="Hors plage (min/max)")
    est_valide = models.BooleanField(default=True, verbose_name="Lecture valide")
    interpolation = models.BooleanField(default=False, verbose_name="Valeur interpolée")

    class Meta:
        verbose_name = 'Lecture de capteur'
        verbose_name_plural = 'Lectures de capteurs'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['sensor', '-timestamp']),
            models.Index(fields=['timestamp']),
        ]

    def __str__(self):
        return f'{self.sensor.identifiant}: {self.valeur} {self.sensor.unite} @ {self.timestamp}'


class InspectionVisuelle(models.Model):
    """Module 4 — Inspection visuelle par IA d'une machine.

    Une inspection associe une image à une machine existante (Module 2) et
    conserve le résultat d'une analyse IA (via `VisionAIService`).
    """

    class StatutAnalyse(models.TextChoices):
        EN_ATTENTE = 'EN_ATTENTE', 'En attente'
        EN_ANALYSE = 'EN_ANALYSE', 'En analyse'
        TERMINEE = 'TERMINEE', 'Terminée'
        ERREUR = 'ERREUR', 'Erreur'

    machine = models.ForeignKey(
        Machine,
        on_delete=models.CASCADE,
        related_name='inspections',
        verbose_name="Machine inspectée",
    )
    image = models.ImageField(
        upload_to='inspections/images/',
        verbose_name="Image inspectée",
    )
    date_inspection = models.DateTimeField(
        auto_now_add=True, verbose_name="Date d'inspection"
    )
    utilisateur = models.ForeignKey(
        'accounts.Utilisateur',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='inspections',
        verbose_name="Utilisateur",
    )
    statut_analyse = models.CharField(
        max_length=20,
        choices=StatutAnalyse.choices,
        default=StatutAnalyse.EN_ATTENTE,
        verbose_name="Statut de l'analyse",
    )
    resultat_analyse = models.JSONField(
        null=True, blank=True, verbose_name="Résultat de l'analyse"
    )
    score_confiance = models.FloatField(
        null=True, blank=True, verbose_name="Score de confiance"
    )
    # Champs de résultat dénormalisés (cahier des charges Module 4) : ils
    # reflètent `resultat_analyse` et facilitent l'affichage, le filtrage et le tri.
    defect_detected = models.BooleanField(
        null=True, blank=True, default=None, verbose_name="Défaut détecté"
    )
    defect_type = models.CharField(
        max_length=50, blank=True, default='', verbose_name="Type de défaut"
    )
    confidence = models.FloatField(
        null=True, blank=True, verbose_name="Score de confiance (0-1)"
    )
    observation = models.TextField(
        blank=True, default='', verbose_name="Observation de l'analyse"
    )
    observations = models.TextField(blank=True, default='', verbose_name="Observations")
    erreur_message = models.TextField(
        blank=True, default='', verbose_name="Message d'erreur"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Inspection visuelle'
        verbose_name_plural = 'Inspections visuelles'
        ordering = ['-date_inspection']
        indexes = [
            models.Index(fields=['machine', '-date_inspection']),
            models.Index(fields=['statut_analyse']),
        ]

    def __str__(self):
        return f'Inspection #{self.pk} — {self.machine.nom} ({self.get_statut_analyse_display()})'


# ── Périmètres d'accès (affectations utilisateur ↔ équipements) ────────────────

class UserScope(models.Model):
    """Affectation d'un utilisateur à un périmètre de la hiérarchie industrielle.

    Modèle explicite (et non un simple FK sur `Utilisateur`) car un utilisateur
    peut avoir **plusieurs** périmètres, à des niveaux différents :

        Opérateur  → Ligne CNC 01, Ligne CNC 02
        Technicien → Zone Usinage, Machine Robot RA-104

    Le niveau cible est déduit du seul champ renseigné :

    * `usine`   → toute l'usine (et zones / lignes / machines descendantes) ;
    * `zone`    → toute la zone (et lignes / machines descendantes) ;
    * `ligne`   → les machines de la ligne ;
    * `machine` → cette machine seule.

    `ADMIN` n'a pas besoin d'affectation : son accès est global.
    Les affectations peuvent être historisées via `date_debut` / `date_fin`.
    """

    class Meta:
        verbose_name = "Périmètre d'accès"
        verbose_name_plural = "Périmètres d'accès"
        ordering = ['utilisateur', 'usine', 'zone', 'ligne', 'machine']
        constraints = [
            # Un seul niveau cible par affectation : évite les périmètres ambigus.
            models.CheckConstraint(
                condition=(
                    models.Q(usine__isnull=False, zone__isnull=True, ligne__isnull=True, machine__isnull=True)
                    | models.Q(usine__isnull=True, zone__isnull=False, ligne__isnull=True, machine__isnull=True)
                    | models.Q(usine__isnull=True, zone__isnull=True, ligne__isnull=False, machine__isnull=True)
                    | models.Q(usine__isnull=True, zone__isnull=True, ligne__isnull=True, machine__isnull=False)
                ),
                name='userscope_exactly_one_target',
            ),
            # Pas d'affectation vide.
            models.CheckConstraint(
                condition=(
                    models.Q(usine__isnull=False)
                    | models.Q(zone__isnull=False)
                    | models.Q(ligne__isnull=False)
                    | models.Q(machine__isnull=False)
                ),
                name='userscope_at_least_one_target',
            ),
        ]
        # Pas de `UniqueConstraint` ici, volontairement : sur PostgreSQL/SQLite
        # les NULL sont distincts, elle n'interdirait donc pas les doublons
        # réels (3 colonnes sur 4 valent NULL pour une affectation sur une
        # ligne). De plus DRF la traduisait en `UniqueTogetherValidator`, ce
        # qui rendait `usine`/`zone`/`ligne`/`machine` obligatoires dans
        # l'API alors qu'ils sont alternatifs. L'unicité est garantie
        # applicativement dans `UserScope.clean()`.

    utilisateur = models.ForeignKey(
        'accounts.Utilisateur',
        on_delete=models.CASCADE,
        related_name='scopes',
        verbose_name="Utilisateur",
    )
    usine = models.ForeignKey(
        Usine, on_delete=models.CASCADE, null=True, blank=True,
        related_name='user_scopes', verbose_name="Usine",
    )
    zone = models.ForeignKey(
        Zone, on_delete=models.CASCADE, null=True, blank=True,
        related_name='user_scopes', verbose_name="Zone",
    )
    ligne = models.ForeignKey(
        LigneProduction, on_delete=models.CASCADE, null=True, blank=True,
        related_name='user_scopes', verbose_name="Ligne de production",
    )
    machine = models.ForeignKey(
        Machine, on_delete=models.CASCADE, null=True, blank=True,
        related_name='user_scopes', verbose_name="Machine",
    )
    actif = models.BooleanField(default=True, verbose_name="Actif")
    date_debut = models.DateTimeField(null=True, blank=True, verbose_name="Date de début")
    date_fin = models.DateTimeField(null=True, blank=True, verbose_name="Date de fin")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        cible = self.usine or self.zone or self.ligne or self.machine
        return f'{self.utilisateur} → {cible}'

    def clean(self):
        """Valide : une seule cible, pas de doublon pour un même utilisateur."""
        from django.core.exceptions import ValidationError

        cibles = [self.usine_id, self.zone_id, self.ligne_id, self.machine_id]
        if sum(1 for c in cibles if c) != 1:
            raise ValidationError(
                "Une affectation doit cibler exactement un niveau : "
                "usine, zone, ligne de production ou machine."
            )

        doublon = UserScope.objects.filter(
            utilisateur=self.utilisateur,
            usine_id=self.usine_id,
            zone_id=self.zone_id,
            ligne_id=self.ligne_id,
            machine_id=self.machine_id,
        ).exclude(pk=self.pk).exists()
        if doublon:
            raise ValidationError("Cette affectation existe déjà pour cet utilisateur.")

    def save(self, *args, **kwargs):
        self.full_clean(exclude=['date_debut', 'date_fin'])
        super().save(*args, **kwargs)

    def est_active(self, now=None):
        """L'affectation est-elle en cours de validité ?"""
        from django.utils import timezone
        now = now or timezone.now()
        if not self.actif:
            return False
        if self.date_debut and self.date_debut > now:
            return False
        if self.date_fin and self.date_fin <= now:
            return False
        return True
