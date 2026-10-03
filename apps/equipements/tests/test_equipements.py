import pytest
import io
import csv
from rest_framework.test import APIClient
from apps.accounts.models import Utilisateur
from apps.equipements.models import Usine, Zone, LigneProduction, Machine, Composant


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def api_client():
    return APIClient()

@pytest.fixture
def admin_user(db):
    return Utilisateur.objects.create_user(
        email='admin@eq.com', password='Admin@123!', role='ADMIN',
        nom='Admin', prenom='Eq'
    )

@pytest.fixture
def tech_user(db):
    return Utilisateur.objects.create_user(
        email='tech@eq.com', password='Tech@123!', role='TECHNICIEN',
        nom='Tech', prenom='Eq'
    )

@pytest.fixture
def op_user(db):
    return Utilisateur.objects.create_user(
        email='op@eq.com', password='Op@123!', role='OPERATEUR',
        nom='Op', prenom='Eq'
    )

@pytest.fixture
def usine(db):
    return Usine.objects.create(nom='Usine Test', adresse='Alger')

@pytest.fixture
def zone(db, usine):
    return Zone.objects.create(nom='Zone Test', usine=usine)

@pytest.fixture
def ligne(db, zone):
    return LigneProduction.objects.create(nom='Ligne Test', zone=zone)

@pytest.fixture
def machine(db, ligne):
    return Machine.objects.create(
        nom='Machine Test',
        identifiant_interne='MCH-001',
        statut='NORMAL',
        ligne_production=ligne
    )


# ── Helpers CSV ───────────────────────────────────────────────────────────────

def make_csv(rows):
    output = io.StringIO()
    fieldnames = ['nom', 'identifiant_interne', 'numero_serie', 'marque',
                  'modele', 'date_installation', 'statut', 'ligne_production_id']
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    output.seek(0)
    return io.BytesIO(output.read().encode('utf-8'))


# ── Tests Usine ───────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestUsineAPI:
    def test_list(self, api_client, admin_user, usine):
        api_client.force_authenticate(admin_user)
        r = api_client.get('/api/equipements/usines/')
        assert r.status_code == 200

    def test_create_admin(self, api_client, admin_user):
        api_client.force_authenticate(admin_user)
        r = api_client.post('/api/equipements/usines/', {'nom': 'Usine Alger'})
        assert r.status_code == 201
        assert r.data['nom'] == 'Usine Alger'

    def test_create_technicien_forbidden(self, api_client, tech_user):
        api_client.force_authenticate(tech_user)
        r = api_client.post('/api/equipements/usines/', {'nom': 'X'})
        assert r.status_code == 403

    def test_create_operateur_forbidden(self, api_client, op_user):
        api_client.force_authenticate(op_user)
        r = api_client.post('/api/equipements/usines/', {'nom': 'X'})
        assert r.status_code == 403

    def test_retrieve(self, api_client, admin_user, usine):
        api_client.force_authenticate(admin_user)
        r = api_client.get(f'/api/equipements/usines/{usine.id}/')
        assert r.status_code == 200
        assert r.data['nom'] == 'Usine Test'

    def test_update(self, api_client, admin_user, usine):
        api_client.force_authenticate(admin_user)
        r = api_client.patch(f'/api/equipements/usines/{usine.id}/', {'nom': 'Usine Modifiée'})
        assert r.status_code == 200
        assert r.data['nom'] == 'Usine Modifiée'

    def test_delete(self, api_client, admin_user, usine):
        api_client.force_authenticate(admin_user)
        r = api_client.delete(f'/api/equipements/usines/{usine.id}/')
        assert r.status_code == 204

    def test_unauthenticated_forbidden(self, api_client):
        r = api_client.get('/api/equipements/usines/')
        assert r.status_code == 401


