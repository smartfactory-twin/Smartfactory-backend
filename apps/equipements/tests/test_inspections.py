"""Tests Module 4 — Inspection visuelle par IA (UC-10).

Couvre :
 1. création d'une inspection ;
 2. upload d'une image valide ;
 3. rejet d'un mauvais format ;
 4. rejet d'une image trop volumineuse ;
 5. association à une machine ;
 6. lancement de l'analyse IA ;
 7. récupération du résultat ;
 8. permissions ADMIN ;
 9. permissions TECHNICIEN ;
10. restrictions OPERATEUR.
"""
import io
import os

import pytest
from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.equipements.models import (
    Usine, Zone, LigneProduction, Machine, InspectionVisuelle, UserScope,
)
from apps.equipements.vision_ai import MockVisionAIService


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def media_root(settings, tmp_path):
    """Isole les fichiers média dans un dossier temporaire par test."""
    settings.MEDIA_ROOT = tmp_path
    yield


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def admin_user(db):
    return Utilisateur.objects.create_user(
        email='m4-admin@smartfactory.com', password='Admin@123!', role='ADMIN',
        nom='Admin', prenom='Module4',
    )


@pytest.fixture
def tech_user(db):
    return Utilisateur.objects.create_user(
        email='m4-tech@smartfactory.com', password='Tech@123!', role='TECHNICIEN',
        nom='Tech', prenom='Module4',
    )


@pytest.fixture
def op_user(db):
    return Utilisateur.objects.create_user(
        email='m4-op@smartfactory.com', password='Op@123!', role='OPERATEUR',
        nom='Op', prenom='Module4',
    )


@pytest.fixture
def machine(db):
    usine = Usine.objects.create(nom='Usine M4')
    zone = Zone.objects.create(nom='Zone M4', usine=usine)
    ligne = LigneProduction.objects.create(nom='Ligne M4', zone=zone)
    return Machine.objects.create(
        nom='Presse hydraulique PH-010', identifiant_interne='PH-010',
        statut='NORMAL', ligne_production=ligne,
    )


# ── Helpers images ────────────────────────────────────────────────────────────

def make_png(name='inspection.png', size=(48, 48), color=(200, 30, 30)):
    buffer = io.BytesIO()
    Image.new('RGB', size, color).save(buffer, format='PNG')
    return SimpleUploadedFile(name, buffer.getvalue(), content_type='image/png')


def make_jpeg(name='inspection.jpg', size=(48, 48), color=(30, 120, 200)):
    buffer = io.BytesIO()
    Image.new('RGB', size, color).save(buffer, format='JPEG')
    return SimpleUploadedFile(name, buffer.getvalue(), content_type='image/jpeg')


def make_large_png(size=(1200, 1200)):
    """PNG volumineux (bruit aléatoire peu compressible)."""
    data = os.urandom(size[0] * size[1] * 3)
    image = Image.frombytes('RGB', size, data)
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    return SimpleUploadedFile('big.png', buffer.getvalue(), content_type='image/png')


def create_inspection(machine, user, upload=None):
    return InspectionVisuelle.objects.create(
        machine=machine, utilisateur=user, image=upload or make_png(),
    )


class StubVisionService:
    """Service IA de test : résultat de défaut déterministe."""

    def analyze_image(self, image):
        return {
            'defect_detected': True,
            'defect_type': 'Fissure',
            'confidence': 0.93,
            'localization': 'centre',
            'comment': 'Défaut de type « Fissure » détecté.',
        }


class FailingVisionService:
    def analyze_image(self, image):
        raise RuntimeError('modèle indisponible')


# ── 1. Création d'une inspection ──────────────────────────────────────────────

@pytest.mark.django_db
class TestInspectionCreate:
    def test_01_create_inspection(self, api_client, admin_user, machine):
        api_client.force_authenticate(admin_user)
        r = api_client.post('/api/inspections/', {
            'machine': machine.id, 'image': make_png(),
            'observations': 'Contrôle de routine',
        }, format='multipart')
        assert r.status_code == 201
        assert InspectionVisuelle.objects.count() == 1
        inspection = InspectionVisuelle.objects.get()
        assert inspection.machine == machine
        assert inspection.utilisateur == admin_user
        assert inspection.statut_analyse == 'EN_ATTENTE'
        assert r.data['statut_analyse'] == 'EN_ATTENTE'
        assert r.data['statut_analyse_label'] == 'En attente'

    def test_01b_create_requires_machine(self, api_client, admin_user):
        api_client.force_authenticate(admin_user)
        r = api_client.post('/api/inspections/', {'image': make_png()}, format='multipart')
        assert r.status_code == 400
        assert 'machine' in r.data
        assert InspectionVisuelle.objects.count() == 0

    def test_01c_create_requires_image(self, api_client, admin_user, machine):
        api_client.force_authenticate(admin_user)
        r = api_client.post('/api/inspections/', {'machine': machine.id}, format='multipart')
        assert r.status_code == 400
        assert 'image' in r.data
        assert InspectionVisuelle.objects.count() == 0

    def test_01d_create_unknown_machine(self, api_client, admin_user):
        api_client.force_authenticate(admin_user)
        r = api_client.post('/api/inspections/', {
            'machine': 999999, 'image': make_png(),
        }, format='multipart')
        assert r.status_code == 400
        assert InspectionVisuelle.objects.count() == 0


