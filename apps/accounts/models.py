from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models


class UtilisateurManager(BaseUserManager):

    def create_user(self, email: str, password: str, **extra_fields):
        if not email:
            raise ValueError("L'adresse email est obligatoire.")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email: str, password: str, **extra_fields):
        extra_fields.setdefault('role', Utilisateur.Role.ADMIN)
        extra_fields.setdefault('actif', True)
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(email, password, **extra_fields)


class Utilisateur(AbstractBaseUser, PermissionsMixin):
    class Role(models.TextChoices):
        ADMIN = 'ADMIN', 'Administrateur'
        TECHNICIEN = 'TECHNICIEN', 'Technicien'
        OPERATEUR = 'OPERATEUR', 'Opérateur'

    nom = models.CharField(max_length=100, verbose_name='Nom')
    prenom = models.CharField(max_length=100, verbose_name='Prénom')
    email = models.EmailField(unique=True, verbose_name='Adresse email')
    google_sub = models.CharField(
        max_length=255, unique=True, null=True, blank=True,
        editable=False, verbose_name='Identifiant Google',
    )
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.OPERATEUR,
        verbose_name='Rôle'
    )
    actif = models.BooleanField(default=True, verbose_name='Actif')
    must_reset_password = models.BooleanField(
        default=False, verbose_name='Doit réinitialiser son mot de passe'
    )
    telephone = models.CharField(
        max_length=20, blank=True, default='', verbose_name='Numéro de téléphone'
    )
    photo = models.ImageField(
        upload_to='profiles/', null=True, blank=True, verbose_name='Photo de profil'
    )

    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)
    last_login = models.DateTimeField(null=True, blank=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['nom', 'prenom']

    objects = UtilisateurManager()

    class Meta:
        verbose_name = 'Utilisateur'
        verbose_name_plural = 'Utilisateurs'
        ordering = ['-date_joined']

    def __str__(self):
        return f'{self.prenom} {self.nom} — {self.get_role_display()}'

    @property
    def is_active(self):
        return self.actif

    @property
    def is_admin(self):
        return self.role == self.Role.ADMIN

    @property
    def is_technicien(self):
        return self.role == self.Role.TECHNICIEN

    @property
    def is_operateur(self):
        return self.role == self.Role.OPERATEUR


class AuditLog(models.Model):

    acteur = models.ForeignKey(
        'accounts.Utilisateur', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='audit_events', verbose_name='Acteur',
    )
    acteur_email = models.EmailField(blank=True, default='', verbose_name='E-mail acteur')
    acteur_role = models.CharField(max_length=20, blank=True, default='', verbose_name='Rôle acteur')
    action = models.CharField(max_length=255, verbose_name='Action')
    methode = models.CharField(max_length=10, verbose_name='Méthode HTTP')
    chemin = models.CharField(max_length=512, verbose_name='Chemin API')
    code_http = models.PositiveSmallIntegerField(verbose_name='Code HTTP')
    adresse_ip = models.GenericIPAddressField(null=True, blank=True, verbose_name='Adresse IP')
    user_agent = models.CharField(max_length=512, blank=True, default='')
    details = models.JSONField(default=dict, blank=True)
    cree_le = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Date')

    class Meta:
        ordering = ['-cree_le', '-pk']
        indexes = [models.Index(fields=['action', '-cree_le'], name='accounts_audit_action_dt_idx')]
        verbose_name = "Événement d'audit"
        verbose_name_plural = "Journal d'audit"

    def __str__(self):
        return f'{self.action} — {self.acteur_email or "anonyme"} — {self.cree_le:%Y-%m-%d %H:%M:%S}'

    @property
    def is_temp_password_expired(self):  
        if self.must_reset_password and self.date_joined:
            from django.utils import timezone
            from datetime import timedelta
            return (timezone.now() - self.date_joined) > timedelta(hours=48)
        return False


class VocalCommand(models.Model):
    utilisateur = models.ForeignKey(
        'accounts.Utilisateur', on_delete=models.CASCADE, related_name='commandes_vocales'
    )
    texte = models.CharField(max_length=1000)
    intention = models.CharField(max_length=80, blank=True, default='')
    confiance = models.FloatField(null=True, blank=True)
    resultat = models.CharField(max_length=1000, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-pk']
        indexes = [models.Index(fields=['utilisateur', '-created_at'])]

    def __str__(self):
        return f'{self.utilisateur_id} — {self.intention} — {self.created_at:%Y-%m-%d %H:%M}'