# ── Tests Zone ────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestZoneAPI:
    def test_list(self, api_client, admin_user, zone):
        api_client.force_authenticate(admin_user)
        r = api_client.get('/api/equipements/zones/')
        assert r.status_code == 200

    def test_create_admin(self, api_client, admin_user, usine):
        api_client.force_authenticate(admin_user)
        r = api_client.post('/api/equipements/zones/', {'nom': 'Zone A', 'usine': usine.id})
        assert r.status_code == 201

    def test_create_forbidden(self, api_client, tech_user, usine):
        api_client.force_authenticate(tech_user)
        r = api_client.post('/api/equipements/zones/', {'nom': 'X', 'usine': usine.id})
        assert r.status_code == 403

    def test_filter_by_usine(self, api_client, admin_user, zone, usine):
        api_client.force_authenticate(admin_user)
        r = api_client.get(f'/api/equipements/zones/?usine={usine.id}')
        assert r.status_code == 200
        assert r.data['count'] >= 1

    def test_delete(self, api_client, admin_user, zone):
        api_client.force_authenticate(admin_user)
        r = api_client.delete(f'/api/equipements/zones/{zone.id}/')
        assert r.status_code == 204


# ── Tests LigneProduction ─────────────────────────────────────────────────────

@pytest.mark.django_db
class TestLigneProductionAPI:
    def test_list(self, api_client, admin_user, ligne):
        api_client.force_authenticate(admin_user)
        r = api_client.get('/api/equipements/lignes/')
        assert r.status_code == 200

    def test_create_admin(self, api_client, admin_user, zone):
        api_client.force_authenticate(admin_user)
        r = api_client.post('/api/equipements/lignes/', {'nom': 'Ligne B', 'zone': zone.id})
        assert r.status_code == 201

    def test_create_forbidden(self, api_client, op_user, zone):
        api_client.force_authenticate(op_user)
        r = api_client.post('/api/equipements/lignes/', {'nom': 'X', 'zone': zone.id})
        assert r.status_code == 403

    def test_filter_by_zone(self, api_client, admin_user, ligne, zone):
        api_client.force_authenticate(admin_user)
        r = api_client.get(f'/api/equipements/lignes/?zone={zone.id}')
        assert r.status_code == 200
        assert r.data['count'] >= 1


