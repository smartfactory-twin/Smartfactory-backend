from django.core.management.base import BaseCommand
from apps.equipements.models import Usine, Zone, LigneProduction, Machine, Composant


class Command(BaseCommand):
    help = "Seed the database with sample equipment data (Usine, Zones, Lignes, Machines, Composants)"

    def handle(self, *args, **options):
        # ── Usine ─────────────────────────────────────────────────────────────
        usine, created = Usine.objects.get_or_create(
            nom='Usine Alger',
            defaults={'adresse': 'Zone Industrielle, Alger', 'description': 'Usine principale Alger'},
        )
        self.stdout.write(f"{'Créée' if created else 'Existante'} : Usine '{usine.nom}'")

        # ── Zones (2) ─────────────────────────────────────────────────────────
        zones_data = [
            {'nom': 'Zone A – Assemblage', 'description': 'Zone dédiée à l'assemblage'},
            {'nom': 'Zone B – Peinture',   'description': 'Zone dédiée à la peinture'},
        ]
        zones = []
        for zd in zones_data:
            zone, created = Zone.objects.get_or_create(
                nom=zd['nom'],
                usine=usine,
                defaults={'description': zd['description']},
            )
            zones.append(zone)
            self.stdout.write(f"  {'Créée' if created else 'Existante'} : Zone '{zone.nom}'")

        # ── Lignes (2 par zone) ────────────────────────────────────────────────
        lignes_data = [
            ('Ligne A1', 'Première ligne assemblage'),
            ('Ligne A2', 'Deuxième ligne assemblage'),
            ('Ligne B1', 'Première ligne peinture'),
            ('Ligne B2', 'Deuxième ligne peinture'),
        ]
        lignes = []
        for idx, zone in enumerate(zones):
            for j in range(2):
                nom, desc = lignes_data[idx * 2 + j]
                ligne, created = LigneProduction.objects.get_or_create(
                    nom=nom,
                    zone=zone,
                    defaults={'description': desc},
                )
                lignes.append(ligne)
                self.stdout.write(f"    {'Créée' if created else 'Existante'} : Ligne '{ligne.nom}'")

        # ── Machines (3 par ligne) + Composants (2 par machine) ───────────────
        machine_counter = 1
        for ligne in lignes:
            for k in range(1, 4):
                identifiant = f'MCH-{machine_counter:03d}'
                machine, created = Machine.objects.get_or_create(
                    identifiant_interne=identifiant,
                    defaults={
                        'nom': f'Machine {machine_counter}',
                        'numero_serie': f'SN-{machine_counter:04d}',
                        'marque': 'SmartTech',
                        'modele': f'ST-{1000 + machine_counter}',
                        'statut': Machine.Statut.NORMAL,
                        'ligne_production': ligne,
                        'description': f'Machine {machine_counter} sur {ligne.nom}',
                    },
                )
                self.stdout.write(
                    f"      {'Créée' if created else 'Existante'} : Machine '{machine.nom}' ({identifiant})"
                )

                # 2 composants par machine
                for c in range(1, 3):
                    comp, comp_created = Composant.objects.get_or_create(
                        nom=f'Composant {c} – {machine.nom}',
                        machine=machine,
                        defaults={
                            'numero_piece': f'PC-{machine_counter:03d}-{c}',
                            'description': f'Composant {c} de la machine {machine.nom}',
                        },
                    )
                    self.stdout.write(
                        f"        {'Créé' if comp_created else 'Existant'} : Composant '{comp.nom}'"
                    )

                machine_counter += 1

        self.stdout.write(self.style.SUCCESS(
            f"\nSeed terminé : 1 usine, {len(zones)} zones, {len(lignes)} lignes, "
            f"{machine_counter - 1} machines, {(machine_counter - 1) * 2} composants."
        ))