# ── 2. Upload d'une image valide ──────────────────────────────────────────────

@pytest.mark.django_db
class TestInspectionUpload:
    def test_02_upload_valid_png(self, api_client, admin_user, machine):
        api_client.force_authenticate(admin_user)
        r = api_client.post('/api/inspections/', {
            'machine': machine.id, 'image': make_png('photo.png'),
        }, format='multipart')
        assert r.status_code == 201
        inspection = InspectionVisuelle.objects.get()
        assert inspection.image.name.endswith('.png')
        assert inspection.image.name.startswith('inspections/images/')
        assert r.data['image']  # URL absolue exposée

    def test_02b_upload_valid_jpeg(self, api_client, admin_user, machine):
        api_client.force_authenticate(admin_user)
        r = api_client.post('/api/inspections/', {
            'machine': machine.id, 'image': make_jpeg('photo.jpg'),
        }, format='multipart')
        assert r.status_code == 201
        assert InspectionVisuelle.objects.get().image.name.endswith('.jpg')


# ── 3. Rejet d'un mauvais format ──────────────────────────────────────────────

@pytest.mark.django_db
class TestInspectionBadFormat:
    def test_03_reject_text_file(self, api_client, admin_user, machine):
        api_client.force_authenticate(admin_user)
        bad = SimpleUploadedFile('notes.txt', b'ceci nest pas une image',
                                 content_type='text/plain')
        r = api_client.post('/api/inspections/', {
            'machine': machine.id, 'image': bad,
        }, format='multipart')
        assert r.status_code == 400
        assert 'image' in r.data
        assert InspectionVisuelle.objects.count() == 0

    def test_03b_reject_disguised_extension(self, api_client, admin_user, machine):
        # Un fichier .png mais dont le contenu n'est pas une image.
        bad = SimpleUploadedFile('fake.png', b'pas une image', content_type='image/png')
        api_client.force_authenticate(admin_user)
        r = api_client.post('/api/inspections/', {
            'machine': machine.id, 'image': bad,
        }, format='multipart')
        assert r.status_code == 400
        assert InspectionVisuelle.objects.count() == 0


# ── 4. Rejet d'une image trop volumineuse ─────────────────────────────────────

@pytest.mark.django_db
class TestInspectionTooLarge:
    def test_04_reject_oversized_image(self, api_client, admin_user, machine,
                                       settings):
        settings.INSPECTION_IMAGE_MAX_MB = 1
        big = make_large_png()
        assert big.size > 1024 * 1024  # le fichier dépasse bien 1 Mo
        api_client.force_authenticate(admin_user)
        r = api_client.post('/api/inspections/', {
            'machine': machine.id, 'image': big,
        }, format='multipart')
        assert r.status_code == 400
        assert 'image' in r.data
        assert InspectionVisuelle.objects.count() == 0


# ── 5. Association à une machine ──────────────────────────────────────────────

@pytest.mark.django_db
class TestInspectionMachine:
    def test_05_machine_info_exposed(self, api_client, admin_user, machine):
        api_client.force_authenticate(admin_user)
        r = api_client.post('/api/inspections/', {
            'machine': machine.id, 'image': make_png(),
        }, format='multipart')
        assert r.status_code == 201
        assert r.data['machine'] == machine.id
        assert r.data['machine_nom'] == 'Presse hydraulique PH-010'
        assert r.data['machine_identifiant'] == 'PH-010'
        assert r.data['machine_statut'] == 'NORMAL'
        assert r.data['ligne_nom'] == 'Ligne M4'
        assert r.data['usine_nom'] == 'Usine M4'

    def test_05b_filter_by_machine(self, api_client, admin_user, machine):
        other = Machine.objects.create(
            nom='Autre machine', identifiant_interne='ZZ-001',
            statut='NORMAL', ligne_production=machine.ligne_production,
        )
        create_inspection(machine, admin_user)
        InspectionVisuelle.objects.create(
            machine=other, utilisateur=admin_user, image=make_png(),
        )
        api_client.force_authenticate(admin_user)
        r = api_client.get(f'/api/inspections/?machine={machine.id}')
        assert r.status_code == 200
        assert r.data['count'] == 1
        assert r.data['results'][0]['machine'] == machine.id


