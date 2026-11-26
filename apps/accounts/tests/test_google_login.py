from unittest.mock import patch

import pytest
from django.urls import reverse
from django.test import override_settings
from google.auth.exceptions import TransportError

URL = reverse('auth-google-login')
CLIENT_ID = 'smartfactory-test-client-id'
TOKEN = 'simulated-google-id-token'


@pytest.mark.django_db
class TestGoogleLogin:
    @override_settings(GOOGLE_OAUTH_CLIENT_ID='')
    def test_server_client_id_missing_returns_503_without_verifying(self, api_client):
        with patch('google.oauth2.id_token.verify_oauth2_token') as verify:
            response = api_client.post(URL, {'credential': TOKEN}, format='json')
        assert response.status_code == 503
        verify.assert_not_called()

    @override_settings(GOOGLE_OAUTH_CLIENT_ID=CLIENT_ID)
    def test_valid_credential_returns_smartfactory_tokens(self, api_client, regular_user):
        claims = {'sub': 'google-sub-123', 'email': regular_user.email, 'email_verified': True, 'hd': 'smartfactory.tn'}
        with patch('google.oauth2.id_token.verify_oauth2_token', return_value=claims) as verify:
            response = api_client.post(URL, {'credential': TOKEN}, format='json')
        verify.assert_called_once()
        assert verify.call_args.args[0] == TOKEN
        assert verify.call_args.args[2] == CLIENT_ID
        assert response.status_code == 200
        assert {'access', 'refresh', 'user'} <= response.data.keys()
        assert response.data['user']['id'] == regular_user.id
        regular_user.refresh_from_db()
        assert regular_user.google_sub == 'google-sub-123'

    @override_settings(GOOGLE_OAUTH_CLIENT_ID=CLIENT_ID)
    @pytest.mark.parametrize('claims', [
        {'sub': 's', 'email': 'person@gmail.com', 'email_verified': True},
        {'sub': 's', 'email': 'person@gmail.com', 'email_verified': False},
        {'sub': 's', 'email': 'person@unverified.example', 'email_verified': True},
    ], ids=['expired-or-incomplete-claims', 'email-not-verified', 'non-gmail-without-workspace-domain'])
    def test_invalid_claims_are_rejected(self, api_client, claims):
        with patch('google.oauth2.id_token.verify_oauth2_token', return_value=claims):
            response = api_client.post(URL, {'credential': TOKEN}, format='json')
        assert response.status_code == 401

    @override_settings(GOOGLE_OAUTH_CLIENT_ID=CLIENT_ID)
    def test_expired_or_invalid_google_token_is_rejected(self, api_client):
        with patch('google.oauth2.id_token.verify_oauth2_token', side_effect=ValueError('expired')):
            response = api_client.post(URL, {'credential': TOKEN}, format='json')
        assert response.status_code == 401

    @override_settings(GOOGLE_OAUTH_CLIENT_ID=CLIENT_ID)
    def test_unknown_account_is_forbidden(self, api_client):
        claims = {'sub': 'unknown-sub', 'email': 'unknown@gmail.com', 'email_verified': True}
        with patch('google.oauth2.id_token.verify_oauth2_token', return_value=claims):
            response = api_client.post(URL, {'credential': TOKEN}, format='json')
        assert response.status_code == 403

    @override_settings(GOOGLE_OAUTH_CLIENT_ID=CLIENT_ID)
    def test_inactive_account_is_forbidden(self, api_client, regular_user):
        regular_user.actif = False
        regular_user.save(update_fields=['actif'])
        claims = {'sub': 'inactive-sub', 'email': regular_user.email, 'email_verified': True, 'hd': 'smartfactory.tn'}
        with patch('google.oauth2.id_token.verify_oauth2_token', return_value=claims):
            response = api_client.post(URL, {'credential': TOKEN}, format='json')
        assert response.status_code == 403

    @override_settings(GOOGLE_OAUTH_CLIENT_ID=CLIENT_ID)
    def test_google_provider_unavailable_returns_503(self, api_client):
        with patch('google.oauth2.id_token.verify_oauth2_token', side_effect=TransportError('offline')):
            response = api_client.post(URL, {'credential': TOKEN}, format='json')
        assert response.status_code == 503
