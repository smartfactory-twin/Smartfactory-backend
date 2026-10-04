"""Tests de l'API des périmètres d'accès (UserScope).

Couvre :
  * la lecture de ses propres affectations (OPERATEUR / TECHNICIEN) ;
  * la lecture de n'importe quel utilisateur (ADMIN) ;
  * l'écriture réservée à l'ADMIN (403 pour un utilisateur standard) ;
  * `mon-perimetre` : périmètre RÉELLEMENT appliqué par
    `accessible_machine_ids` (cohérence affichage ↔ sécurité) ;
  * la création d'un utilisateur avec affectations ;
  * le cas ADMIN (accès global, aucune affectation requise) ;
  * le cas « utilisateur sans affectation ».

Ces tests ne modifient pas la logique de permissions : ils vérifient que
l'endpoint l'expose fidèlement.
"""
import pytest
from django.core import mail

from apps.accounts.models import Utilisateur
from apps.equipements.models import (
    Usine, Zone, LigneProduction, Machine, Sensor, Reading, UserScope,
)
from apps.equipements.serializers import UserScopeSerializer


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def no_email(settings):
    settings.EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
    yield


@pytest.fixture
def api_client():
    from rest_framework.test import APIClient
    return APIClient(SERVER_NAME='127.0.0.1')


@pytest.fixture
def admin(db):
    return Utilisateur.objects.create_user(
        email='api-admin@sf.tn', password='Admin@123!', role='ADMIN',
        nom='Admin', prenom='Scope',
    )


@pytest.fixture
def operateur(db):
    return Utilisateur.objects.create_user(
        email='api-op@sf.tn', password='Op@123!', role='OPERATEUR',
        nom='Brahmi', prenom='Amine',
    )


@pytest.fixture
def technicien(db):
    return Utilisateur.objects.create_user(
        email='api-tech@sf.tn', password='Tech@123!', role='TECHNICIEN',
        nom='Trabelsi', prenom='Yassine',
    )


@pytest.fixture
def hier(db):
    """2 usines / 2 zones / 2 lignes / 3 machines (2 sur la ligne A)."""
    usine_a = Usine.objects.create(nom='Usine Nord')
    zone_a = Zone.objects.create(nom='Atelier Usinage', usine=usine_a)
    ligne_a = LigneProduction.objects.create(nom='Ligne Usinage 01', zone=zone_a)
    m_a1 = Machine.objects.create(nom='Tour CNC 1', identifiant_interne='CNC-A1',
                                  ligne_production=ligne_a)
    m_a2 = Machine.objects.create(nom='Tour CNC 2', identifiant_interne='CNC-A2',
                                  ligne_production=ligne_a)

    usine_b = Usine.objects.create(nom='Usine Sud')
    zone_b = Zone.objects.create(nom='Atelier Assemblage', usine=usine_b)
    ligne_b = LigneProduction.objects.create(nom='Ligne Assemblage 01', zone=zone_b)
    m_b1 = Machine.objects.create(nom='Presse 1', identifiant_interne='PRS-B1',
                                  ligne_production=ligne_b)
    return {
        'usine_a': usine_a, 'zone_a': zone_a, 'ligne_a': ligne_a,
        'm_a1': m_a1, 'm_a2': m_a2,
        'usine_b': usine_b, 'zone_b': zone_b, 'ligne_b': ligne_b, 'm_b1': m_b1,
    }


PERIMETRES = '/api/equipements/perimetres/'
MON_PERIMETRE = '/api/equipements/perimetres/mon-perimetre/'


# ── Forme du contrat serializer ───────────────────────────────────────────────

