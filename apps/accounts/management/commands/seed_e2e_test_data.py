import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import Utilisateur
from apps.equipements.models import LigneProduction, Machine, Usine, Zone


class Command(BaseCommand):
    help = 'Seed only the dedicated isolated E2E SQLite database.'

    def handle(self, *args, **options):
        engine = settings.DATABASES['default']['ENGINE']
        db_name = str(settings.DATABASES['default']['NAME']).lower()
        password = os.environ.get('E2E_TEST_PASSWORD', '')
        if engine != 'django.db.backends.sqlite3' or 'smartfactory-e2e-' not in db_name:
            raise CommandError('Refusing to seed a database that is not the isolated E2E SQLite database.')
        if len(password) < 16:
            raise CommandError('Set a temporary E2E_TEST_PASSWORD of at least 16 characters.')

        for role, email, first_name in (
            ('ADMIN', 'admin.e2e@example.test', 'Admin'),
            ('TECHNICIEN', 'technicien.e2e@example.test', 'Technicien'),
            ('OPERATEUR', 'operateur.e2e@example.test', 'Operateur'),
        ):
            user, _ = Utilisateur.objects.get_or_create(
                email=email,
                defaults={'nom': 'E2E', 'prenom': first_name, 'role': role},
            )
            user.nom = 'E2E'
            user.prenom = first_name
            user.role = role
            user.actif = True
            user.must_reset_password = False
            user.set_password(password)
            user.save()

        usine, _ = Usine.objects.get_or_create(nom='Usine E2E isolée')
        zone, _ = Zone.objects.get_or_create(nom='Zone E2E', usine=usine)
        ligne, _ = LigneProduction.objects.get_or_create(nom='Ligne E2E', zone=zone)
        Machine.objects.get_or_create(
            identifiant_interne='E2E-SEED-001',
            defaults={'nom': 'Machine témoin E2E', 'ligne_production': ligne},
        )
        self.stdout.write(self.style.SUCCESS('Seed E2E isolated database ready.'))
