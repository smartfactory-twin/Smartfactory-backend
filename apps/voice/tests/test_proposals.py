import json
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import AuditLog, Utilisateur
from apps.alertes.models import Alerte
from apps.equipements.models import Machine, Sensor, UserScope
from apps.voice.models import VoiceActionProposal, VoiceAgentRequest


class ScriptedLLM:
    def __init__(self, *responses):
        self.responses = list(responses)

    def complete(self, messages, tools, timeout=None):
        return self.responses.pop(0)


def client_for(user):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {RefreshToken.for_user(user).access_token}')
    return client


def tool_response(name, params):
    return {'tool_calls': [{
        'id': 'write-1', 'type': 'function',
        'function': {'name': name, 'arguments': json.dumps(params)},
    }]}


@pytest.fixture
def proposal_setup(db):
    admin = Utilisateur.objects.create_user(
        email='proposal-admin@test.local', password='Test@123456', role='ADMIN',
        nom='Admin', prenom='Proposal',
    )
    tech = Utilisateur.objects.create_user(
        email='proposal-tech@test.local', password='Test@123456', role='TECHNICIEN',
        nom='Tech', prenom='Proposal',
    )
    other = Utilisateur.objects.create_user(
        email='proposal-other@test.local', password='Test@123456', role='ADMIN',
        nom='Other', prenom='Proposal',
    )
    machine = Machine.objects.create(nom='Pompe test', identifiant_interne='POMPE-PROP')
    hidden = Machine.objects.create(nom='Presse test', identifiant_interne='PRESSE-PROP')
    sensor = Sensor.objects.create(
        identifiant='TEMP-PROP', nom='Température test', type_capteur='TEMPERATURE',
        machine=machine, unite='°C', frequence_mesure=60, seuil_min=0, seuil_max=80,
    )
    UserScope.objects.create(utilisateur=tech, machine=machine)
    alert = Alerte.objects.create(
        machine=machine, capteur=sensor, valeur=90, seuil=80, unite='°C',
        message='Seuil dépassé', derniere_occurrence=timezone.now(),
        date_declenchement=timezone.now(),
    )
    return {'admin': admin, 'tech': tech, 'other': other, 'machine': machine,
            'hidden': hidden, 'sensor': sensor, 'alert': alert}


def install(monkeypatch, fake):
    monkeypatch.setattr('apps.voice.views.get_llm_client', lambda: fake)


@pytest.mark.django_db
def test_write_tool_only_proposes_and_explicit_endpoint_executes_once(proposal_setup, monkeypatch):
    from apps.voice.views import VoiceAgentAPIView

    fake = ScriptedLLM(tool_response('acknowledge_alert', {
        'alert_id': proposal_setup['alert'].pk, 'comment': 'Pièce remplacée',
    }))
    install(monkeypatch, fake)
    client = client_for(proposal_setup['tech'])
    response = client.post('/api/voice/agent/', {
        'message': 'Acquitte cette alerte avec pièce remplacée', 'interaction_mode': 'voice',
    }, format='json')
    assert response.status_code == 200, response.data
    proposal_id = response.data['proposal']['id']
    proposal_setup['alert'].refresh_from_db()
    assert proposal_setup['alert'].statut == Alerte.Statut.ACTIVE
    assert proposal_setup['alert'].commentaire_acquittement == ''
    assert VoiceAgentRequest.objects.latest('pk').interaction_mode == 'voice'

    confirmed = client.post(f'/api/voice/proposals/{proposal_id}/confirm/', {}, format='json')
    assert confirmed.status_code == 200, confirmed.data
    proposal_setup['alert'].refresh_from_db()
    assert proposal_setup['alert'].statut == Alerte.Statut.ACKNOWLEDGED
    assert proposal_setup['alert'].commentaire_acquittement == 'Pièce remplacée'
    assert VoiceActionProposal.objects.get(pk=proposal_id).statut == VoiceActionProposal.Status.EXECUTED
    assert AuditLog.objects.filter(acteur=proposal_setup['tech'], chemin=f'/api/alertes/{proposal_setup["alert"].pk}/acquitter/').exists()
    assert client.post(f'/api/voice/proposals/{proposal_id}/confirm/', {}, format='json').status_code == 409


@pytest.mark.django_db
def test_proposal_is_private_expiring_and_cancellable(proposal_setup, monkeypatch):
    fake = ScriptedLLM(tool_response('acknowledge_alert', {
        'alert_id': proposal_setup['alert'].pk, 'comment': 'Contrôle terminé',
    }))
    install(monkeypatch, fake)
    client = client_for(proposal_setup['admin'])
    response = client.post('/api/voice/agent/', {'message': 'Acquitte alerte'}, format='json')
    proposal_id = response.data['proposal']['id']
    assert client_for(proposal_setup['other']).post(
        f'/api/voice/proposals/{proposal_id}/confirm/', {}, format='json',
    ).status_code == 404
    assert len(client.get('/api/voice/proposals/pending/').data['results']) == 1

    proposal = VoiceActionProposal.objects.get(pk=proposal_id)
    proposal.expires_at = timezone.now() - timedelta(seconds=1)
    proposal.save(update_fields=['expires_at'])
    assert client.post(f'/api/voice/proposals/{proposal_id}/confirm/', {}, format='json').status_code == 410
    proposal.refresh_from_db()
    assert proposal.statut == VoiceActionProposal.Status.EXPIRED


