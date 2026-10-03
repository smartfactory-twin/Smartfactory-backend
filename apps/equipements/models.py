from django.db import models

class Usine(models.Model):
    nom = models.CharField(max_length=200)
    adresse = models.CharField(max_length=300, blank=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        verbose_name = 'Usine'
        ordering = ['nom']
    def __str__(self): return self.nom

class Zone(models.Model):
    nom = models.CharField(max_length=200)
    usine = models.ForeignKey(Usine, on_delete=models.CASCADE, related_name='zones')
    description = models.TextField(blank=True)
    class Meta:
        verbose_name = 'Zone'
        ordering = ['nom']
    def __str__(self): return f'{self.nom} — {self.usine.nom}'

class LigneProduction(models.Model):
    nom = models.CharField(max_length=200)
    zone = models.ForeignKey(Zone, on_delete=models.CASCADE, related_name='lignes')
    description = models.TextField(blank=True)
    class Meta:
        verbose_name = 'Ligne de production'
        ordering = ['nom']
    def __str__(self): return f'{self.nom} — {self.zone.nom}'

class Machine(models.Model):
    class Statut(models.TextChoices):
        NORMAL     = 'NORMAL',     'Normal'
        DEGRADE    = 'DEGRADE',    'Dégradé'
        CRITIQUE   = 'CRITIQUE',   'Critique'
        HORS_LIGNE = 'HORS_LIGNE', 'Hors ligne'
    nom                 = models.CharField(max_length=200)
    identifiant_interne = models.CharField(max_length=100, unique=True)
    numero_serie        = models.CharField(max_length=100, blank=True)
    marque              = models.CharField(max_length=100, blank=True)
    modele              = models.CharField(max_length=100, blank=True)
    date_installation   = models.DateField(null=True, blank=True)
    position_sur_plan   = models.CharField(max_length=100, blank=True)
    statut              = models.CharField(max_length=20, choices=Statut.choices, default=Statut.NORMAL)
    ligne_production    = models.ForeignKey(LigneProduction, on_delete=models.SET_NULL, null=True, blank=True, related_name='machines')
    photo               = models.ImageField(upload_to='machines/photos/', null=True, blank=True)
    description         = models.TextField(blank=True)
    created_at          = models.DateTimeField(auto_now_add=True)
    updated_at          = models.DateTimeField(auto_now=True)
    class Meta:
        verbose_name = 'Machine'
        ordering = ['nom']
    def __str__(self): return f'{self.nom} ({self.identifiant_interne})'
    @property
    def zone(self):
        return self.ligne_production.zone if self.ligne_production else None
    @property
    def usine(self):
        z = self.zone
        return z.usine if z else None

class Document(models.Model):
    class TypeDocument(models.TextChoices):
        MANUEL          = 'MANUEL',          'Manuel'
        FICHE_TECHNIQUE = 'FICHE_TECHNIQUE', 'Fiche technique'
        AUTRE           = 'AUTRE',           'Autre'
    machine       = models.ForeignKey(Machine, on_delete=models.CASCADE, related_name='documents')
    nom           = models.CharField(max_length=200)
    type_document = models.CharField(max_length=30, choices=TypeDocument.choices, default=TypeDocument.AUTRE)
    fichier       = models.FileField(upload_to='machines/documents/')
    created_at    = models.DateTimeField(auto_now_add=True)
    class Meta:
        verbose_name = 'Document'
    def __str__(self): return self.nom

class Composant(models.Model):
    nom          = models.CharField(max_length=200)
    machine      = models.ForeignKey(Machine, on_delete=models.CASCADE, related_name='composants')
    description  = models.TextField(blank=True)
    numero_piece = models.CharField(max_length=100, blank=True)
    class Meta:
        verbose_name = 'Composant'
        ordering = ['nom']
    def __str__(self): return f'{self.nom} — {self.machine.nom}'