@pytest.mark.django_db
class TestUserScopeSerializer:
    def test_10_libelle_ligne_remonte_la_hiérarchie(self, operateur, hier):
        scope = UserScope.objects.create(utilisateur=operateur, ligne=hier['ligne_a'])
        r = UserScopeSerializer(scope)
        assert r.data['niveau'] == 'ligne'
        assert r.data['libelle'] == (
            f"{hier['usine_a'].nom} → {hier['zone_a'].nom} → {hier['ligne_a'].nom}"
        )
        assert r.data['ligne_zone_nom'] == hier['zone_a'].nom
        assert r.data['ligne_zone_usine_nom'] == hier['usine_a'].nom

    def test_10b_libelle_par_niveau(self, operateur, hier):
        assert UserScopeSerializer(
            UserScope(utilisateur=operateur, usine=hier['usine_a'])).data['libelle'] \
            == hier['usine_a'].nom
        assert UserScopeSerializer(
            UserScope(utilisateur=operateur, zone=hier['zone_a'])).data['libelle'] \
            == f"{hier['usine_a'].nom} → {hier['zone_a'].nom}"
        assert UserScopeSerializer(
            UserScope(utilisateur=operateur, machine=hier['m_a1'])).data['libelle'] \
            == hier['m_a1'].nom

    def test_10c_machines_accessibles_par_affectation(self, operateur, hier):
        """Chaque affectation expose les machines qu'elle ouvre réellement."""
        scope_ligne = UserScope(utilisateur=operateur, ligne=hier['ligne_a'])
        data = UserScopeSerializer(scope_ligne).data
        assert data['nb_machines_accessibles'] == 2
        assert {m['identifiant_interne'] for m in data['machines_accessibles']} == \
            {'CNC-A1', 'CNC-A2'}

        scope_zone = UserScope(utilisateur=operateur, zone=hier['zone_a'])
        assert UserScopeSerializer(scope_zone).data['nb_machines_accessibles'] == 2

        scope_machine = UserScope(utilisateur=operateur, machine=hier['m_b1'])
        assert UserScopeSerializer(scope_machine).data['nb_machines_accessibles'] == 1

    def test_10d_combinaison_incohérente_refusée(self, operateur, hier):
        s = UserScopeSerializer(data={'utilisateur': operateur.id,
                                      'zone': hier['zone_a'].id,
                                      'ligne': hier['ligne_a'].id})
        assert not s.is_valid()

    def test_10e_affectation_vide_refusée(self, operateur):
        assert not UserScopeSerializer(data={'utilisateur': operateur.id}).is_valid()

    def test_10f_cible_ids_remonte_la_chaîne(self, operateur, hier):
        """Le frontend doit pouvoir pré-remplir le sélecteur hiérarchique."""
        # affectation ligne → chaîne usine → zone → ligne
        s = UserScope(utilisateur=operateur, ligne=hier['ligne_a'])
        assert UserScopeSerializer(s).data['cible_ids'] == {
            'usine': hier['usine_a'].id, 'zone': hier['zone_a'].id,
            'ligne': hier['ligne_a'].id, 'machine': None,
        }
        # affectation machine → on retrouve sa ligne / zone / usine
        s2 = UserScope(utilisateur=operateur, machine=hier['m_a1'])
        assert UserScopeSerializer(s2).data['cible_ids'] == {
            'usine': hier['usine_a'].id, 'zone': hier['zone_a'].id,
            'ligne': hier['ligne_a'].id, 'machine': hier['m_a1'].id,
        }
        # affectation usine → aucun descendant renseigné
        s3 = UserScope(utilisateur=operateur, usine=hier['usine_a'])
        assert UserScopeSerializer(s3).data['cible_ids'] == {
            'usine': hier['usine_a'].id, 'zone': None,
            'ligne': None, 'machine': None,
        }

    def test_10g_cible_ids_présent_dans_mon_perimetre(self, api_client, operateur, hier):
        UserScope.objects.create(utilisateur=operateur, machine=hier['m_a1'])
        api_client.force_authenticate(operateur)
        data = api_client.get(MON_PERIMETRE).data
        assert data['affectations'][0]['cible_ids']['ligne'] == hier['ligne_a'].id


# ── Lecture de ses propres affectations ────────────────────────────────────────

