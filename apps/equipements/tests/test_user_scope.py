"""Tests des périmètres d'accès (UserScope) — restriction côté BACKEND.

Scénarios imposés :
  TEST 1 : Opérateur affecté à Ligne A   → peut voir Machine A1.
  TEST 2 : Même opérateur               → ne peut PAS voir Machine B1 (Ligne B).
  TEST 3 : Opérateur affecté Ligne A+B   → voit les machines des deux lignes.
  TEST 4 : Technicien multi-périmètres  → accès aux équipements autorisés.
  TEST 5 : ADMIN                        → accès global.

Ces tests prouvent que la restriction est appliquée par l'API (et non par un
filtrage frontend) : un appel direct avec un identifiant hors périmètre échoue.
"""
import pytest

from apps.accounts.models import Utilisateur
from apps.equipements.models import (
    Usine, Zone, LigneProduction, Machine, Sensor, Reading, InspectionVisuelle,
    Composant, Document, UserScope,
)


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def media_root(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    yield


@pytest.fixture
def api_client():
    from rest_framework.test import APIClient
    return APIClient()


@pytest.fixture
def admin(db):
    return Utilisateur.objects.create_user(
        email='scope-admin@sf.tn', password='Admin@123!', role='ADMIN',
        nom='Scope', prenom='Admin',
    )


@pytest.fixture
def operateur(db):
    return Utilisateur.objects.create_user(
        email='scope-op@sf.tn', password='Op@123!', role='OPERATEUR',
        nom='Brahmi', prenom='Amine',
    )


@pytest.fixture
def technicien(db):
    return Utilisateur.objects.create_user(
        email='scope-tech@sf.tn', password='Tech@123!', role='TECHNICIEN',
        nom='Trabelsi', prenom='Yassine',
    )


@pytest.fixture
def hierarchie(db):
    """Deux usines, deux zones, deux lignes, deux machines."""
    usine_a = Usine.objects.create(nom='Usine Nord')
    zone_a = Zone.objects.create(nom='Zone Usinage', usine=usine_a)
    ligne_a = LigneProduction.objects.create(nom='Ligne CNC 01', zone=zone_a)
    machine_a1 = Machine.objects.create(
        nom='Tour CNC 1', identifiant_interne='CNC-A1', ligne_production=ligne_a,
    )
    machine_a2 = Machine.objects.create(
        nom='Tour CNC 2', identifiant_interne='CNC-A2', ligne_production=ligne_a,
    )

    usine_b = Usine.objects.create(nom='Usine Sud')
    zone_b = Zone.objects.create(nom='Zone Assemblage', usine=usine_b)
    ligne_b = LigneProduction.objects.create(nom='Ligne Assemblage 01', zone=zone_b)
    machine_b1 = Machine.objects.create(
        nom='Presse 1', identifiant_interne='PRS-B1', ligne_production=ligne_b,
    )

    return {
        'usine_a': usine_a, 'zone_a': zone_a, 'ligne_a': ligne_a,
        'machine_a1': machine_a1, 'machine_a2': machine_a2,
        'usine_b': usine_b, 'zone_b': zone_b, 'ligne_b': ligne_b,
        'machine_b1': machine_b1,
    }


def _capteur(machine, identifiant):
    return Sensor.objects.create(
        identifiant=identifiant, nom=f'Capteur {identifiant}',
        type_capteur=Sensor.SensorType.TEMPERATURE, machine=machine,
        unite='°C', frequence_mesure=60, seuil_min=0, seuil_max=100,
    )


def _mesure(capteur, valeur=50.0):
    from django.utils import timezone
    return Reading.objects.create(
        sensor=capteur, valeur=valeur, timestamp=timezone.now(),
    )


def _ids(response):
    return {row['id'] for row in response.data['results']}


# ── TEST 1 : l'opérateur voit les machines de sa ligne ────────────────────────

@pytest.mark.django_db
class TestOperateurScope:
    def test_01_opérateur_voit_machines_de_sa_ligne(self, api_client, operateur,
                                                   hierarchie):
        UserScope.objects.create(utilisateur=operateur, ligne=hierarchie['ligne_a'])
        api_client.force_authenticate(operateur)

        r = api_client.get('/api/equipements/machines/')
        assert r.status_code == 200
        assert _ids(r) == {hierarchie['machine_a1'].id, hierarchie['machine_a2'].id}
        assert r.data['count'] == 2

    def test_01b_détail_machine_de_sa_ligne_est_accesible(self, api_client, operateur,
                                                          hierarchie):
        UserScope.objects.create(utilisateur=operateur, ligne=hierarchie['ligne_a'])
        api_client.force_authenticate(operateur)

        r = api_client.get(f'/api/equipements/machines/{hierarchie["machine_a1"].id}/')
        assert r.status_code == 200

    # ── TEST 2 : aucune fuite vers une autre ligne ────────────────────────────

    def test_02_opérateur_ne_voit_pas_machine_d_autre_ligne(self, api_client,
                                                            operateur, hierarchie):
        UserScope.objects.create(utilisateur=operateur, ligne=hierarchie['ligne_a'])
        api_client.force_authenticate(operateur)

        r = api_client.get('/api/equipements/machines/')
        assert hierarchie['machine_b1'].id not in _ids(r)

    def test_02b_appel_direct_vers_machine_non_autorisée_est_refusé(self, api_client,
                                                                    operateur, hierarchie):
        """Bypass du frontend : accès direct par ID → 404."""
        UserScope.objects.create(utilisateur=operateur, ligne=hierarchie['ligne_a'])
        api_client.force_authenticate(operateur)

        r = api_client.get(f'/api/equipements/machines/{hierarchie["machine_b1"].id}/')
        assert r.status_code == 404

    def test_02c_capteurs_et_mesures_sont_aussi_filtrés(self, api_client, operateur,
                                                          hierarchie):
        capteur_a = _capteur(hierarchie['machine_a1'], 'TEMP-A1')
        capteur_b = _capteur(hierarchie['machine_b1'], 'TEMP-B1')
        _mesure(capteur_a, 42.0)
        _mesure(capteur_b, 99.0)

        UserScope.objects.create(utilisateur=operateur, ligne=hierarchie['ligne_a'])
        api_client.force_authenticate(operateur)

        r_capteurs = api_client.get('/api/equipements/capteurs/')
        assert _ids(r_capteurs) == {capteur_a.id}

        r_mesures = api_client.get('/api/equipements/readings/')
        assert len(r_mesures.data['results']) == 1
        assert r_mesures.data['results'][0]['valeur'] == 42.0

        # Appel direct sur une mesure hors périmètre → 404
        r_direct = api_client.get(f'/api/equipements/readings/{capteur_b.lectures.first().id}/')
        assert r_direct.status_code == 404

    def test_02d_filtrage_par_ligne_ne_permet_pas_de_contourner(self, api_client,
                                                                 operateur, hierarchie):
        UserScope.objects.create(utilisateur=operateur, ligne=hierarchie['ligne_a'])
        api_client.force_authenticate(operateur)

        r = api_client.get(
            f'/api/equipements/machines/?ligne_production__zone={hierarchie["zone_b"].id}'
        )
        assert r.status_code == 200
        assert r.data['count'] == 0

    def test_02e_inspections_hors_périmètre_sont_masquées(self, api_client, operateur,
                                                         hierarchie, tmp_path):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image
        import io as _io

        buf = _io.BytesIO()
        Image.new('RGB', (8, 8), (10, 20, 30)).save(buf, format='PNG')
        image = SimpleUploadedFile('a.png', buf.getvalue(), content_type='image/png')
        inspection = InspectionVisuelle.objects.create(
            machine=hierarchie['machine_b1'], utilisateur=operateur, image=image,
        )
        UserScope.objects.create(utilisateur=operateur, ligne=hierarchie['ligne_a'])
        api_client.force_authenticate(operateur)

        r = api_client.get('/api/inspections/')
        assert r.data['count'] == 0
        assert api_client.get(f'/api/inspections/{inspection.id}/').status_code == 404

    def test_02f_composants_et_documents_sont_filtrés(self, api_client, operateur,
                                                      hierarchie, tmp_path):
        """Les enfants de machine (composant/document) suivent le même périmètre."""
        from django.core.files.uploadedfile import SimpleUploadedFile

        comp_a = Composant.objects.create(nom='Moteur A', machine=hierarchie['machine_a1'])
        comp_b = Composant.objects.create(nom='Moteur B', machine=hierarchie['machine_b1'])
        doc_b = Document.objects.create(
            nom='Manuel B', type_document='MANUEL',
            machine=hierarchie['machine_b1'],
            fichier=SimpleUploadedFile('m.pdf', b'%PDF-1.4'),
        )

        UserScope.objects.create(utilisateur=operateur, ligne=hierarchie['ligne_a'])
        api_client.force_authenticate(operateur)

        r = api_client.get('/api/equipements/composants/')
        assert _ids(r) == {comp_a.id}
        assert api_client.get(f'/api/equipements/composants/{comp_b.id}/').status_code == 404

        r_doc = api_client.get('/api/equipements/documents/')
        assert _ids(r_doc) == set()
        assert api_client.get(f'/api/equipements/documents/{doc_b.id}/').status_code == 404

    def test_02g_action_composants_inline_refusee_hors_périmètre(self, api_client, operateur,
                                                                  hierarchie):
        """L'action /machines/{id}/composants/ est également protégée."""
        Composant.objects.create(nom='Moteur A', machine=hierarchie['machine_a1'])
        Composant.objects.create(nom='Moteur B', machine=hierarchie['machine_b1'])
        UserScope.objects.create(utilisateur=operateur, ligne=hierarchie['ligne_a'])
        api_client.force_authenticate(operateur)

        url_a = f'/api/equipements/machines/{hierarchie["machine_a1"].id}/composants/'
        url_b = f'/api/equipements/machines/{hierarchie["machine_b1"].id}/composants/'
        assert api_client.get(url_a).status_code == 200
        assert api_client.get(url_b).status_code == 404

    # ── TEST 3 : plusieurs lignes affectées ───────────────────────────────────

    def test_03_opérateur_affecté_à_deux_lignes(self, api_client, operateur, hierarchie):
        UserScope.objects.create(utilisateur=operateur, ligne=hierarchie['ligne_a'])
        UserScope.objects.create(utilisateur=operateur, ligne=hierarchie['ligne_b'])
        api_client.force_authenticate(operateur)

        r = api_client.get('/api/equipements/machines/')
        assert _ids(r) == {
            hierarchie['machine_a1'].id,
            hierarchie['machine_a2'].id,
            hierarchie['machine_b1'].id,
        }
        assert api_client.get(
            f'/api/equipements/machines/{hierarchie["machine_b1"].id}/'
        ).status_code == 200

    def test_03b_affectation_usine_ouvre_tout_le_sous_arbre(self, api_client, operateur,
                                                             hierarchie):
        UserScope.objects.create(utilisateur=operateur, usine=hierarchie['usine_a'])
        api_client.force_authenticate(operateur)

        r = api_client.get('/api/equipements/machines/')
        assert _ids(r) == {hierarchie['machine_a1'].id, hierarchie['machine_a2'].id}

    def test_03c_affectation_machine_ouvre_cette_machine_seule(self, api_client,
                                                                operateur, hierarchie):
        UserScope.objects.create(utilisateur=operateur,
                                 machine=hierarchie['machine_b1'])
        api_client.force_authenticate(operateur)

        r = api_client.get('/api/equipements/machines/')
        assert _ids(r) == {hierarchie['machine_b1'].id}

    def test_03d_affectation_inactive_est_ignorée(self, api_client, operateur,
                                                   hierarchie):
        UserScope.objects.create(utilisateur=operateur, ligne=hierarchie['ligne_a'],
                                 actif=False)
        api_client.force_authenticate(operateur)

        r = api_client.get('/api/equipements/machines/')
        assert r.data['count'] == 0

    def test_03e_affectation_expirée_est_ignorée(self, api_client, operateur,
                                                 hierarchie):
        from django.utils import timezone
        from datetime import timedelta
        UserScope.objects.create(
            utilisateur=operateur, ligne=hierarchie['ligne_a'],
            date_fin=timezone.now() - timedelta(days=1),
        )
        api_client.force_authenticate(operateur)

        assert api_client.get('/api/equipements/machines/').data['count'] == 0

    def test_03f_opérateur_sans_affectation_n_accède_à_rien(self, api_client,
                                                             operateur, hierarchie):
        api_client.force_authenticate(operateur)

        assert api_client.get('/api/equipements/machines/').data['count'] == 0
        assert api_client.get('/api/equipements/capteurs/').data['count'] == 0
        assert api_client.get('/api/equipements/readings/').data['count'] == 0


# ── TEST 4 : technicien multi-périmètres ─────────────────────────────────────

@pytest.mark.django_db
class TestTechnicienScope:
    def test_04_technicien_avec_zone_et_ligne(self, api_client, technicien, hierarchie):
        """Périmètre hétérogène : une zone + une ligne d'une autre zone."""
        UserScope.objects.create(utilisateur=technicien, zone=hierarchie['zone_a'])
        UserScope.objects.create(utilisateur=technicien, ligne=hierarchie['ligne_b'])
        api_client.force_authenticate(technicien)

        r = api_client.get('/api/equipements/machines/')
        assert _ids(r) == {
            hierarchie['machine_a1'].id,
            hierarchie['machine_a2'].id,
            hierarchie['machine_b1'].id,
        }

    def test_04b_technicien_restreint_ne_voit_pas_le_reste(self, api_client, technicien,
                                                             hierarchie):
        """Affecté à une zone seulement → la zone B est invisible."""
        machine_c1 = Machine.objects.create(
            nom='Laser 1', identifiant_interne='LSR-C1',
            ligne_production=hierarchie['ligne_b'],
        )
        UserScope.objects.create(utilisateur=technicien, zone=hierarchie['zone_a'])
        api_client.force_authenticate(technicien)

        r = api_client.get('/api/equipements/machines/')
        assert machine_c1.id not in _ids(r)
        assert api_client.get(
            f'/api/equipements/machines/{machine_c1.id}/'
        ).status_code == 404

    def test_04c_technicien_garde_ses_droits_de_maintenance(self, api_client, technicien,
                                                             hierarchie):
        capteur = _capteur(hierarchie['machine_a1'], 'TEMP-A1')
        UserScope.objects.create(utilisateur=technicien, zone=hierarchie['zone_a'])
        api_client.force_authenticate(technicien)

        r = api_client.patch(
            f'/api/equipements/capteurs/{capteur.id}/', {'nom': 'MAJ technicien'},
            format='json',
        )
        assert r.status_code == 200
        assert r.data['nom'] == 'MAJ technicien'

    def test_04d_technicien_sans_affectation_na_accede_a_rien(self, api_client,
                                                               technicien,
                                                               hierarchie):
        """Fail-closed : sans affectation, un technicien n'a aucun accès machine."""
        api_client.force_authenticate(technicien)

        assert api_client.get('/api/equipements/machines/').data['count'] == 0
        # Le queryset étant filtré par périmètre, la machine est « invisible »
        # pour lui : 404 (et non 403), comme pour l'opérateur hors périmètre.
        assert api_client.get(
            f'/api/equipements/machines/{hierarchie["machine_b1"].id}/'
        ).status_code == 404


# ── TEST 5 : ADMIN = accès global ────────────────────────────────────────────

@pytest.mark.django_db
class TestAdminGlobal:
    def test_05_admin_voit_tout(self, api_client, admin, operateur, hierarchie):
        UserScope.objects.create(utilisateur=operateur, ligne=hierarchie['ligne_a'])
        api_client.force_authenticate(admin)

        r = api_client.get('/api/equipements/machines/')
        assert r.data['count'] == Machine.objects.count()
        assert api_client.get(
            f'/api/equipements/machines/{hierarchie["machine_b1"].id}/'
        ).status_code == 200

    def test_05b_admin_n_a_pas_besoin_d_affectation(self, admin):
        assert not UserScope.objects.filter(utilisateur=admin).exists()


# ── Intégrité du modèle UserScope ────────────────────────────────────────────

@pytest.mark.django_db
class TestUserScopeModel:
    def test_06_une_seule_cible_par_affectation(self, operateur, hierarchie):
        """Deux cibles à la fois → refusé (contrôle applicatif + contraintes BDD)."""
        from django.core.exceptions import ValidationError
        with pytest.raises(ValidationError):
            UserScope.objects.create(
                utilisateur=operateur, zone=hierarchie['zone_a'],
                ligne=hierarchie['ligne_a'],
            )
        assert not UserScope.objects.filter(utilisateur=operateur).exists()

    def test_06b_affectation_vide_refusée(self, operateur):
        """Aucune cible → refusée."""
        from django.core.exceptions import ValidationError
        with pytest.raises(ValidationError):
            UserScope.objects.create(utilisateur=operateur)
        assert not UserScope.objects.filter(utilisateur=operateur).exists()

    def test_06c_plusieurs_affectations_autorisées(self, operateur, hierarchie):
        UserScope.objects.create(utilisateur=operateur, ligne=hierarchie['ligne_a'])
        UserScope.objects.create(utilisateur=operateur, ligne=hierarchie['ligne_b'])
        assert UserScope.objects.filter(utilisateur=operateur).count() == 2

    def test_06c2_doublon_d_affectation_refusé(self, operateur, hierarchie):
        """Unicité garantie applicativement (les NULL ne sont pas distincts en SQL)."""
        from django.core.exceptions import ValidationError
        UserScope.objects.create(utilisateur=operateur, ligne=hierarchie['ligne_a'])
        with pytest.raises(ValidationError):
            UserScope.objects.create(utilisateur=operateur,
                                     ligne=hierarchie['ligne_a'])
        assert UserScope.objects.filter(utilisateur=operateur).count() == 1

    def test_06d_est_active(self, operateur, hierarchie):
        from django.utils import timezone
        from datetime import timedelta
        scope = UserScope.objects.create(utilisateur=operateur,
                                          ligne=hierarchie['ligne_a'])
        assert scope.est_active() is True

        scope.date_fin = timezone.now() - timedelta(days=1)
        assert scope.est_active() is False

        scope.date_fin = None
        scope.actif = False
        assert scope.est_active() is False

    def test_06e_suppression_cascade_de_l_utilisateur(self, operateur, hierarchie):
        UserScope.objects.create(utilisateur=operateur, ligne=hierarchie['ligne_a'])
        user_id = operateur.id
        Utilisateur.objects.filter(id=user_id).delete()
        assert not UserScope.objects.filter(utilisateur_id=user_id).exists()

    def test_06f_suppression_cascade_de_la_ligne(self, operateur, hierarchie):
        UserScope.objects.create(utilisateur=operateur, ligne=hierarchie['ligne_a'])
        ligne_id = hierarchie['ligne_a'].id
        LigneProduction.objects.filter(id=ligne_id).delete()
        assert not UserScope.objects.filter(ligne_id=ligne_id).exists()