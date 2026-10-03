import pytest
import io
import csv
from rest_framework.test import APIClient
from apps.accounts.models import Utilisateur
from apps.equipements.models import Usine, Zone, LigneProduction, Machine, Composant


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def admin_user(db):
    return Utilisateur.objects.create_user(
        email='admin@smartfactory.com', password='Admin@123!', role='ADMIN',
        nom='Admin', prenom='User'
    )


@pytest.fixture
def tech_user(db):
    return Utilisateur.objects.create_user(
        email='tech@smartfactory.com', password='Tech@123!', role='TECHNICIEN',
        nom='Tech', prenom='User'
    )


@pytest.fixture
def op_user(db):
    return Utilisateur.objects.create_user(
        email='op@smartfactory.com', password='Op@123!', role='OPERATEUR',
        nom='Op', prenom='User'
    )


def make_hierarchy_csv(rows, fieldnames=None):
    output = io.StringIO()
    if fieldnames is None:
        fieldnames = [
            'usine_nom', 'usine_adresse', 'usine_description',
            'zone_nom', 'zone_description',
            'ligne_nom', 'ligne_description',
            'machine_identifiant', 'machine_nom', 'machine_numero_serie',
            'machine_marque', 'machine_modele', 'machine_date_installation',
            'machine_statut', 'machine_description',
            'composant_nom', 'composant_numero_piece', 'composant_description'
        ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    output.seek(0)
    file_bytes = io.BytesIO(output.read().encode('utf-8'))
    file_bytes.name = 'hierarchie_test.csv'
    return file_bytes


@pytest.mark.django_db
class TestHierarchyCSVExport:
    def test_export_csv_empty_db(self, api_client, admin_user):
        api_client.force_authenticate(admin_user)
        r = api_client.get('/api/equipements/usines/export_csv/')
        assert r.status_code == 200
        assert r['Content-Type'] == 'text/csv; charset=utf-8'
        assert 'smartfactory_hierarchie.csv' in r['Content-Disposition']

    def test_export_csv_full_tree(self, api_client, admin_user):
        u = Usine.objects.create(nom='Usine Nord', adresse='Lille')
        z = Zone.objects.create(nom='Zone Usinage', usine=u)
        l = LigneProduction.objects.create(nom='Ligne CNC', zone=z)
        m = Machine.objects.create(nom='Fraiseuse CNC', identifiant_interne='CNC-001', ligne_production=l)
        c1 = Composant.objects.create(nom='Broche', machine=m, numero_piece='BR-01')
        c2 = Composant.objects.create(nom='Moteur axe X', machine=m, numero_piece='MOT-X')

        api_client.force_authenticate(admin_user)
        r = api_client.get('/api/equipements/usines/export_csv/')
        assert r.status_code == 200
        content = r.content.decode('utf-8-sig')
        assert 'Usine Nord' in content
        assert 'Zone Usinage' in content
        assert 'Ligne CNC' in content
        assert 'CNC-001' in content
        assert 'Broche' in content
        assert 'Moteur axe X' in content

    def test_export_csv_technicien_forbidden(self, api_client, tech_user):
        api_client.force_authenticate(tech_user)
        r = api_client.get('/api/equipements/usines/export_csv/')
        assert r.status_code == 403

    def test_export_csv_operateur_forbidden(self, api_client, op_user):
        api_client.force_authenticate(op_user)
        r = api_client.get('/api/equipements/usines/export_csv/')
        assert r.status_code == 403


@pytest.mark.django_db
class TestHierarchyCSVPreview:
    def test_preview_valid_csv(self, api_client, admin_user):
        rows = [
            {
                'usine_nom': 'Usine Sud',
                'usine_adresse': 'Marseille',
                'zone_nom': 'Zone Emboutissage',
                'ligne_nom': 'Ligne Presse',
                'machine_identifiant': 'PRS-001',
                'machine_nom': 'Presse Hydraulique 50T',
                'machine_statut': 'NORMAL',
                'machine_date_installation': '2024-05-10',
                'composant_nom': 'Vérin',
                'composant_numero_piece': 'VRN-50',
            },
            {
                'usine_nom': 'Usine Sud',
                'usine_adresse': 'Marseille',
                'zone_nom': 'Zone Emboutissage',
                'ligne_nom': 'Ligne Presse',
                'machine_identifiant': 'PRS-001',
                'machine_nom': 'Presse Hydraulique 50T',
                'machine_statut': 'NORMAL',
                'machine_date_installation': '2024-05-10',
                'composant_nom': 'Pompe huile',
                'composant_numero_piece': 'PMP-10',
            },
        ]
        csv_file = make_hierarchy_csv(rows)
        api_client.force_authenticate(admin_user)
        r = api_client.post('/api/equipements/usines/preview_csv/', {'file': csv_file}, format='multipart')

        assert r.status_code == 200
        data = r.data
        assert data['valid_rows_count'] == 2
        assert data['invalid_rows_count'] == 0
        assert data['summary']['usines_count'] == 1
        assert data['summary']['zones_count'] == 1
        assert data['summary']['lignes_count'] == 1
        assert data['summary']['machines_count'] == 1
        assert data['summary']['composants_count'] == 2

    def test_preview_with_validation_errors(self, api_client, admin_user):
        rows = [
            {
                'usine_nom': '',  # missing usine
                'zone_nom': 'Zone Test',
            },
            {
                'usine_nom': 'Usine Test',
                'zone_nom': 'Zone A',
                'ligne_nom': 'Ligne 1',
                'machine_nom': 'Machine sans ID',  # missing machine_identifiant
            },
            {
                'usine_nom': 'Usine Test',
                'zone_nom': 'Zone A',
                'ligne_nom': 'Ligne 1',
                'machine_identifiant': 'M-01',
                'machine_statut': 'INVALID_STATUS',
                'machine_date_installation': 'invalid-date',
            }
        ]
        csv_file = make_hierarchy_csv(rows)
        api_client.force_authenticate(admin_user)
        r = api_client.post('/api/equipements/usines/preview_csv/', {'file': csv_file}, format='multipart')

        assert r.status_code == 200
        data = r.data
        assert len(data['errors']) >= 3
        assert data['invalid_rows_count'] == 3


@pytest.mark.django_db
class TestHierarchyCSVImport:
    def test_import_creates_complete_tree_without_duplicates(self, api_client, admin_user):
        rows = [
            {
                'usine_nom': 'Usine Atlas',
                'usine_adresse': 'Casablanca',
                'usine_description': 'Site principal',
                'zone_nom': 'Zone Assemblage',
                'zone_description': 'Atelier 1',
                'ligne_nom': 'Ligne Robot',
                'ligne_description': 'Ligne automatisée',
                'machine_identifiant': 'ROB-01',
                'machine_nom': 'Robot Soudeur',
                'machine_numero_serie': 'SN-9988',
                'machine_marque': 'Kuka',
                'machine_modele': 'KR-6',
                'machine_date_installation': '2023-11-20',
                'machine_statut': 'NORMAL',
                'composant_nom': 'Bras articulé',
                'composant_numero_piece': 'BA-01',
            },
            {
                'usine_nom': 'Usine Atlas',
                'usine_adresse': 'Casablanca',
                'zone_nom': 'Zone Assemblage',
                'ligne_nom': 'Ligne Robot',
                'machine_identifiant': 'ROB-01',
                'machine_nom': 'Robot Soudeur',
                'composant_nom': 'Torche de soudage',
                'composant_numero_piece': 'TS-02',
            },
            {
                'usine_nom': 'Usine Atlas',
                'zone_nom': 'Zone Assemblage',
                'ligne_nom': 'Ligne Robot 2',
                'machine_identifiant': 'ROB-02',
                'machine_nom': 'Robot Peintre',
                'machine_statut': 'DEGRADE',
            }
        ]
        csv_file = make_hierarchy_csv(rows)
        api_client.force_authenticate(admin_user)
        r = api_client.post('/api/equipements/usines/import_csv/', {'file': csv_file}, format='multipart')

        assert r.status_code == 200
        assert Usine.objects.filter(nom='Usine Atlas').count() == 1
        assert Zone.objects.filter(nom='Zone Assemblage').count() == 1
        assert LigneProduction.objects.filter(zone__nom='Zone Assemblage').count() == 2
        assert Machine.objects.filter(identifiant_interne='ROB-01').count() == 1
        assert Machine.objects.filter(identifiant_interne='ROB-02').count() == 1
        assert Composant.objects.filter(machine__identifiant_interne='ROB-01').count() == 2

    def test_import_reuses_existing_equipment_and_updates_machine(self, api_client, admin_user):
        # Create existing usine, zone, ligne, machine
        u = Usine.objects.create(nom='Usine Existante', adresse='Ancienne adresse')
        z = Zone.objects.create(nom='Zone Existante', usine=u)
        l = LigneProduction.objects.create(nom='Ligne Existante', zone=z)
        m = Machine.objects.create(
            nom='Ancien Nom Machine',
            identifiant_interne='MCH-EXISTS',
            statut='NORMAL',
            ligne_production=l
        )

        rows = [
            {
                'usine_nom': 'Usine Existante',
                'zone_nom': 'Zone Existante',
                'ligne_nom': 'Ligne Existante',
                'machine_identifiant': 'MCH-EXISTS',
                'machine_nom': 'Nouveau Nom Machine',
                'machine_statut': 'CRITIQUE',
                'composant_nom': 'Nouveau Composant',
            }
        ]
        csv_file = make_hierarchy_csv(rows)
        api_client.force_authenticate(admin_user)
        r = api_client.post('/api/equipements/usines/import_csv/', {'file': csv_file}, format='multipart')

        assert r.status_code == 200
        assert Usine.objects.filter(nom='Usine Existante').count() == 1
        assert Zone.objects.filter(nom='Zone Existante').count() == 1
        assert LigneProduction.objects.filter(nom='Ligne Existante').count() == 1

        m.refresh_from_db()
        assert m.nom == 'Nouveau Nom Machine'
        assert m.statut == 'CRITIQUE'
        assert Composant.objects.filter(machine=m, nom='Nouveau Composant').count() == 1

    def test_import_forbidden_for_technician_and_operator(self, api_client, tech_user, op_user):
        rows = [{'usine_nom': 'Usine X'}]
        csv_file1 = make_hierarchy_csv(rows)
        api_client.force_authenticate(tech_user)
        r1 = api_client.post('/api/equipements/usines/import_csv/', {'file': csv_file1}, format='multipart')
        assert r1.status_code == 403

        csv_file2 = make_hierarchy_csv(rows)
        api_client.force_authenticate(op_user)
        r2 = api_client.post('/api/equipements/usines/import_csv/', {'file': csv_file2}, format='multipart')
        assert r2.status_code == 403
