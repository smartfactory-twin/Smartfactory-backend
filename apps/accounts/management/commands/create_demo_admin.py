from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.conf import settings

User = get_user_model()


class Command(BaseCommand):
    help = 'Crée un superuser ADMIN de démonstration.'

    def handle(self, *args, **options):
        email = settings.DEMO_ADMIN_EMAIL
        password = settings.DEMO_ADMIN_PASSWORD

        if User.objects.filter(email=email).exists():
            self.stdout.write(self.style.WARNING(f'Un utilisateur avec l\'email {email} existe déjà.'))
            return

        User.objects.create_superuser(
            email=email,
            password=password,
            nom='Admin',
            prenom='Demo',
            role=User.Role.ADMIN,
        )
        self.stdout.write(self.style.SUCCESS(f'Superuser ADMIN créé : {email}'))