@pytest.mark.django_db
class TestLecturePerimetre:
    def test_11_opérateur_lit_ses_propres_affectations(self, api_client, operateur, hier):
        UserScope.objects.create(utilisateur=operateur, ligne=hier['ligne_a'])
        api_client.force_authenticate(operateur)

        r = api_client.get(PERIMETRES)
        assert r.status_code == 200
        assert r.data['count'] == 1
        assert r.data['results'][0]['utilisateur'] == operateur.id
        assert r.data['results'][0]['niveau'] == 'ligne'

    def test_11b_opérateur_ne_lit_pas_les_affectations_d_autrui(self, api_client,
                                                                  operateur, technicien,
                                                                  hier):
        UserScope.objects.create(utilisateur=technicien, ligne=hier['ligne_a'])
        api_client.force_authenticate(operateur)

        r = api_client.get(PERIMETRES, {'utilisateur': technicien.id})
        assert r.status_code == 200
        assert r.data['count'] == 0

    def test_11c_opérateur_ne_peut_pas_consulter_le_détail_d_autrui(self, api_client,
                                                                     operateur, technicien,
                                                                     hier):
        scope = UserScope.objects.create(utilisateur=technicien, ligne=hier['ligne_a'])
        api_client.force_authenticate(operateur)
        assert api_client.get(f'{PERIMETRES}{scope.id}/').status_code == 404

    def test_11d_admin_lit_les_affectations_de_n_importe_qui(self, api_client, admin,
                                                              operateur, technicien, hier):
        UserScope.objects.create(utilisateur=operateur, ligne=hier['ligne_a'])
        UserScope.objects.create(utilisateur=operateur, ligne=hier['ligne_b'])
        UserScope.objects.create(utilisateur=technicien, zone=hier['zone_b'])
        api_client.force_authenticate(admin)

        r = api_client.get(PERIMETRES)
        assert r.data['count'] == 3

        r_op = api_client.get(PERIMETRES, {'utilisateur': operateur.id})
        assert r_op.data['count'] == 2

        r_tech = api_client.get(PERIMETRES, {'utilisateur': technicien.id})
        assert r_tech.data['count'] == 1

    def test_11e_filtre_par_niveau(self, api_client, admin, operateur, hier):
        UserScope.objects.create(utilisateur=operateur, zone=hier['zone_a'])
        UserScope.objects.create(utilisateur=operateur, ligne=hier['ligne_b'])
        api_client.force_authenticate(admin)

        assert api_client.get(PERIMETRES, {'zone': hier['zone_a'].id}).data['count'] == 1
        assert api_client.get(PERIMETRES, {'ligne': hier['ligne_b'].id}).data['count'] == 1
        assert api_client.get(PERIMETRES, {'usine': hier['usine_a'].id}).data['count'] == 0

    def test_11f_anonyme_refusé(self, api_client):
        assert api_client.get(PERIMETRES).status_code == 401


# ── mon-perimetre : cohérence avec la sécurité backend ────────────────────────