# ── Tests Machine ─────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestMachineAPI:
    def test_create_admin(self, api_client, admin_user, ligne):
        api_client.force_authenticate(admin_user)
        r = api_client.post('/api/equipements/machines/', {
            'nom': 'Machine A', 'identifiant_interne': 'MCH-A01',
            'statut': 'NORMAL', 'ligne_production': ligne.id
        })
        assert r.status_code == 201

    def test_create_technicien_forbidden(self, api_client, tech_user, ligne):
        api_client.force_authenticate(tech_user)
        r = api_client.post('/api/equipements/machines/', {
            'nom': 'X', 'identifiant_interne': 'MCH-X01', 'statut': 'NORMAL'
        })
        assert r.status_code == 403

    def test_create_operateur_forbidden(self, api_client, op_user):
        api_client.force_authenticate(op_user)
        r = api_client.post('/api/equipements/machines/', {
            'nom': 'X', 'identifiant_interne': 'MCH-X02', 'statut': 'NORMAL'
        })
        assert r.status_code == 403

    def test_list_technicien(self, api_client, tech_user, machine):
        api_client.force_authenticate(tech_user)
        r = api_client.get('/api/equipements/machines/')
        assert r.status_code == 200

    def test_list_operateur(self, api_client, op_user, machine):
        api_client.force_authenticate(op_user)
        r = api_client.get('/api/equipements/machines/')
        assert r.status_code == 200

    def test_retrieve(self, api_client, admin_user, machine):
        api_client.force_authenticate(admin_user)
        r = api_client.get(f'/api/equipements/machines/{machine.id}/')
        assert r.status_code == 200
        assert r.data['nom'] == 'Machine Test'

    def test_update_admin(self, api_client, admin_user, machine):
        api_client.force_authenticate(admin_user)
        r = api_client.patch(f'/api/equipements/machines/{machine.id}/', {'nom': 'Machine Modifiée'})
        assert r.status_code == 200

    @staticmethod
    def _png(name='machine.png'):
        import io
        from PIL import Image
        from django.core.files.uploadedfile import SimpleUploadedFile
        buffer = io.BytesIO()
        Image.new('RGB', (2, 2), (200, 30, 30)).save(buffer, format='PNG')
        return SimpleUploadedFile(name, buffer.getvalue(), content_type='image/png')

    def test_update_machine_photo_multipart(self, api_client, admin_user, machine, tmp_path, settings):
        """PATCH multipart : on peut ajouter / changer la photo d'une machine."""
        settings.MEDIA_ROOT = tmp_path
        api_client.force_authenticate(admin_user)
        r = api_client.patch(
            f'/api/equipements/machines/{machine.id}/',
            {'photo': self._png()},
            format='multipart',
        )
        assert r.status_code == 200, r.data
        machine.refresh_from_db()
        assert machine.photo
        assert 'machines/photos/' in machine.photo.name

        # La photo est bien exposée (URL) dans le détail
        detail = api_client.get(f'/api/equipements/machines/{machine.id}/')
        assert detail.status_code == 200
        assert detail.data['photo']
        assert 'machines/photos/' in detail.data['photo']

    def test_update_machine_photo_json_null_removes_it(self, api_client, admin_user, machine, tmp_path, settings):
        """PATCH JSON avec photo=null : retire la photo de la machine."""
        settings.MEDIA_ROOT = tmp_path
        machine.photo.save('x.png', self._png(), save=True)
        assert machine.photo

        api_client.force_authenticate(admin_user)
        r = api_client.patch(
            f'/api/equipements/machines/{machine.id}/',
            {'photo': None},
            format='json',
        )
        assert r.status_code == 200
        machine.refresh_from_db()
        assert not machine.photo

    def test_delete_admin(self, api_client, admin_user, machine):
        api_client.force_authenticate(admin_user)
        r = api_client.delete(f'/api/equipements/machines/{machine.id}/')
        assert r.status_code == 204

    def test_delete_technicien_forbidden(self, api_client, tech_user, machine):
        api_client.force_authenticate(tech_user)
        r = api_client.delete(f'/api/equipements/machines/{machine.id}/')
        assert r.status_code == 403

    def test_delete_operateur_forbidden(self, api_client, op_user, machine):
        api_client.force_authenticate(op_user)
        r = api_client.delete(f'/api/equipements/machines/{machine.id}/')
        assert r.status_code == 403

    def test_search_by_nom(self, api_client, admin_user, machine):
        api_client.force_authenticate(admin_user)
        r = api_client.get('/api/equipements/machines/?search=Machine Test')
        assert r.status_code == 200
        assert r.data['count'] >= 1

    def test_search_by_identifiant(self, api_client, admin_user, machine):
        api_client.force_authenticate(admin_user)
        r = api_client.get('/api/equipements/machines/?search=MCH-001')
        assert r.status_code == 200
        assert r.data['count'] >= 1

    def test_filter_by_statut(self, api_client, admin_user, machine):
        api_client.force_authenticate(admin_user)
        r = api_client.get('/api/equipements/machines/?statut=NORMAL')
        assert r.status_code == 200
        assert r.data['count'] >= 1

    def test_pagination(self, api_client, admin_user, machine):
        api_client.force_authenticate(admin_user)
        r = api_client.get('/api/equipements/machines/')
        assert r.status_code == 200
        assert 'count' in r.data
        assert 'results' in r.data

    def test_unauthenticated_forbidden(self, api_client):
        r = api_client.get('/api/equipements/machines/')
        assert r.status_code == 401


