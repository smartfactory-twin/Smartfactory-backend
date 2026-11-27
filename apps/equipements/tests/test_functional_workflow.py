import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.equipements.models import (
    LigneProduction, Machine, OrdreTravail, Usine, UserScope, Zone,
)


@pytest.mark.django_db
def test_work_order_workflow_requires_valid_transitions_and_preserves_history():
    admin = Utilisateur.objects.create_user(
        email='workflow-admin@example.test', password='Admin@123456',
        nom='Admin', prenom='Workflow', role=Utilisateur.Role.ADMIN,
    )
    technician = Utilisateur.objects.create_user(
        email='workflow-tech@example.test', password='Tech@123456',
        nom='Tech', prenom='Workflow', role=Utilisateur.Role.TECHNICIEN,
    )
    usine = Usine.objects.create(nom='Usine workflow')
    zone = Zone.objects.create(nom='Zone workflow', usine=usine)
    ligne = LigneProduction.objects.create(nom='Ligne workflow', zone=zone)
    machine = Machine.objects.create(
        nom='Machine workflow', identifiant_interne='E2E-WORKFLOW-001',
        ligne_production=ligne,
    )
    UserScope.objects.create(utilisateur=technician, machine=machine)
    client = APIClient()

    client.force_authenticate(user=technician)
    created = client.post('/api/equipements/ordres-travail/', {
        'machine_id': machine.id,
        'titre': 'Vérifier la pompe',
        'assigne': 'Technicien Workflow',
        'priorite': OrdreTravail.Priorite.HAUTE,
    }, format='json')

    assert created.status_code == 201, created.data
    order_id = created.data['id']
    assert created.data['statut'] == OrdreTravail.Statut.ASSIGNE
    assert len(created.data['historique']) == 1

    # Le workflow ne permet pas de sauter directement de « Assigné » à « Validé ».
    skipped = client.patch(
        f'/api/equipements/ordres-travail/{order_id}/',
        {'statut': OrdreTravail.Statut.VALIDE}, format='json',
    )
    assert skipped.status_code == 400
    order = OrdreTravail.objects.get(pk=order_id)
    assert order.statut == OrdreTravail.Statut.ASSIGNE
    assert len(order.historique) == 1

    started = client.patch(
        f'/api/equipements/ordres-travail/{order_id}/',
        {'statut': OrdreTravail.Statut.EN_COURS}, format='json',
    )
    assert started.status_code == 200, started.data
    assert started.data['statut'] == OrdreTravail.Statut.EN_COURS
    assert [step['statut'] for step in started.data['historique']] == [
        OrdreTravail.Statut.ASSIGNE,
        OrdreTravail.Statut.EN_COURS,
    ]

    # Le dépôt du rapport est l’étape métier suivante après les travaux.
    report = client.post(f'/api/equipements/ordres-travail/{order_id}/rapport/', {
        'travaux': 'Joint remplacé et essai effectué',
        'duree': 1.5,
        'signataire': 'Technicien Workflow',
        'pieces': [{'ref': 'JOINT-001', 'qte': 1, 'cout': 12.5}],
    }, format='json')
    assert report.status_code == 200, report.data
    assert report.data['statut'] == OrdreTravail.Statut.RAPPORT_DEPOSE
    assert report.data['rapport']['travaux'] == 'Joint remplacé et essai effectué'
    assert [step['statut'] for step in report.data['historique']] == [
        OrdreTravail.Statut.ASSIGNE,
        OrdreTravail.Statut.EN_COURS,
        OrdreTravail.Statut.RAPPORT_DEPOSE,
    ]

    # Un technicien peut déposer son rapport, mais seule l’administration peut valider.
    forbidden_validation = client.patch(
        f'/api/equipements/ordres-travail/{order_id}/',
        {'statut': OrdreTravail.Statut.VALIDE}, format='json',
    )
    assert forbidden_validation.status_code == 400
    assert OrdreTravail.objects.get(pk=order_id).statut == OrdreTravail.Statut.RAPPORT_DEPOSE

    client.force_authenticate(user=admin)
    validated = client.patch(
        f'/api/equipements/ordres-travail/{order_id}/',
        {'statut': OrdreTravail.Statut.VALIDE}, format='json',
    )
    assert validated.status_code == 200, validated.data
    assert validated.data['statut'] == OrdreTravail.Statut.VALIDE
    assert validated.data['historique'][-1]['statut'] == OrdreTravail.Statut.VALIDE
