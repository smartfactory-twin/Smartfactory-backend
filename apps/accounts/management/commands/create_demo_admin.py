from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.conf import settings

User = get_user_model()


class Command(BaseCommand):
    help = 'Crée un superuser ADMIN de démonstration.'

    def handle(self, *args, **options):
        email = settings.DEMO_ADMIN_EMAIL
        password = settings.DEMO_ADMIN_PASSWORD

        if User.objects.filter(email=email).exists():
            user = User.objects.get(email=email)
            if user.must_reset_password:
                if not password:
                    raise CommandError('DEMO_ADMIN_PASSWORD doit être défini pour initialiser le compte administrateur.')
                # Ne pas rechiffrer le mot de passe à chaque redémarrage : cela
                # invaliderait un jeton de premier accès déjà ouvert.
                if not user.check_password(password):
                    user.set_password(password)
                    user.save(update_fields=['password'])
                    self.stdout.write(self.style.SUCCESS(f'Compte administrateur initialisé : {email}'))
                else:
                    self.stdout.write(self.style.WARNING(f'Compte administrateur déjà initialisé : {email}'))
            else:
                self.stdout.write(self.style.WARNING(f'Un utilisateur avec l\'email {email} existe déjà.'))
            return

        if User.objects.filter(is_superuser=True).exists():
            self.stdout.write(self.style.WARNING(
                'Un compte super-administrateur existe déjà ; aucun compte de démonstration supplémentaire n’a été créé.'
            ))
            return

        if not password:
            raise CommandError(
                'DEMO_ADMIN_PASSWORD doit être défini dans le fichier .env pour créer le compte administrateur.'
            )

        User.objects.create_superuser(
            email=email,
            password=password,
            nom='Admin',
            prenom='Demo',
            role=User.Role.ADMIN,
            must_reset_password=False,
        )
        self.stdout.write(self.style.SUCCESS(f'Superuser ADMIN créé : {email}'))