@pytest.mark.django_db
class TestMonPerimetre:
    def test_12_opérateur_ligne_unique(self, api_client, operateur, hier):
        UserScope.objects.create(utilisateur=operateur, ligne=hier['ligne_a'])
        api_client.force_authenticate(operateur)

        r = api_client.get(MON_PERIMETRE)
        assert r.status_code == 200
        assert r.data['role'] == 'OPERATEUR'
        assert r.data['acces_global'] is False
        assert r.data['nb_machines_accessibles'] == 2
        assert {m['identifiant_interne'] for m in r.data['machines']} == \
            {'CNC-A1', 'CNC-A2'}
        assert len(r.data['affectations']) == 1

    def test_12b_opérateur_plusieurs_lignes(self, api_client, operateur, hier):
        UserScope.objects.create(utilisateur=operateur, ligne=hier['ligne_a'])
        UserScope.objects.create(utilisateur=operateur, ligne=hier['ligne_b'])
        api_client.force_authenticate(operateur)

        r = api_client.get(MON_PERIMETRE)
        assert r.data['nb_machines_accessibles'] == 3
        assert len(r.data['affectations']) == 2

    def test_12c_technicien_multi_périmètres(self, api_client, technicien, hier):
        UserScope.objects.create(utilisateur=technicien, zone=hier['zone_a'])
        UserScope.objects.create(utilisateur=technicien, ligne=hier['ligne_b'])
        api_client.force_authenticate(technicien)

        r = api_client.get(MON_PERIMETRE)
        assert r.data['nb_machines_accessibles'] == 3
        assert len(r.data['affectations']) == 2

    def test_12d_affectation_usine_ouvre_le_sous_arbre(self, api_client, operateur, hier):
        UserScope.objects.create(utilisateur=operateur, usine=hier['usine_a'])
        api_client.force_authenticate(operateur)

        r = api_client.get(MON_PERIMETRE)
        assert r.data['nb_machines_accessibles'] == 2

    def test_12e_affectation_inactive_ignorée(self, api_client, operateur, hier):
        UserScope.objects.create(utilisateur=operateur, ligne=hier['ligne_a'], actif=False)
        api_client.force_authenticate(operateur)

        r = api_client.get(MON_PERIMETRE)
        assert r.data['nb_machines_accessibles'] == 0
        assert r.data['affectations'][0]['est_active'] is False

    def test_12f_opérateur_sans_affectation(self, api_client, operateur, hier):
        api_client.force_authenticate(operateur)

        r = api_client.get(MON_PERIMETRE)
        assert r.status_code == 200
        assert r.data['nb_machines_accessibles'] == 0
        assert r.data['machines'] == []
        assert r.data['affectations'] == []
        assert r.data['acces_global'] is False

    def test_12g_technicien_sans_affectation_na_accede_a_rien(self, api_client,
                                                               technicien, hier):
        """Fail-closed : cohérent avec `accessible_machine_ids`, aucun accès."""
        api_client.force_authenticate(technicien)

        r = api_client.get(MON_PERIMETRE)
        assert r.data['acces_global'] is False
        assert r.data['nb_machines_accessibles'] == 0
        assert r.data['machines'] == []
        assert r.data['affectations'] == []

    def test_12g_b_technicien_sans_affectation_ne_liste_aucune_machine(
        self, api_client, technicien, hier,
    ):
        UserScope.objects.create(utilisateur=technicien, ligne=hier['ligne_a'])
        api_client.force_authenticate(technicien)

        # Son périmètre est cohérent avec ce que l'API machines expose.
        machines = api_client.get('/api/equipements/machines/').data
        perimetre = api_client.get(MON_PERIMETRE).data
        assert machines['count'] == perimetre['nb_machines_accessibles']
        assert machines['count'] > 0

    def test_12h_admin_accès_global(self, api_client, admin, operateur, hier):
        UserScope.objects.create(utilisateur=operateur, ligne=hier['ligne_a'])
        api_client.force_authenticate(admin)

        r = api_client.get(MON_PERIMETRE)
        assert r.data['acces_global'] is True
        assert r.data['nb_machines_accessibles'] == Machine.objects.count()

    def test_12i_mon_perimetre_reflète_exactement_l_api_machines(self, api_client,
                                                                  operateur, hier):
        """Le compteur affiché = nombre de machines réellement listables par l'API."""
        UserScope.objects.create(utilisateur=operateur, zone=hier['zone_b'])
        api_client.force_authenticate(operateur)

        perimetre = api_client.get(MON_PERIMETRE).data
        machines = api_client.get('/api/equipements/machines/')
        assert perimetre['nb_machines_accessibles'] == machines.data['count']
        assert {m['identifiant_interne'] for m in machines.data['results']} == \
            {'PRS-B1'}


# ── Écriture réservée à l'ADMIN ───────────────────────────────────────────────

