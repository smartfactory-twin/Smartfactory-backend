import asyncio

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.test import AsyncClient
from rest_framework.test import APIClient

from apps.accounts.models import AuditLog

User = get_user_model()


@pytest.fixture
def audit_users(db):
    return {
        'admin': User.objects.create_user(
            email='audit-admin@example.test', password='Admin@123456',
            nom='Audit', prenom='Admin', role=User.Role.ADMIN,
        ),
        'operator': User.objects.create_user(
            email='audit-operator@example.test', password='Operator@123456',
            nom='Audit', prenom='Operator', role=User.Role.OPERATEUR,
        ),
    }


@pytest.mark.django_db
def test_api_mutation_is_recorded_with_actor_and_response(audit_users):
    client = APIClient()
    client.force_authenticate(user=audit_users['operator'])

    response = client.post(reverse('vocal-command-history'), {
        'texte': 'Afficher les alertes', 'intention': 'LIST_ALERTS',
        'confiance': 0.9, 'resultat': 'success',
    }, format='json')

    assert response.status_code == 201
    event = AuditLog.objects.get(methode='POST', chemin='/api/auth/vocal/commands/')
    assert event.acteur == audit_users['operator']
    assert event.acteur_email == audit_users['operator'].email
    assert event.acteur_role == 'OPERATEUR'
    assert event.code_http == 201
    assert 'body' not in event.details


@pytest.mark.django_db
def test_audit_does_not_store_request_credentials():
    client = APIClient()
    response = client.post(reverse('auth-register'), {
        'nom': 'Test', 'prenom': 'Secret', 'email': 'secret@example.test',
        'password': 'SecretPass123!', 'password_confirm': 'SecretPass123!',
    }, format='json')

    assert response.status_code == 201
    event = AuditLog.objects.get(chemin='/api/auth/register/')
    assert 'SecretPass123!' not in str(event.details)
    assert 'password' not in str(event.details).lower()


@pytest.mark.django_db
def test_audit_log_endpoint_is_admin_only_and_read_only(audit_users):
    AuditLog.objects.create(
        acteur_email='operator@example.test', action='POST example',
        methode='POST', chemin='/api/example/', code_http=201,
    )
    client = APIClient()
    url = reverse('audit-log-list')

    client.force_authenticate(user=audit_users['operator'])
    assert client.get(url).status_code == 403

    client.force_authenticate(user=audit_users['admin'])
    response = client.get(url)
    assert response.status_code == 200
    assert response.data['count'] == 1
    assert response.data['results'][0]['action'] == 'POST example'
    assert client.post(url, {}, format='json').status_code == 405


@pytest.mark.django_db
def test_non_api_reads_are_not_recorded(audit_users):
    client = APIClient()
    client.force_authenticate(user=audit_users['admin'])
    before = AuditLog.objects.count()

    response = client.get(reverse('auth-me'))

    assert response.status_code == 200
    assert AuditLog.objects.count() == before


@pytest.mark.django_db
def test_admin_login_attempt_is_recorded_without_password():
    client = APIClient()
    client.raise_request_exception = False
    client.post('/admin/login/', {'username': 'unknown', 'password': 'DoNotPersist-123'})

    event = AuditLog.objects.filter(chemin='/admin/login/').latest('cree_le')
    assert event.acteur is None
    assert event.code_http in (200, 302)
    assert 'DoNotPersist-123' not in str(event.details)


@pytest.mark.django_db(transaction=True)
def test_async_api_request_is_audited_without_breaking_the_response():
    async def make_request():
        client = AsyncClient()
        return await client.post('/api/auth/login/', {
            'email': 'missing@example.test', 'password': 'not-a-real-password',
        })

    response = asyncio.run(make_request())

    assert response.status_code == 401
    event = AuditLog.objects.get(chemin='/api/auth/login/')
    assert event.code_http == 401
