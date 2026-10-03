from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models


class UtilisateurManager(BaseUserManager):
    """Manager personnalisé pour le modèle Utilisateur."""

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
    """
    Modèle utilisateur personnalisé pour SmartFactory Twin.
    Connexion par EMAIL (pas username).
    3 rôles : ADMIN, TECHNICIEN, OPERATEUR.
    """

    class Role(models.TextChoices):
        ADMIN = 'ADMIN', 'Administrateur'
        TECHNICIEN = 'TECHNICIEN', 'Technicien'
        OPERATEUR = 'OPERATEUR', 'Opérateur'

    nom = models.CharField(max_length=100, verbose_name='Nom')
    prenom = models.CharField(max_length=100, verbose_name='Prénom')
    email = models.EmailField(unique=True, verbose_name='Adresse email')
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.OPERATEUR,
        verbose_name='Rôle'
    )
    actif = models.BooleanField(default=True, verbose_name='Actif')

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
