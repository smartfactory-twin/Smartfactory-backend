from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """
    Modèle utilisateur personnalisé.
    Connexion par EMAIL (pas username).
    3 rôles : Administrateur, Technicien Terrain, Opérateur.
    """

    class Role(models.TextChoices):
        ADMIN      = 'ADMIN',      'Administrateur'
        TECHNICIAN = 'TECHNICIAN', 'Technicien Terrain'
        OPERATOR   = 'OPERATOR',   'Opérateur'

    email = models.EmailField(
        unique=True,
        verbose_name='Adresse email'
    )
    username = models.CharField(
        max_length=150,
        unique=True,
        verbose_name="Nom d'utilisateur"
    )
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.OPERATOR,
        verbose_name='Rôle'
    )
    phone = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        verbose_name='Téléphone'
    )
    avatar = models.ImageField(
        upload_to='avatars/',
        blank=True,
        null=True,
        verbose_name='Photo de profil'
    )

    # L'email est l'identifiant principal
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username', 'first_name', 'last_name']

    class Meta:
        verbose_name = 'Utilisateur'
        verbose_name_plural = 'Utilisateurs'
        ordering = ['-date_joined']

    def __str__(self):
        return f'{self.get_full_name()} — {self.get_role_display()}'

    # ── Helpers de rôle ───────────────────────────────────────────────────────
    @property
    def is_admin(self):
        return self.role == self.Role.ADMIN

    @property
    def is_technician(self):
        return self.role == self.Role.TECHNICIAN

    @property
    def is_operator(self):
        return self.role == self.Role.OPERATOR