@pytest.mark.django_db
def test_cancelled_proposal_cannot_be_confirmed(proposal_setup, monkeypatch):
    fake = ScriptedLLM(tool_response('acknowledge_alert', {
        'alert_id': proposal_setup['alert'].pk, 'comment': 'test annulation',
    }))
    install(monkeypatch, fake)
    client = client_for(proposal_setup['admin'])
    created = client.post('/api/voice/agent/', {'message': 'Acquitte alerte'}, format='json')
    assert created.status_code == 200, created.data
    proposal_id = created.data['proposal']['id']

    cancelled = client.post(f'/api/voice/proposals/{proposal_id}/cancel/', {}, format='json')
    assert cancelled.status_code == 200, cancelled.data
    assert cancelled.data['proposal']['status'] == VoiceActionProposal.Status.CANCELLED

    refused = client.post(f'/api/voice/proposals/{proposal_id}/confirm/', {}, format='json')
    assert refused.status_code == 409
    proposal_setup['alert'].refresh_from_db()
    assert proposal_setup['alert'].statut == Alerte.Statut.ACTIVE


@pytest.mark.django_db
def test_saying_yes_never_confirms_a_pending_proposal(proposal_setup, monkeypatch):
    fake = ScriptedLLM(tool_response('acknowledge_alert', {
        'alert_id': proposal_setup['alert'].pk, 'comment': 'Contrôle terminé',
    }))
    install(monkeypatch, fake)
    client = client_for(proposal_setup['admin'])
    response = client.post('/api/voice/agent/', {'message': 'Acquitte cette alerte'}, format='json')
    proposal_id = response.data['proposal']['id']
    yes = client.post('/api/voice/agent/', {
        'message': 'oui', 'conversation_id': response.data['conversation_id'], 'interaction_mode': 'voice',
    }, format='json')
    assert yes.status_code == 200
    assert 'confirmation' in yes.data['reply'].lower()
    proposal_setup['alert'].refresh_from_db()
    assert proposal_setup['alert'].statut == Alerte.Statut.ACTIVE
    assert VoiceActionProposal.objects.get(pk=proposal_id).statut == VoiceActionProposal.Status.PENDING


@pytest.mark.django_db
def test_create_work_order_proposal_refuses_operator_and_out_of_scope(proposal_setup, monkeypatch):
    operator = Utilisateur.objects.create_user(
        email='proposal-operator@test.local', password='Test@123456', role='OPERATEUR',
        nom='Operator', prenom='Proposal',
    )
    fake = ScriptedLLM(tool_response('create_work_order', {
        'machine_id': proposal_setup['machine'].pk, 'type': 'Corrective',
        'priority': 'Haute', 'title': 'Remplacer joint',
    }), {'content': 'Action refusée.'})
    install(monkeypatch, fake)
    response = client_for(operator).post('/api/voice/agent/', {'message': 'Crée un OT'}, format='json')
    assert response.status_code == 200
    assert VoiceActionProposal.objects.count() == 0
    assert not proposal_setup['machine'].ordres_travail.exists()

    fake2 = ScriptedLLM(tool_response('create_work_order', {
        'machine_id': proposal_setup['hidden'].pk, 'type': 'Corrective',
        'priority': 'Haute', 'title': 'Intervention hors scope',
    }), {'content': 'Machine inaccessible.'})
    install(monkeypatch, fake2)
    denied = client_for(proposal_setup['tech']).post('/api/voice/agent/', {'message': 'Crée un OT'}, format='json')
    assert denied.status_code == 200
    assert VoiceActionProposal.objects.count() == 0


@pytest.mark.django_db
def test_tampered_proposal_hash_fails_without_business_write(proposal_setup, monkeypatch):
    from apps.voice.proposals import create_proposal
    from apps.voice.views import VoiceAgentAPIView

    client = client_for(proposal_setup['admin'])
    conversation, _ = VoiceAgentAPIView._conversation(proposal_setup['admin'], None)
    request = type('Request', (), {
        'user': proposal_setup['admin'], 'headers': {'Authorization': client._credentials['HTTP_AUTHORIZATION']},
        'META': {},
    })()
    proposal, _, _ = create_proposal(request, conversation, 'acknowledge_alert', {
        'alert_id': proposal_setup['alert'].pk, 'comment': 'Texte original',
    })
    proposal.parametres['commentaire'] = 'altéré'
    proposal.save(update_fields=['parametres'])
    response = client.post(f'/api/voice/proposals/{proposal.pk}/confirm/', {}, format='json')
    assert response.status_code == 409
    proposal_setup['alert'].refresh_from_db()
    assert proposal_setup['alert'].statut == Alerte.Statut.ACTIVE