# ── Tests Import CSV ──────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestImportCSV:
    def test_valid_csv(self, api_client, admin_user):
        api_client.force_authenticate(admin_user)
        f = make_csv([{
            'nom': 'Machine CSV', 'identifiant_interne': 'CSV-001',
            'numero_serie': 'SN001', 'marque': 'ABB', 'modele': 'M1',
            'date_installation': '2024-01-15', 'statut': 'NORMAL',
            'ligne_production_id': ''
        }])
        r = api_client.post('/api/equipements/machines/import_csv/', {'file': f}, format='multipart')
        assert r.status_code == 200
        assert r.data['created'] == 1
        assert len(r.data['errors']) == 0

    def test_duplicate_identifiant(self, api_client, admin_user, machine):
        api_client.force_authenticate(admin_user)
        f = make_csv([{
            'nom': 'Doublon', 'identifiant_interne': 'MCH-001',
            'numero_serie': '', 'marque': '', 'modele': '',
            'date_installation': '', 'statut': 'NORMAL', 'ligne_production_id': ''
        }])
        r = api_client.post('/api/equipements/machines/import_csv/', {'file': f}, format='multipart')
        assert r.status_code == 200
        assert r.data['created'] == 0
        assert len(r.data['errors']) > 0

    def test_invalid_statut(self, api_client, admin_user):
        api_client.force_authenticate(admin_user)
        f = make_csv([{
            'nom': 'Bad Statut', 'identifiant_interne': 'BAD-001',
            'numero_serie': '', 'marque': '', 'modele': '',
            'date_installation': '', 'statut': 'INVALIDE', 'ligne_production_id': ''
        }])
        r = api_client.post('/api/equipements/machines/import_csv/', {'file': f}, format='multipart')
        assert r.status_code == 200
        assert r.data['created'] == 0
        assert len(r.data['errors']) > 0

    def test_missing_nom(self, api_client, admin_user):
        api_client.force_authenticate(admin_user)
        f = make_csv([{
            'nom': '', 'identifiant_interne': 'MISS-001',
            'numero_serie': '', 'marque': '', 'modele': '',
            'date_installation': '', 'statut': 'NORMAL', 'ligne_production_id': ''
        }])
        r = api_client.post('/api/equipements/machines/import_csv/', {'file': f}, format='multipart')
        assert r.status_code == 200
        assert r.data['created'] == 0
        assert len(r.data['errors']) > 0

    def test_empty_csv(self, api_client, admin_user):
        api_client.force_authenticate(admin_user)
        f = make_csv([])
        r = api_client.post('/api/equipements/machines/import_csv/', {'file': f}, format='multipart')
        assert r.status_code == 200
        assert r.data['created'] == 0
        assert len(r.data['errors']) == 0

    def test_non_admin_forbidden(self, api_client, tech_user):
        api_client.force_authenticate(tech_user)
        f = make_csv([])
        r = api_client.post('/api/equipements/machines/import_csv/', {'file': f}, format='multipart')
        assert r.status_code == 403


# ── Tests Composant ───────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestComposantAPI:
    def test_create(self, api_client, admin_user, machine):
        api_client.force_authenticate(admin_user)
        r = api_client.post('/api/equipements/composants/', {
            'nom': 'Moteur', 'machine': machine.id, 'numero_piece': 'CP-001'
        })
        assert r.status_code == 201

    def test_list(self, api_client, admin_user, machine):
        api_client.force_authenticate(admin_user)
        Composant.objects.create(nom='C1', machine=machine)
        r = api_client.get('/api/equipements/composants/')
        assert r.status_code == 200
        assert r.data['count'] >= 1

    def test_create_forbidden(self, api_client, op_user, machine):
        api_client.force_authenticate(op_user)
        r = api_client.post('/api/equipements/composants/', {
            'nom': 'X', 'machine': machine.id
        })
        assert r.status_code == 403

    def test_delete(self, api_client, admin_user, machine):
        api_client.force_authenticate(admin_user)
        c = Composant.objects.create(nom='C2', machine=machine)
        r = api_client.delete(f'/api/equipements/composants/{c.id}/')
        assert r.status_code == 204