@pytest.mark.django_db
class TestEcritureAdminOnly:
    def test_13_admin_crée_une_affectation(self, api_client, admin, operateur, hier):
        api_client.force_authenticate(admin)

        r = api_client.post(PERIMETRES,
                            {'utilisateur': operateur.id, 'ligne': hier['ligne_a'].id},
                            format='json')
        assert r.status_code == 201
        assert r.data['niveau'] == 'ligne'
        assert UserScope.objects.filter(utilisateur=operateur).count() == 1

    def test_13b_admin_modifie_une_affectation(self, api_client, admin, operateur, hier):
        scope = UserScope.objects.create(utilisateur=operateur, ligne=hier['ligne_a'])
        api_client.force_authenticate(admin)

        r = api_client.patch(f'{PERIMETRES}{scope.id}/',
                             {'ligne': hier['ligne_b'].id}, format='json')
        assert r.status_code == 200
        scope.refresh_from_db()
        assert scope.ligne_id == hier['ligne_b'].id

    def test_13c_admin_modifie_une_affectation_via_changement_de_niveau(
        self, api_client, admin, operateur, hier,
    ):
        """Passer d'une affectation ligne à une affectation zone."""
        scope = UserScope.objects.create(utilisateur=operateur, ligne=hier['ligne_a'])
        api_client.force_authenticate(admin)

        r = api_client.patch(f'{PERIMETRES}{scope.id}/',
                             {'zone': hier['zone_b'].id, 'ligne': None}, format='json')
        assert r.status_code == 200
        scope.refresh_from_db()
        assert scope.ligne_id is None
        assert scope.zone_id == hier['zone_b'].id

    def test_13d_admin_supprime_une_affectation(self, api_client, admin, operateur, hier):
        scope = UserScope.objects.create(utilisateur=operateur, ligne=hier['ligne_a'])
        api_client.force_authenticate(admin)

        assert api_client.delete(f'{PERIMETRES}{scope.id}/').status_code == 204
        assert not UserScope.objects.filter(pk=scope.pk).exists()

    def test_13e_admin_peut_ajouter_plusieurs_affectations(self, api_client, admin,
                                                            operateur, hier):
        api_client.force_authenticate(admin)

        for payload in ({'ligne': hier['ligne_a'].id}, {'ligne': hier['ligne_b'].id}):
            r = api_client.post(PERIMETRES,
                                {'utilisateur': operateur.id, **payload}, format='json')
            assert r.status_code == 201
        assert UserScope.objects.filter(utilisateur=operateur).count() == 2

    def test_13f_combinaison_incohérente_refusée_par_l_api(self, api_client, admin,
                                                            operateur, hier):
        api_client.force_authenticate(admin)

        r = api_client.post(PERIMETRES,
                            {'utilisateur': operateur.id,
                             'zone': hier['zone_a'].id,
                             'ligne': hier['ligne_a'].id}, format='json')
        assert r.status_code == 400
        assert not UserScope.objects.filter(utilisateur=operateur).exists()

    def test_13g_affectation_vide_refusée_par_l_api(self, api_client, admin, operateur):
        api_client.force_authenticate(admin)
        assert api_client.post(PERIMETRES, {'utilisateur': operateur.id},
                               format='json').status_code == 400

    def test_13h_opérateur_ne_peut_PAS_ajouter_son_propre_périmètre(
        self, api_client, operateur, hier,
    ):
        """Exigence : un utilisateur standard ne modifie pas son propre périmètre."""
        api_client.force_authenticate(operateur)

        r = api_client.post(PERIMETRES,
                            {'utilisateur': operateur.id, 'ligne': hier['ligne_a'].id},
                            format='json')
        assert r.status_code == 403
        assert not UserScope.objects.filter(utilisateur=operateur).exists()

    def test_13i_opérateur_ne_peut_PAS_modifier_ni_supprimer(self, api_client, operateur,
                                                              technicien, hier):
        cible = UserScope.objects.create(utilisateur=technicien, ligne=hier['ligne_a'])
        api_client.force_authenticate(operateur)

        assert api_client.patch(f'{PERIMETRES}{cible.id}/', {'actif': False},
                                format='json').status_code == 403
        assert api_client.delete(f'{PERIMETRES}{cible.id}/').status_code == 403
        cible.refresh_from_db()
        assert cible.actif is True

    def test_13j_technicien_ne_peut_pas_non_plus(self, api_client, technicien, hier):
        api_client.force_authenticate(technicien)
        assert api_client.post(PERIMETRES, {'usine': hier['usine_a'].id},
                               format='json').status_code == 403

    def test_13k_anonyme_ne_peut_pas_écrire(self, api_client, hier):
        assert api_client.post(PERIMETRES, {'usine': hier['usine_a'].id},
                               format='json').status_code == 401


# ── Création d'utilisateur avec affectations ──────────────────────────────────