# ── 6. Lancement de l'analyse IA ──────────────────────────────────────────────

@pytest.mark.django_db
class TestInspectionAnalyze:
    def test_06_launch_analysis(self, api_client, admin_user, machine, monkeypatch):
        monkeypatch.setattr(
            'apps.equipements.views.get_vision_service', lambda: StubVisionService()
        )
        inspection = create_inspection(machine, admin_user)
        api_client.force_authenticate(admin_user)
        r = api_client.post(f'/api/inspections/{inspection.id}/analyze/')
        assert r.status_code == 200
        inspection.refresh_from_db()
        assert inspection.statut_analyse == 'TERMINEE'
        assert inspection.score_confiance == 0.93
        assert inspection.resultat_analyse['defect_detected'] is True
        assert inspection.resultat_analyse['defect_type'] == 'Fissure'

    def test_06b_analysis_error_recorded(self, api_client, admin_user, machine,
                                         monkeypatch):
        monkeypatch.setattr(
            'apps.equipements.views.get_vision_service', lambda: FailingVisionService()
        )
        inspection = create_inspection(machine, admin_user)
        api_client.force_authenticate(admin_user)
        r = api_client.post(f'/api/inspections/{inspection.id}/analyze/')
        assert r.status_code == 400
        inspection.refresh_from_db()
        assert inspection.statut_analyse == 'ERREUR'
        assert inspection.erreur_message

    def test_06c_analyze_unknown_inspection(self, api_client, admin_user):
        api_client.force_authenticate(admin_user)
        r = api_client.post('/api/inspections/999999/analyze/')
        assert r.status_code == 404

    def test_06d_mock_service_contract(self):
        service = MockVisionAIService()
        upload = make_png()
        result = service.analyze_image(upload)
        assert set(result) == {
            'defect_detected', 'defect_type', 'confidence', 'localization', 'comment',
        }
        assert isinstance(result['defect_detected'], bool)
        assert 0.0 <= result['confidence'] <= 1.0
        # Déterminisme : même image → même résultat.
        assert service.analyze_image(make_png())['confidence'] == result['confidence']


# ── 7. Récupération du résultat ───────────────────────────────────────────────

@pytest.mark.django_db
class TestInspectionResult:
    def test_07_retrieve_after_analysis(self, api_client, admin_user, machine,
                                        monkeypatch):
        monkeypatch.setattr(
            'apps.equipements.views.get_vision_service', lambda: StubVisionService()
        )
        inspection = create_inspection(machine, admin_user)
        api_client.force_authenticate(admin_user)
        api_client.post(f'/api/inspections/{inspection.id}/analyze/')

        r = api_client.get(f'/api/inspections/{inspection.id}/')
        assert r.status_code == 200
        assert r.data['statut_analyse'] == 'TERMINEE'
        assert r.data['resultat_analyse']['defect_detected'] is True
        assert r.data['resultat_analyse']['defect_type'] == 'Fissure'
        assert r.data['resultat_analyse']['localization'] == 'centre'
        assert r.data['score_confiance'] == 0.93
        assert r.data['utilisateur_nom'] == 'Module4 Admin'

    def test_07b_history_listing(self, api_client, admin_user, machine):
        create_inspection(machine, admin_user)
        create_inspection(machine, admin_user)
        api_client.force_authenticate(admin_user)
        r = api_client.get('/api/inspections/')
        assert r.status_code == 200
        assert r.data['count'] == 2

    def test_07c_alias_route_works(self, api_client, admin_user, machine):
        create_inspection(machine, admin_user)
        api_client.force_authenticate(admin_user)
        assert api_client.get('/api/equipements/inspections/').status_code == 200
        assert api_client.get('/api/inspections/').status_code == 200

    def test_07d_filter_by_status(self, api_client, admin_user, machine, monkeypatch):
        monkeypatch.setattr(
            'apps.equipements.views.get_vision_service', lambda: StubVisionService()
        )
        inspection = create_inspection(machine, admin_user)
        create_inspection(machine, admin_user)
        api_client.force_authenticate(admin_user)
        api_client.post(f'/api/inspections/{inspection.id}/analyze/')
        r = api_client.get('/api/inspections/?statut_analyse=TERMINEE')
        assert r.status_code == 200
        assert r.data['count'] == 1


