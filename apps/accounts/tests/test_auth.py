import pytest
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core import mail
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def user_data():
    return {
        'nom': 'Dupont',
        'prenom': 'Jean',
        'email': 'jean.dupont@example.com',
        'password': 'MonMotDePasse123',
        'password_confirm': 'MonMotDePasse123',
    }


@pytest.fixture
def admin_user(db):
    return User.objects.create_user(
        email='admin@example.com',
        password='Admin@123456',
        nom='Admin',
        prenom='Super',
        role=User.Role.ADMIN,
    )


@pytest.fixture
def regular_user(db):
    return User.objects.create_user(
        email='user@example.com',
        password='User@123456',
        nom='User',
        prenom='Regular',
        role=User.Role.OPERATEUR,
    )


# ─── REGISTER ─────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestRegister:
    def test_register_success(self, api_client, user_data):
        url = reverse('auth-register')
        response = api_client.post(url, user_data, format='json')
        assert response.status_code == 201
        assert response.data['email'] == user_data['email']
        assert response.data['role'] == 'OPERATEUR'
        assert 'password' not in response.data

    def test_register_email_already_used(self, api_client, user_data, regular_user):
        user_data['email'] = regular_user.email
        url = reverse('auth-register')
        response = api_client.post(url, user_data, format='json')
        assert response.status_code == 400

    def test_register_passwords_differ(self, api_client, user_data):
        user_data['password_confirm'] = 'DifferentPass123'
        url = reverse('auth-register')
        response = api_client.post(url, user_data, format='json')
        assert response.status_code == 400

    def test_register_weak_password(self, api_client, user_data):
        user_data['password'] = '123'
        user_data['password_confirm'] = '123'
        url = reverse('auth-register')
        response = api_client.post(url, user_data, format='json')
        assert response.status_code == 400

    def test_register_anonymous_cannot_set_admin_role(self, api_client, user_data):
        user_data['role'] = 'ADMIN'
        url = reverse('auth-register')
        response = api_client.post(url, user_data, format='json')
        assert response.status_code == 201
        assert response.data['role'] == 'OPERATEUR'

    def test_register_admin_can_create_admin(self, api_client, user_data, admin_user):
        api_client.force_authenticate(user=admin_user)
        user_data['role'] = 'ADMIN'
        url = reverse('auth-register')
        response = api_client.post(url, user_data, format='json')
        assert response.status_code == 201
        assert response.data['role'] == 'ADMIN'


# ─── LOGIN ───────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestLogin:
    def test_login_success(self, api_client, regular_user):
        url = reverse('auth-login')
        response = api_client.post(url, {
            'email': 'user@example.com',
            'password': 'User@123456',
        }, format='json')
        assert response.status_code == 200
        assert 'access' in response.data
        assert 'refresh' in response.data
        assert response.data['user']['email'] == 'user@example.com'

    def test_login_wrong_password(self, api_client, regular_user):
        url = reverse('auth-login')
        response = api_client.post(url, {
            'email': 'user@example.com',
            'password': 'WrongPassword123',
        }, format='json')
        assert response.status_code == 401

    def test_login_unknown_email(self, api_client):
        url = reverse('auth-login')
        response = api_client.post(url, {
            'email': 'unknown@example.com',
            'password': 'SomePass123',
        }, format='json')
        assert response.status_code == 401

    def test_login_inactive_account(self, api_client, regular_user):
        regular_user.actif = False
        regular_user.save()
        url = reverse('auth-login')
        response = api_client.post(url, {
            'email': 'user@example.com',
            'password': 'User@123456',
        }, format='json')
        assert response.status_code == 403


# ─── LOGOUT ──────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestLogout:
    def test_logout_success(self, api_client, regular_user):
        refresh = RefreshToken.for_user(regular_user)
        api_client.force_authenticate(user=regular_user)
        url = reverse('auth-logout')
        response = api_client.post(url, {'refresh': str(refresh)}, format='json')
        assert response.status_code == 205

    def test_logout_refresh_token_blacklisted(self, api_client, regular_user):
        refresh = RefreshToken.for_user(regular_user)
        api_client.force_authenticate(user=regular_user)
        url = reverse('auth-logout')
        api_client.post(url, {'refresh': str(refresh)}, format='json')

        # Tenter de rafraîchir avec le token blacklisté
        refresh_url = reverse('token-refresh')
        response = api_client.post(refresh_url, {'refresh': str(refresh)}, format='json')
        assert response.status_code == 401


# ─── TOKEN REFRESH ───────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestTokenRefresh:
    def test_refresh_success(self, api_client, regular_user):
        refresh = RefreshToken.for_user(regular_user)
        url = reverse('token-refresh')
        response = api_client.post(url, {'refresh': str(refresh)}, format='json')
        assert response.status_code == 200
        assert 'access' in response.data

    def test_refresh_old_token_rejected_after_rotation(self, api_client, regular_user):
        refresh = RefreshToken.for_user(regular_user)
        url = reverse('token-refresh')
        response = api_client.post(url, {'refresh': str(refresh)}, format='json')
        assert response.status_code == 200

        # L'ancien refresh token doit être refusé
        response2 = api_client.post(url, {'refresh': str(refresh)}, format='json')
        assert response2.status_code == 401