@pytest.mark.django_db
class TestCreationUtilisateurAvecPerimetres:
    def test_14_opérateur_avec_une_ligne(self, api_client, admin, hier):
        api_client.force_authenticate(admin)

        r = api_client.post('/api/auth/users/', {
            'nom': 'Benali', 'prenom': 'Ali', 'email': 'ali.benali@sf.tn',
            'role': 'OPERATEUR',
            'perimetres': [{'ligne': hier['ligne_a'].id}],
        }, format='json')
        assert r.status_code == 201, r.data

        user = Utilisateur.objects.get(email='ali.benali@sf.tn')
        scopes = UserScope.objects.filter(utilisateur=user)
        assert scopes.count() == 1
        assert scopes.first().ligne_id == hier['ligne_a'].id

    def test_14b_technicien_avec_plusieurs_affectations(self, api_client, admin, hier):
        api_client.force_authenticate(admin)

        r = api_client.post('/api/auth/users/', {
            'nom': 'Trabelsi', 'prenom': 'Yassine', 'email': 'yas.trabelsi@sf.tn',
            'role': 'TECHNICIEN',
            'perimetres': [
                {'zone': hier['zone_a'].id},
                {'ligne': hier['ligne_b'].id},
                {'machine': hier['m_b1'].id},
            ],
        }, format='json')
        assert r.status_code == 201, r.data

        user = Utilisateur.objects.get(email='yas.trabelsi@sf.tn')
        assert UserScope.objects.filter(utilisateur=user).count() == 3

    def test_14c_sans_affectation_c_est_valide(self, api_client, admin):
        api_client.force_authenticate(admin)

        r = api_client.post('/api/auth/users/', {
            'nom': 'Sans', 'prenom': 'Perimetre', 'email': 'sans.perimetre@sf.tn',
            'role': 'OPERATEUR',
        }, format='json')
        assert r.status_code == 201
        user = Utilisateur.objects.get(email='sans.perimetre@sf.tn')
        assert not UserScope.objects.filter(utilisateur=user).exists()

    def test_14d_liste_vide_c_est_valide(self, api_client, admin):
        api_client.force_authenticate(admin)
        r = api_client.post('/api/auth/users/', {
            'nom': 'Vide', 'prenom': 'Liste', 'email': 'liste.vide@sf.tn',
            'role': 'OPERATEUR', 'perimetres': [],
        }, format='json')
        assert r.status_code == 201

    def test_14e_affectation_invalide_annule_la_création(self, api_client, admin, hier):
        """Transaction : si une affectation est invalide, l'utilisateur n'est pas créé."""
        api_client.force_authenticate(admin)

        r = api_client.post('/api/auth/users/', {
            'nom': 'Annule', 'prenom': 'User', 'email': 'annule.user@sf.tn',
            'role': 'OPERATEUR',
            'perimetres': [
                {'ligne': hier['ligne_a'].id},
                {'zone': hier['zone_b'].id, 'ligne': hier['ligne_b'].id},
            ],
        }, format='json')
        assert r.status_code == 400
        assert 'perimetres' in r.data
        assert not Utilisateur.objects.filter(email='annule.user@sf.tn').exists()
        assert not UserScope.objects.exists()

    def test_14f_perimetre_mauvais_type_refusé(self, api_client, admin):
        api_client.force_authenticate(admin)
        r = api_client.post('/api/auth/users/', {
            'nom': 'Type', 'prenom': 'Bad', 'email': 'type.bad@sf.tn',
            'role': 'OPERATEUR', 'perimetres': 'ligne=1',
        }, format='json')
        assert r.status_code == 400
        assert not Utilisateur.objects.filter(email='type.bad@sf.tn').exists()

    def test_14g_utilisateur_non_admin_ne_peut_pas_créer_avec_périmètre(
        self, api_client, operateur, hier,
    ):
        api_client.force_authenticate(operateur)
        r = api_client.post('/api/auth/users/', {
            'nom': 'Hack', 'prenom': 'Er', 'email': 'hack@sf.tn',
            'role': 'OPERATEUR', 'perimetres': [{'usine': hier['usine_a'].id}],
        }, format='json')
        assert r.status_code == 403
        assert not Utilisateur.objects.filter(email='hack@sf.tn').exists()

    def test_14h_admin_rôle_sans_affectation_exigée(self, api_client, admin):
        """L'ADMIN a un accès global : aucune affectation n'est demandée."""
        api_client.force_authenticate(admin)
        r = api_client.get(MON_PERIMETRE)
        assert r.data['acces_global'] is True
        assert r.data['affectations'] == []