# ── 8. Permissions ADMIN ──────────────────────────────────────────────────────

@pytest.mark.django_db
class TestInspectionAdminPermissions:
    def test_08_admin_full_access(self, api_client, admin_user, machine, monkeypatch):
        monkeypatch.setattr(
            'apps.equipements.views.get_vision_service', lambda: StubVisionService()
        )
        api_client.force_authenticate(admin_user)
        r = api_client.post('/api/inspections/', {
            'machine': machine.id, 'image': make_png(),
        }, format='multipart')
        assert r.status_code == 201
        inspection_id = r.data['id']
        assert api_client.post(
            f'/api/inspections/{inspection_id}/analyze/'
        ).status_code == 200
        assert api_client.patch(
            f'/api/inspections/{inspection_id}/', {'observations': 'MAJ'}
        ).status_code == 200
        assert api_client.delete(
            f'/api/inspections/{inspection_id}/'
        ).status_code == 204

    def test_08b_unauthenticated_rejected(self, api_client, machine):
        assert api_client.get('/api/inspections/').status_code == 401
        assert api_client.post('/api/inspections/', {
            'machine': machine.id, 'image': make_png(),
        }, format='multipart').status_code == 401


# ── 9. Permissions TECHNICIEN ─────────────────────────────────────────────────

@pytest.mark.django_db
class TestInspectionTechnicianPermissions:
    def test_09_technicien_can_create_and_analyze(self, api_client, tech_user,
                                                  machine, monkeypatch):
        # Depuis le passage en fail-closed, un technicien doit disposer d'une
        # affectation explicite pour intervenir sur une machine.
        UserScope.objects.create(utilisateur=tech_user,
                                 ligne=machine.ligne_production)
        monkeypatch.setattr(
            'apps.equipements.views.get_vision_service', lambda: StubVisionService()
        )
        api_client.force_authenticate(tech_user)
        r = api_client.post('/api/inspections/', {
            'machine': machine.id, 'image': make_png(),
        }, format='multipart')
        assert r.status_code == 201
        inspection_id = r.data['id']
        assert api_client.post(
            f'/api/inspections/{inspection_id}/analyze/'
        ).status_code == 200
        assert api_client.get('/api/inspections/').status_code == 200

    def test_09b_technicien_cannot_delete(self, api_client, tech_user, machine):
        inspection = create_inspection(machine, tech_user)
        api_client.force_authenticate(tech_user)
        r = api_client.delete(f'/api/inspections/{inspection.id}/')
        assert r.status_code == 403
        assert InspectionVisuelle.objects.filter(id=inspection.id).exists()


# ── 10. Restrictions OPERATEUR ────────────────────────────────────────────────

@pytest.mark.django_db
class TestInspectionOperatorPermissions:
    def test_10_operateur_read_only(self, api_client, op_user, machine, admin_user):
        create_inspection(machine, admin_user)
        api_client.force_authenticate(op_user)
        assert api_client.get('/api/inspections/').status_code == 200

    def test_10b_operateur_cannot_create(self, api_client, op_user, machine):
        api_client.force_authenticate(op_user)
        r = api_client.post('/api/inspections/', {
            'machine': machine.id, 'image': make_png(),
        }, format='multipart')
        assert r.status_code == 403
        assert InspectionVisuelle.objects.count() == 0

    def test_10c_operateur_cannot_analyze_or_delete(self, api_client, op_user,
                                                    machine, admin_user):
        inspection = create_inspection(machine, admin_user)
        api_client.force_authenticate(op_user)
        assert api_client.post(
            f'/api/inspections/{inspection.id}/analyze/'
        ).status_code == 403
        assert api_client.delete(
            f'/api/inspections/{inspection.id}/'
        ).status_code == 403
        assert InspectionVisuelle.objects.filter(id=inspection.id).exists()


# ── 11. Champs de résultat dénormalisés (cahier des charges Module 4) ─────────