# ─── PASSWORD RESET ──────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestPasswordReset:
    def test_password_reset_existing_email(self, api_client, regular_user):
        url = reverse('password-reset')
        response = api_client.post(url, {'email': 'user@example.com'}, format='json')
        assert response.status_code == 200
        assert 'message' in response.data

    def test_password_reset_nonexistent_email(self, api_client):
        url = reverse('password-reset')
        response = api_client.post(url, {'email': 'nonexistent@example.com'}, format='json')
        assert response.status_code == 200
        assert 'message' in response.data

    def test_password_reset_email_sent(self, api_client, regular_user):
        url = reverse('password-reset')
        api_client.post(url, {'email': 'user@example.com'}, format='json')
        assert len(mail.outbox) == 1
        assert 'Réinitialisation' in mail.outbox[0].subject


# ─── PASSWORD RESET CONFIRM ──────────────────────────────────────────────────

@pytest.mark.django_db
class TestPasswordResetConfirm:
    def test_password_reset_confirm_success(self, api_client, regular_user):
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.http import urlsafe_base64_encode
        from django.utils.encoding import force_bytes

        uid = urlsafe_base64_encode(force_bytes(regular_user.pk))
        token = default_token_generator.make_token(regular_user)

        url = reverse('password-reset-confirm')
        response = api_client.post(url, {
            'uid': uid,
            'token': token,
            'new_password': 'NewPass@123456',
            'new_password_confirm': 'NewPass@123456',
        }, format='json')
        assert response.status_code == 200

        # Vérifier que le nouveau mot de passe fonctionne
        regular_user.refresh_from_db()
        assert regular_user.check_password('NewPass@123456')

    def test_password_reset_confirm_invalid_token(self, api_client, regular_user):
        from django.utils.http import urlsafe_base64_encode
        from django.utils.encoding import force_bytes

        uid = urlsafe_base64_encode(force_bytes(regular_user.pk))

        url = reverse('password-reset-confirm')
        response = api_client.post(url, {
            'uid': uid,
            'token': 'invalid-token',
            'new_password': 'NewPass@123456',
            'new_password_confirm': 'NewPass@123456',
        }, format='json')
        assert response.status_code == 400

    def test_password_reset_confirm_token_already_used(self, api_client, regular_user):
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.http import urlsafe_base64_encode
        from django.utils.encoding import force_bytes

        uid = urlsafe_base64_encode(force_bytes(regular_user.pk))
        token = default_token_generator.make_token(regular_user)

        url = reverse('password-reset-confirm')
        # Première utilisation
        api_client.post(url, {
            'uid': uid,
            'token': token,
            'new_password': 'NewPass@123456',
            'new_password_confirm': 'NewPass@123456',
        }, format='json')

        # Deuxième utilisation (doit échouer)
        response = api_client.post(url, {
            'uid': uid,
            'token': token,
            'new_password': 'AnotherPass@123',
            'new_password_confirm': 'AnotherPass@123',
        }, format='json')
        assert response.status_code == 400

    def test_password_reset_confirm_passwords_differ(self, api_client, regular_user):
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.http import urlsafe_base64_encode
        from django.utils.encoding import force_bytes

        uid = urlsafe_base64_encode(force_bytes(regular_user.pk))
        token = default_token_generator.make_token(regular_user)

        url = reverse('password-reset-confirm')
        response = api_client.post(url, {
            'uid': uid,
            'token': token,
            'new_password': 'NewPass@123456',
            'new_password_confirm': 'DifferentPass@123',
        }, format='json')
        assert response.status_code == 400

    def test_password_reset_confirm_invalidates_refresh_tokens(self, api_client, regular_user):
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.http import urlsafe_base64_encode
        from django.utils.encoding import force_bytes
        from rest_framework_simplejwt.tokens import RefreshToken

        refresh = RefreshToken.for_user(regular_user)
        uid = urlsafe_base64_encode(force_bytes(regular_user.pk))
        token = default_token_generator.make_token(regular_user)

        url = reverse('password-reset-confirm')
        api_client.post(url, {
            'uid': uid,
            'token': token,
            'new_password': 'NewPass@123456',
            'new_password_confirm': 'NewPass@123456',
        }, format='json')

        # L'ancien refresh token doit être invalide
        refresh_url = reverse('token-refresh')
        response = api_client.post(refresh_url, {'refresh': str(refresh)}, format='json')
        assert response.status_code == 401


# ─── ME ──────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestMe:
    def test_me_with_token(self, api_client, regular_user):
        api_client.force_authenticate(user=regular_user)
        url = reverse('auth-me')
        response = api_client.get(url)
        assert response.status_code == 200
        assert response.data['email'] == 'user@example.com'

    def test_me_without_token(self, api_client):
        url = reverse('auth-me')
        response = api_client.get(url)
        assert response.status_code == 401


# ─── PASSWORD HASHING ────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestPasswordHashing:
    def test_password_hashed_with_bcrypt(self, regular_user):
        assert regular_user.password.startswith('bcrypt_sha256$')