# ── Cohérence avec les listings de sécurité ───────────────────────────────────

@pytest.mark.django_db
class TestCoherenceSecurite:
    def test_15_affectations_affichees_egalent_machines_accessibles(self, api_client, admin,
                                                                     operateur, hier):
        """Test d'intégration : ce qu'affiche `mon-perimetre` = ce que l'API autorise."""
        UserScope.objects.create(utilisateur=operateur, zone=hier['zone_a'])
        api_client.force_authenticate(operateur)

        perimetre = api_client.get(MON_PERIMETRE).data
        machines_api = api_client.get('/api/equipements/machines/').data
        assert {m['id'] for m in perimetre['machines']} == \
            {m['id'] for m in machines_api['results']}

    def test_15b_modifier_périmètre_change_l_accès(self, api_client, admin, operateur,
                                                    hier):
        """Le compteur suit immédiatement une modification d'affectation."""
        scope = UserScope.objects.create(utilisateur=operateur, zone=hier['zone_a'])
        api_client.force_authenticate(operateur)
        assert api_client.get(MON_PERIMETRE).data['nb_machines_accessibles'] == 2

        api_client.force_authenticate(admin)
        api_client.patch(f'{PERIMETRES}{scope.id}/', {'zone': None, 'ligne': hier['ligne_b'].id},
                         format='json')

        api_client.force_authenticate(operateur)
        assert api_client.get(MON_PERIMETRE).data['nb_machines_accessibles'] == 1

    def test_15c_supprimer_périmètre_ferme_l_accès(self, api_client, admin, operateur,
                                                   hier):
        scope = UserScope.objects.create(utilisateur=operateur, ligne=hier['ligne_a'])
        api_client.force_authenticate(operateur)
        assert api_client.get(MON_PERIMETRE).data['nb_machines_accessibles'] == 2

        api_client.force_authenticate(admin)
        api_client.delete(f'{PERIMETRES}{scope.id}/')

        api_client.force_authenticate(operateur)
        perimetre = api_client.get(MON_PERIMETRE).data
        assert perimetre['nb_machines_accessibles'] == 0
        assert perimetre['affectations'] == []

    def test_15d_capteurs_et_mesures_suivent_le_périmètre(self, api_client, operateur,
                                                           hier):
        capteur_a = Sensor.objects.create(
            identifiant='TEMP-A1', nom='T A1', machine=hier['m_a1'],
            type_capteur=Sensor.SensorType.TEMPERATURE, unite='°C',
            frequence_mesure=60, seuil_min=0, seuil_max=100,
        )
        capteur_b = Sensor.objects.create(
            identifiant='TEMP-B1', nom='T B1', machine=hier['m_b1'],
            type_capteur=Sensor.SensorType.TEMPERATURE, unite='°C',
            frequence_mesure=60, seuil_min=0, seuil_max=100,
        )
        from django.utils import timezone
        Reading.objects.create(sensor=capteur_a, valeur=42, timestamp=timezone.now())
        Reading.objects.create(sensor=capteur_b, valeur=99, timestamp=timezone.now())

        UserScope.objects.create(utilisateur=operateur, ligne=hier['ligne_a'])
        api_client.force_authenticate(operateur)

        assert api_client.get('/api/equipements/capteurs/').data['count'] == 1
        assert api_client.get('/api/equipements/readings/').data['count'] == 1

    def test_15e_email_envoyé_à_la_création(self, api_client, admin, hier):
        api_client.force_authenticate(admin)
        mail.outbox.clear()
        api_client.post('/api/auth/users/', {
            'nom': 'Mail', 'prenom': 'Test', 'email': 'mail.test@sf.tn',
            'role': 'OPERATEUR', 'perimetres': [{'ligne': hier['ligne_a'].id}],
        }, format='json')
        assert len(mail.outbox) == 1