# ── Tests Hiérarchie ──────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestHierarchie:
    """Tests de la hiérarchie complète : Usine → Zone → Ligne → Machine → Composant."""

    def test_hierarchie_complete(self, api_client, admin_user, machine):
        """Vérifie que la hiérarchie complète est bien accessible."""
        api_client.force_authenticate(admin_user)
        usine = machine.ligne_production.zone.usine
        r = api_client.get(f'/api/equipements/usines/{usine.id}/hierarchie/')
        assert r.status_code == 200
        assert r.data['nom'] == usine.nom
        assert 'zones' in r.data
        assert len(r.data['zones']) >= 1
        zone_data = r.data['zones'][0]
        assert 'lignes' in zone_data
        assert len(zone_data['lignes']) >= 1
        ligne_data = zone_data['lignes'][0]
        assert 'machines' in ligne_data
        assert len(ligne_data['machines']) >= 1
        machine_data = ligne_data['machines'][0]
        assert machine_data['nom'] == machine.nom
        assert 'composants' in machine_data

    def test_hierarchie_technicien_can_read(self, api_client, tech_user, machine):
        """Technicien peut lire la hiérarchie."""
        api_client.force_authenticate(tech_user)
        usine = machine.ligne_production.zone.usine
        r = api_client.get(f'/api/equipements/usines/{usine.id}/hierarchie/')
        assert r.status_code == 200

    def test_hierarchie_operateur_can_read(self, api_client, op_user, machine):
        """Opérateur peut lire la hiérarchie."""
        api_client.force_authenticate(op_user)
        usine = machine.ligne_production.zone.usine
        r = api_client.get(f'/api/equipements/usines/{usine.id}/hierarchie/')
        assert r.status_code == 200

    def test_zone_has_lignes_count(self, api_client, admin_user, ligne):
        """ZoneSerializer retourne lignes_count."""
        api_client.force_authenticate(admin_user)
        zone = ligne.zone
        r = api_client.get(f'/api/equipements/zones/{zone.id}/')
        assert r.status_code == 200
        assert 'lignes_count' in r.data
        assert r.data['lignes_count'] >= 1

    def test_ligne_has_machines_count(self, api_client, admin_user, machine):
        """LigneProductionSerializer retourne machines_count."""
        api_client.force_authenticate(admin_user)
        ligne = machine.ligne_production
        r = api_client.get(f'/api/equipements/lignes/{ligne.id}/')
        assert r.status_code == 200
        assert 'machines_count' in r.data
        assert r.data['machines_count'] >= 1

    def test_usine_has_zones_count(self, api_client, admin_user, zone):
        """UsineSerializer retourne zones_count."""
        api_client.force_authenticate(admin_user)
        r = api_client.get(f'/api/equipements/usines/{zone.usine.id}/')
        assert r.status_code == 200
        assert 'zones_count' in r.data
        assert r.data['zones_count'] >= 1

    def test_cannot_create_zone_without_usine(self, api_client, admin_user):
        """Une zone sans usine valide doit être refusée."""
        api_client.force_authenticate(admin_user)
        r = api_client.post('/api/equipements/zones/', {'nom': 'Zone X', 'usine': 99999})
        assert r.status_code == 400

    def test_cannot_create_ligne_without_zone(self, api_client, admin_user):
        """Une ligne sans zone valide doit être refusée."""
        api_client.force_authenticate(admin_user)
        r = api_client.post('/api/equipements/lignes/', {'nom': 'Ligne X', 'zone': 99999})
        assert r.status_code == 400

    def test_cannot_create_composant_without_machine(self, api_client, admin_user):
        """Un composant sans machine valide doit être refusé."""
        api_client.force_authenticate(admin_user)
        r = api_client.post('/api/equipements/composants/', {'nom': 'C', 'machine': 99999})
        assert r.status_code == 400

    def test_machine_inline_composants_list(self, api_client, admin_user, machine):
        """GET /machines/{id}/composants/ retourne les composants de la machine."""
        Composant.objects.create(nom='Moteur', machine=machine)
        api_client.force_authenticate(admin_user)
        r = api_client.get(f'/api/equipements/machines/{machine.id}/composants/')
        assert r.status_code == 200
        assert len(r.data) >= 1

    def test_machine_inline_composants_add(self, api_client, admin_user, machine):
        """POST /machines/{id}/composants/add/ crée un composant lié."""
        api_client.force_authenticate(admin_user)
        r = api_client.post(f'/api/equipements/machines/{machine.id}/composants/add/', {
            'nom': 'Vanne', 'numero_piece': 'VP-001', 'description': 'Vanne de contrôle'
        })
        assert r.status_code == 201
        assert r.data['nom'] == 'Vanne'
        assert r.data['machine'] == machine.id

    def test_machine_inline_composants_add_technicien_forbidden(self, api_client, tech_user, machine):
        """Technicien ne peut pas ajouter de composant inline."""
        api_client.force_authenticate(tech_user)
        r = api_client.post(f'/api/equipements/machines/{machine.id}/composants/add/', {
            'nom': 'Vanne', 'numero_piece': 'VP-002'
        })
        assert r.status_code == 403

    def test_composant_update(self, api_client, admin_user, machine):
        """PATCH /composants/{id}/ met à jour un composant."""
        c = Composant.objects.create(nom='Ancien nom', machine=machine)
        api_client.force_authenticate(admin_user)
        r = api_client.patch(f'/api/equipements/composants/{c.id}/', {'nom': 'Nouveau nom'})
        assert r.status_code == 200
        assert r.data['nom'] == 'Nouveau nom'

    def test_composant_delete(self, api_client, admin_user, machine):
        """DELETE /composants/{id}/ supprime un composant."""
        c = Composant.objects.create(nom='À supprimer', machine=machine)
        api_client.force_authenticate(admin_user)
        r = api_client.delete(f'/api/equipements/composants/{c.id}/')
        assert r.status_code == 204
        assert not Composant.objects.filter(id=c.id).exists()

    def test_filter_zones_by_usine(self, api_client, admin_user, zone):
        """Filtre zones par usine."""
        api_client.force_authenticate(admin_user)
        r = api_client.get(f'/api/equipements/zones/?usine={zone.usine.id}')
        assert r.status_code == 200
        for item in r.data['results']:
            assert item['usine'] == zone.usine.id

    def test_filter_lignes_by_zone(self, api_client, admin_user, ligne):
        """Filtre lignes par zone."""
        api_client.force_authenticate(admin_user)
        r = api_client.get(f'/api/equipements/lignes/?zone={ligne.zone.id}')
        assert r.status_code == 200
        for item in r.data['results']:
            assert item['zone'] == ligne.zone.id

    def test_delete_usine_cascades_zones(self, api_client, admin_user, zone):
        """Supprimer une usine supprime ses zones en cascade."""
        usine = zone.usine
        usine_id = usine.id
        zone_id  = zone.id
        api_client.force_authenticate(admin_user)
        r = api_client.delete(f'/api/equipements/usines/{usine_id}/')
        assert r.status_code == 204
        assert not Zone.objects.filter(id=zone_id).exists()

    def test_delete_zone_cascades_lignes(self, api_client, admin_user, ligne):
        """Supprimer une zone supprime ses lignes en cascade."""
        zone_id  = ligne.zone.id
        ligne_id = ligne.id
        api_client.force_authenticate(admin_user)
        r = api_client.delete(f'/api/equipements/zones/{zone_id}/')
        assert r.status_code == 204
        assert not LigneProduction.objects.filter(id=ligne_id).exists()

    def test_seed_data_structure(self, api_client, admin_user):
        """Vérifie que la structure de seed peut être créée correctement."""
        api_client.force_authenticate(admin_user)
        # Créer la structure "Usine Centrale Tunis"
        r_usine = api_client.post('/api/equipements/usines/', {
            'nom': 'Usine Centrale Tunis', 'adresse': 'Tunis, Tunisie'
        })
        assert r_usine.status_code == 201
        usine_id = r_usine.data['id']

        r_zone = api_client.post('/api/equipements/zones/', {
            'nom': 'Atelier Production A', 'usine': usine_id
        })
        assert r_zone.status_code == 201
        zone_id = r_zone.data['id']

        r_ligne = api_client.post('/api/equipements/lignes/', {
            'nom': 'Ligne Production 01', 'zone': zone_id
        })
        assert r_ligne.status_code == 201
        ligne_id = r_ligne.data['id']

        r_machine = api_client.post('/api/equipements/machines/', {
            'nom': 'Pompe Hydraulique P-001',
            'identifiant_interne': 'PH-P001',
            'statut': 'NORMAL',
            'ligne_production': ligne_id
        })
        assert r_machine.status_code == 201
        machine_id = r_machine.data['id']

        # Composants
        for composant_nom in ['Moteur électrique', 'Vanne de contrôle', 'Joint hydraulique']:
            r_c = api_client.post('/api/equipements/composants/', {
                'nom': composant_nom, 'machine': machine_id
            })
            assert r_c.status_code == 201

        # Vérifier la hiérarchie
        r_hier = api_client.get(f'/api/equipements/usines/{usine_id}/hierarchie/')
        assert r_hier.status_code == 200
        assert r_hier.data['nom'] == 'Usine Centrale Tunis'
        assert len(r_hier.data['zones']) == 1
        assert len(r_hier.data['zones'][0]['lignes']) == 1
        assert len(r_hier.data['zones'][0]['lignes'][0]['machines']) == 1
        assert len(r_hier.data['zones'][0]['lignes'][0]['machines'][0]['composants']) == 3