@pytest.mark.django_db
class TestInspectionResultFields:
    """Les champs defect_detected / defect_type / confidence / observation
    reflètent le résultat de l'analyse et sont exposés par l'API.
    """

    def test_11a_fields_persisted_after_analysis(self, api_client, admin_user,
                                                 machine, monkeypatch):
        monkeypatch.setattr(
            'apps.equipements.views.get_vision_service', lambda: StubVisionService()
        )
        inspection = create_inspection(machine, admin_user)
        api_client.force_authenticate(admin_user)
        r = api_client.post(f'/api/inspections/{inspection.id}/analyze/')
        assert r.status_code == 200

        inspection.refresh_from_db()
        assert inspection.defect_detected is True
        assert inspection.defect_type == 'Fissure'
        assert inspection.confidence == 0.93
        assert inspection.score_confiance == 0.93
        assert inspection.observation
        assert inspection.statut_analyse == 'TERMINEE'

    def test_11b_serializer_exposes_result_fields(self, api_client, admin_user,
                                                  machine, monkeypatch):
        monkeypatch.setattr(
            'apps.equipements.views.get_vision_service', lambda: StubVisionService()
        )
        inspection = create_inspection(machine, admin_user)
        api_client.force_authenticate(admin_user)
        api_client.post(f'/api/inspections/{inspection.id}/analyze/')

        r = api_client.get(f'/api/inspections/{inspection.id}/')
        assert r.status_code == 200
        assert r.data['defect_detected'] is True
        assert r.data['defect_type'] == 'Fissure'
        assert r.data['confidence'] == 0.93
        assert r.data['observation']
        # Alias `statut` du cahier des charges.
        assert r.data['statut'] == 'TERMINEE'
        assert r.data['statut_analyse'] == 'TERMINEE'

    def test_11c_defaults_before_analysis(self, api_client, admin_user, machine):
        inspection = create_inspection(machine, admin_user)
        api_client.force_authenticate(admin_user)
        r = api_client.get(f'/api/inspections/{inspection.id}/')
        assert r.status_code == 200
        assert r.data['defect_detected'] is None
        assert r.data['defect_type'] == ''
        assert r.data['confidence'] is None
        assert r.data['observation'] == ''
        assert r.data['statut'] == 'EN_ATTENTE'

    def test_11d_error_clears_result_fields(self, api_client, admin_user, machine,
                                            monkeypatch):
        inspection = create_inspection(machine, admin_user)
        api_client.force_authenticate(admin_user)

        monkeypatch.setattr(
            'apps.equipements.views.get_vision_service', lambda: StubVisionService()
        )
        api_client.post(f'/api/inspections/{inspection.id}/analyze/')
        inspection.refresh_from_db()
        assert inspection.defect_type == 'Fissure'

        monkeypatch.setattr(
            'apps.equipements.views.get_vision_service', lambda: FailingVisionService()
        )
        r = api_client.post(f'/api/inspections/{inspection.id}/analyze/')
        assert r.status_code == 400

        inspection.refresh_from_db()
        assert inspection.statut_analyse == 'ERREUR'
        assert inspection.defect_detected is None
        assert inspection.defect_type == ''
        assert inspection.confidence is None
        assert inspection.observation == ''

    def test_11e_filter_by_defect_type(self, api_client, admin_user, machine,
                                       monkeypatch):
        monkeypatch.setattr(
            'apps.equipements.views.get_vision_service', lambda: StubVisionService()
        )
        analyzed = create_inspection(machine, admin_user)
        create_inspection(machine, admin_user)
        api_client.force_authenticate(admin_user)
        api_client.post(f'/api/inspections/{analyzed.id}/analyze/')

        r = api_client.get('/api/inspections/?defect_type=Fissure')
        assert r.status_code == 200
        assert r.data['count'] == 1
        assert r.data['results'][0]['id'] == analyzed.id

    def test_11f_filter_by_defect_detected(self, api_client, admin_user, machine,
                                           monkeypatch):
        monkeypatch.setattr(
            'apps.equipements.views.get_vision_service', lambda: StubVisionService()
        )
        analyzed = create_inspection(machine, admin_user)
        create_inspection(machine, admin_user)
        api_client.force_authenticate(admin_user)
        api_client.post(f'/api/inspections/{analyzed.id}/analyze/')

        r = api_client.get('/api/inspections/?defect_detected=true')
        assert r.status_code == 200
        assert r.data['count'] == 1
        assert r.data['results'][0]['id'] == analyzed.id

    def test_11g_ordering_by_confidence(self, api_client, admin_user, machine):
        InspectionVisuelle.objects.create(
            machine=machine, utilisateur=admin_user, image=make_png(),
            statut_analyse='TERMINEE', confidence=0.5, score_confiance=0.5,
        )
        InspectionVisuelle.objects.create(
            machine=machine, utilisateur=admin_user, image=make_png(),
            statut_analyse='TERMINEE', confidence=0.9, score_confiance=0.9,
        )
        api_client.force_authenticate(admin_user)
        r = api_client.get('/api/inspections/?ordering=confidence')
        assert r.status_code == 200
        confidences = [row['confidence'] for row in r.data['results']]
        assert confidences == sorted(confidences)
