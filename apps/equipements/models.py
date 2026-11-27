from django.db import models
from django.utils import timezone


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
    class TypeEquipement(models.TextChoices):
        COMPRESSEUR = 'COMPRESSEUR', 'Compresseur'
        POMPE = 'POMPE', 'Pompe'
        MOTEUR = 'MOTEUR', 'Moteur'
        CONVOYEUR = 'CONVOYEUR', 'Convoyeur'
        TURBINE = 'TURBINE', 'Turbine'
        PRESSE = 'PRESSE', 'Presse'
        AUTRE = 'AUTRE', 'Autre'

    class Statut(models.TextChoices):
        NORMAL = 'NORMAL', 'Normal'
        DEGRADE = 'DEGRADE', 'Dégradé'
        CRITIQUE = 'CRITIQUE', 'Critique'
        HORS_LIGNE = 'HORS_LIGNE', 'Hors ligne'

    nom = models.CharField(max_length=200)
    identifiant_interne = models.CharField(max_length=100, unique=True)
    numero_serie = models.CharField(max_length=100, blank=True, default='')
    type_equipement = models.CharField(
        max_length=20,
        choices=TypeEquipement.choices,
        blank=True,
        default='',
    )
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
    class SensorRole(models.TextChoices):
        TEMPERATURE = 'temperature', 'Température'
        VIBRATION = 'vibration', 'Vibration'
        PRESSURE = 'pressure', 'Pression'
        FLOW = 'flow', 'Débit'
        CURRENT = 'current', 'Courant'
        SPEED = 'speed', 'Vitesse'
        OTHER = 'other', 'Autre'

    class Criticality(models.TextChoices):
        LOW = 'low', 'Faible'
        MEDIUM = 'medium', 'Moyenne'
        HIGH = 'high', 'Élevée'

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
        help_text="Fréquence en secondes", null=True, blank=True
    )
    seuil_min = models.FloatField(verbose_name="Seuil minimum", null=True, blank=True)
    seuil_max = models.FloatField(verbose_name="Seuil maximum", null=True, blank=True)
    sensor_role = models.CharField(max_length=20, choices=SensorRole.choices, default=SensorRole.OTHER)
    nominal_min = models.FloatField(null=True, blank=True)
    nominal_max = models.FloatField(null=True, blank=True)
    criticality = models.CharField(max_length=10, choices=Criticality.choices, default=Criticality.LOW)
    is_ai_eligible = models.BooleanField(default=False)
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
        errors = {}
        if self.seuil_min is not None and self.seuil_max is not None and self.seuil_min >= self.seuil_max:
            errors['seuil_min'] = "Le seuil minimum doit être inférieur au seuil maximum."
        if self.frequence_mesure is not None and self.frequence_mesure <= 0:
            errors['frequence_mesure'] = "La fréquence de mesure doit être supérieure à 0."
        if (self.nominal_min is None) != (self.nominal_max is None):
            errors['nominal_min'] = "Les deux bornes nominales doivent être renseignées ensemble."
        elif self.nominal_min is not None and self.nominal_max is not None:
            if self.nominal_min >= self.nominal_max:
                errors['nominal_min'] = "La borne nominale minimum doit être inférieure à la borne maximum."
            if self.seuil_min is not None and self.nominal_min < self.seuil_min:
                errors['nominal_min'] = "La plage nominale doit rester au-dessus du seuil d'alerte minimum."
            if self.seuil_max is not None and self.nominal_max > self.seuil_max:
                errors['nominal_max'] = "La plage nominale doit rester sous le seuil d'alerte maximum."
        if self.sensor_role != self.SensorRole.OTHER:
            unit = (self.unite or '').strip().lower().replace('°', '')
            compatible = {
                self.SensorRole.TEMPERATURE: {'c', 'k', 'f', 'celsius', 'kelvin', 'fahrenheit'},
                self.SensorRole.VIBRATION: {'mm/s', 'm/s', 'mm/s²', 'm/s²', 'g'},
                self.SensorRole.PRESSURE: {'pa', 'kpa', 'mpa', 'bar', 'psi'},
                self.SensorRole.FLOW: {'l/min', 'l/s', 'm³/h', 'm3/h', 'm³/s', 'm3/s'},
                self.SensorRole.CURRENT: {'a', 'ma'},
                self.SensorRole.SPEED: {'rpm', 'tr/min', 'm/s'},
            }
            if unit not in compatible.get(self.sensor_role, set()):
                errors['unite'] = f"Unité '{self.unite}' incompatible ou non reconnue pour le rôle '{self.sensor_role}'."
        if self.is_ai_eligible and self.sensor_role == self.SensorRole.OTHER:
            errors['is_ai_eligible'] = "Un capteur de rôle 'other' ne peut pas être éligible à l'IA."
        if self.is_ai_eligible and (self.nominal_min is None or self.nominal_max is None):
            errors['is_ai_eligible'] = "Pour être éligible à l'IA, renseignez nominal_min et nominal_max."
        if errors:
            raise ValidationError(errors)

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
   
    class StatutAnalyse(models.TextChoices):
        EN_ATTENTE = 'EN_ATTENTE', 'En attente'
        EN_ANALYSE = 'EN_ANALYSE', 'En analyse'
        TERMINEE = 'TERMINEE', 'Terminée'
        ERREUR = 'ERREUR', 'Erreur'

    class TypeMedia(models.TextChoices):
        IMAGE = 'IMAGE', 'Image'
        VIDEO = 'VIDEO', 'Vidéo'

    machine = models.ForeignKey(
        Machine,
        on_delete=models.CASCADE,
        related_name='inspections',
        verbose_name="Machine inspectée",
    )
    # FileField conserve la compatibilité de l'API `image` tout en permettant
    # les clips MP4 demandés pour la galerie d'inspection.
    image = models.FileField(
        upload_to='inspections/images/',
        blank=True,
        default='',
        verbose_name="Image inspectée",
    )
    media_type = models.CharField(
        max_length=8,
        choices=TypeMedia.choices,
        default=TypeMedia.IMAGE,
        verbose_name="Type de média",
    )
    image_annotee = models.FileField(
        upload_to='inspections/annotated/',
        blank=True,
        default='',
        verbose_name="Image annotée",
    )
    annotations = models.JSONField(
        blank=True,
        default=list,
        verbose_name="Annotations visuelles",
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


#  Périmètres d'accès 

class UserScope(models.Model):

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
        
        from django.utils import timezone
        now = now or timezone.now()
        if not self.actif:
            return False
        if self.date_debut and self.date_debut > now:
            return False
        if self.date_fin and self.date_fin <= now:
            return False
        return True


class OrdreTravail(models.Model):
    
    class Type(models.TextChoices):
        CORRECTIVE = 'Corrective', 'Corrective'
        PREVENTIVE = 'Préventive', 'Préventive'
        INSPECTION = 'Inspection', 'Inspection'

    class Priorite(models.TextChoices):
        HAUTE = 'Haute', 'Haute'
        MOYENNE = 'Moyenne', 'Moyenne'
        BASSE = 'Basse', 'Basse'

    class Statut(models.TextChoices):
        CREE = 'Créé', 'Créé'
        ASSIGNE = 'Assigné', 'Assigné'
        EN_COURS = 'En cours', 'En cours'
        ATTENTE_PIECES = 'En attente pièces', 'En attente pièces'
        RAPPORT_DEPOSE = 'Rapport déposé', 'Rapport déposé'
        VALIDE = 'Validé', 'Validé'
        CLOTURE = 'Clôturé', 'Clôturé'

    machine = models.ForeignKey(Machine, on_delete=models.CASCADE, related_name='ordres_travail')
    type_ordre = models.CharField(max_length=20, choices=Type.choices, default=Type.CORRECTIVE)
    priorite = models.CharField(max_length=10, choices=Priorite.choices, default=Priorite.MOYENNE)
    titre = models.CharField(max_length=300)
    assigne = models.CharField(max_length=150, blank=True, default='')
    statut = models.CharField(max_length=30, choices=Statut.choices, default=Statut.CREE)
    echeance = models.DateTimeField(null=True, blank=True)
    from_alert = models.PositiveIntegerField(null=True, blank=True)
    historique = models.JSONField(default=list, blank=True)
    rapport = models.JSONField(null=True, blank=True)
    cree_par = models.ForeignKey(
        'accounts.Utilisateur', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='ordres_travail_crees',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Ordre de travail'
        verbose_name_plural = 'Ordres de travail'
        ordering = ['-created_at', '-pk']

    def __str__(self):
        return f'OT {self.pk} — {self.machine.nom} ({self.statut})'


class MaintenanceRecurrente(models.Model):
   
    machine = models.ForeignKey(Machine, on_delete=models.CASCADE, related_name='maintenances_recurrentes')
    titre = models.CharField(max_length=200)
    frequence_jours = models.PositiveIntegerField(default=30)
    date_debut = models.DateField(default=timezone.localdate)
    cree_par = models.ForeignKey(
        'accounts.Utilisateur', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='maintenances_recurrentes_creees',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Maintenance préventive récurrente'
        verbose_name_plural = 'Maintenances préventives récurrentes'
        ordering = ['date_debut', 'pk']

    def __str__(self):
        return f'{self.titre} — {self.machine.nom} (tous les {self.frequence_jours} jours)'
