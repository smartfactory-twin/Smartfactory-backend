import getpass

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model

User = get_user_model()


class Command(BaseCommand):
    """Crée un utilisateur ADMIN (superuser) avec un email personnalisé."""

    help = 'Crée un utilisateur ADMIN (superuser) avec un email personnalisé.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--email', type=str, required=True,
            help='Adresse email de l\'admin',
        )
        parser.add_argument(
            '--password', type=str, default='',
            help='Mot de passe (demandé en interactif si omis)',
        )
        parser.add_argument('--nom', type=str, default='Admin', help='Nom')
        parser.add_argument('--prenom', type=str, default='Super', help='Prénom')

    def handle(self, *args, **options):
        email = options['email'].lower()
        password = options['password'] or getpass.getpass(prompt='Mot de passe: ')
        if not password:
            raise CommandError('Le mot de passe est obligatoire.')

        if User.objects.filter(email=email).exists():
            self.stdout.write(
                self.style.WARNING(f'Un utilisateur avec l\'email {email} existe déjà.')
            )
            return

        User.objects.create_superuser(
            email=email,
            password=password,
            nom=options['nom'],
            prenom=options['prenom'],
            role=User.Role.ADMIN,
        )
        self.stdout.write(self.style.SUCCESS(f'Admin créé : {email}'))
