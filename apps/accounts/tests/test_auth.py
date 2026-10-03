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


# ─── ADMIN CREATE USER ───────────────────────────────────────────────────────

@pytest.mark.django_db
class TestAdminCreateUser:
    def test_admin_creates_user_success(self, api_client, admin_user):
        api_client.force_authenticate(user=admin_user)
        url = reverse('admin-create-user')
        response = api_client.post(url, {
            'nom': 'Technique',
            'prenom': 'Ali',
            'email': 'ali@example.com',
            'role': 'TECHNICIEN',
        }, format='json')
        assert response.status_code == 201
        assert response.data['email'] == 'ali@example.com'
        assert response.data['role'] == 'TECHNICIEN'
        assert 'password' not in response.data
        # Mot de passe haché en base + flag must_reset_password actif
        created = User.objects.get(email='ali@example.com')
        assert created.password.startswith('bcrypt_sha256$')
        assert created.must_reset_password is True
        # Email envoyé avec les credentials + lien de login
        assert len(mail.outbox) == 1
        assert 'SmartFactory Twin' in mail.outbox[0].subject
        assert 'ali@example.com' in mail.outbox[0].body
        assert '/login' in mail.outbox[0].body

    def test_non_admin_cannot_create_user(self, api_client, regular_user):
        api_client.force_authenticate(user=regular_user)
        url = reverse('admin-create-user')
        response = api_client.post(url, {
            'nom': 'X', 'prenom': 'Y', 'email': 'x@example.com',
        }, format='json')
        assert response.status_code == 403

    def test_anonymous_cannot_create_user(self, api_client):
        url = reverse('admin-create-user')
        response = api_client.post(url, {
            'nom': 'X', 'prenom': 'Y', 'email': 'x@example.com',
        }, format='json')
        assert response.status_code == 401

    def test_first_login_forced_reset(self, api_client, admin_user):
        # L'admin crée un user → on récupère le mot de passe depuis l'email
        api_client.force_authenticate(user=admin_user)
        create_url = reverse('admin-create-user')
        api_client.post(create_url, {
            'nom': 'Technique', 'prenom': 'Ali',
            'email': 'ali@example.com', 'role': 'TECHNICIEN',
        }, format='json')
        api_client.force_authenticate(user=None)

        # Extraire le mot de passe temporaire du corps de l'email
        body = mail.outbox[0].body
        temp_password = body.split('Mot de passe temporaire : ')[1].split('\n')[0]

        login_url = reverse('auth-login')
        response = api_client.post(login_url, {
            'email': 'ali@example.com',
            'password': temp_password,
        }, format='json')
        assert response.status_code == 200
        assert response.data['must_reset_password'] is True
        assert 'uid' in response.data
        assert 'token' in response.data
        # Pas de JWT délivré tant que le mot de passe n'est pas changé
        assert 'access' not in response.data
        assert 'refresh' not in response.data

    def test_reset_confirm_clears_flag_and_enables_normal_login(self, api_client, admin_user):
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.http import urlsafe_base64_encode
        from django.utils.encoding import force_bytes

        # Création d'un user avec must_reset_password via l'API admin
        api_client.force_authenticate(user=admin_user)
        create_url = reverse('admin-create-user')
        api_client.post(create_url, {
            'nom': 'Technique', 'prenom': 'Ali',
            'email': 'ali@example.com', 'role': 'TECHNICIEN',
        }, format='json')
        api_client.force_authenticate(user=None)

        body = mail.outbox[0].body
        temp_password = body.split('Mot de passe temporaire : ')[1].split('\n')[0]

        # Premier login → uid + token de reset
        login_url = reverse('auth-login')
        login_resp = api_client.post(login_url, {
            'email': 'ali@example.com', 'password': temp_password,
        }, format='json')
        uid = login_resp.data['uid']
        token = login_resp.data['token']

        # Reset du mot de passe
        confirm_url = reverse('password-reset-confirm')
        new_password = 'NouveauMotDePasse123!'
        confirm_resp = api_client.post(confirm_url, {
            'uid': uid, 'token': token,
            'new_password': new_password,
            'new_password_confirm': new_password,
        }, format='json')
        assert confirm_resp.status_code == 200

        # Le flag est remis à False
        user = User.objects.get(email='ali@example.com')
        assert user.must_reset_password is False
        assert user.check_password(new_password) is True

        # Login normal avec le nouveau mot de passe → JWT délivré
        login_resp2 = api_client.post(login_url, {
            'email': 'ali@example.com', 'password': new_password,
        }, format='json')
        assert login_resp2.status_code == 200
        assert 'access' in login_resp2.data
        assert 'refresh' in login_resp2.data

        # L'ancien mot de passe temporaire ne fonctionne plus
        login_resp3 = api_client.post(login_url, {
            'email': 'ali@example.com', 'password': temp_password,
        }, format='json')
        assert login_resp3.status_code == 401


# ─── ADMIN LIST USERS ─────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestAdminListUsers:
    def test_admin_can_list_users(self, api_client, admin_user, regular_user):
        api_client.force_authenticate(user=admin_user)
        url = reverse('admin-list-users')
        response = api_client.get(url)
        assert response.status_code == 200
        assert response.data['count'] >= 2

    def test_non_admin_cannot_list_users(self, api_client, regular_user):
        api_client.force_authenticate(user=regular_user)
        url = reverse('admin-list-users')
        response = api_client.get(url)
        assert response.status_code == 403

    def test_anonymous_cannot_list_users(self, api_client):
        url = reverse('admin-list-users')
        response = api_client.get(url)
        assert response.status_code == 401

    def test_search_filter(self, api_client, admin_user, regular_user):
        api_client.force_authenticate(user=admin_user)
        url = reverse('admin-list-users')
        response = api_client.get(url, {'search': 'user@example.com'})
        assert response.status_code == 200
        emails = [u['email'] for u in response.data['results']]
        assert 'user@example.com' in emails

    def test_role_filter(self, api_client, admin_user, regular_user):
        api_client.force_authenticate(user=admin_user)
        url = reverse('admin-list-users')
        response = api_client.get(url, {'role': 'OPERATEUR'})
        assert response.status_code == 200
        roles = [u['role'] for u in response.data['results']]
        assert all(r == 'OPERATEUR' for r in roles)

    def test_response_contains_expected_fields(self, api_client, admin_user):
        api_client.force_authenticate(user=admin_user)
        url = reverse('admin-list-users')
        response = api_client.get(url)
        assert response.status_code == 200
        user_data = response.data['results'][0]
        for field in ['id', 'nom', 'prenom', 'email', 'role', 'role_label', 'actif', 'must_reset_password']:
            assert field in user_data


# ─── UPDATE PROFILE ───────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestUpdateProfile:
    def test_update_nom_prenom_telephone(self, api_client, regular_user):
        api_client.force_authenticate(user=regular_user)
        url = reverse('auth-update-profile')
        response = api_client.patch(url, {
            'nom': 'Benali',
            'prenom': 'Karim',
            'telephone': '+213 555 123 456',
        }, format='json')
        assert response.status_code == 200
        assert response.data['nom'] == 'Benali'
        assert response.data['prenom'] == 'Karim'
        regular_user.refresh_from_db()
        assert regular_user.nom == 'Benali'
        assert regular_user.telephone == '+213 555 123 456'

    def test_partial_update_only_telephone(self, api_client, regular_user):
        api_client.force_authenticate(user=regular_user)
        url = reverse('auth-update-profile')
        response = api_client.patch(url, {'telephone': '0555001122'}, format='json')
        assert response.status_code == 200
        regular_user.refresh_from_db()
        assert regular_user.telephone == '0555001122'

    def test_invalid_telephone_rejected(self, api_client, regular_user):
        api_client.force_authenticate(user=regular_user)
        url = reverse('auth-update-profile')
        response = api_client.patch(url, {'telephone': 'abc!!'}, format='json')
        assert response.status_code == 400

    def test_empty_nom_rejected(self, api_client, regular_user):
        api_client.force_authenticate(user=regular_user)
        url = reverse('auth-update-profile')
        response = api_client.patch(url, {'nom': '   '}, format='json')
        assert response.status_code == 400

    def test_unauthenticated_cannot_update(self, api_client):
        url = reverse('auth-update-profile')
        response = api_client.patch(url, {'nom': 'Test'}, format='json')
        assert response.status_code == 401

    def test_cannot_update_email_or_role(self, api_client, regular_user):
        """Email et rôle ne sont pas dans le serializer — ignorés silencieusement."""
        api_client.force_authenticate(user=regular_user)
        url = reverse('auth-update-profile')
        original_email = regular_user.email
        original_role  = regular_user.role
        response = api_client.patch(url, {
            'email': 'hacked@evil.com',
            'role': 'ADMIN',
            'nom': 'Test',
        }, format='json')
        assert response.status_code == 200
        regular_user.refresh_from_db()
        assert regular_user.email == original_email
        assert regular_user.role  == original_role


# ─── CHANGE PASSWORD ──────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestChangePassword:
    def test_change_password_success(self, api_client, regular_user):
        api_client.force_authenticate(user=regular_user)
        url = reverse('auth-change-password')
        response = api_client.post(url, {
            'current_password': 'User@123456',
            'new_password': 'NewSecure@789',
            'new_password_confirm': 'NewSecure@789',
        }, format='json')
        assert response.status_code == 200
        assert 'message' in response.data
        regular_user.refresh_from_db()
        assert regular_user.check_password('NewSecure@789')

    def test_wrong_current_password_rejected(self, api_client, regular_user):
        api_client.force_authenticate(user=regular_user)
        url = reverse('auth-change-password')
        response = api_client.post(url, {
            'current_password': 'WrongPassword!',
            'new_password': 'NewSecure@789',
            'new_password_confirm': 'NewSecure@789',
        }, format='json')
        assert response.status_code == 400

    def test_passwords_mismatch_rejected(self, api_client, regular_user):
        api_client.force_authenticate(user=regular_user)
        url = reverse('auth-change-password')
        response = api_client.post(url, {
            'current_password': 'User@123456',
            'new_password': 'NewSecure@789',
            'new_password_confirm': 'Different@789',
        }, format='json')
        assert response.status_code == 400

    def test_weak_new_password_rejected(self, api_client, regular_user):
        api_client.force_authenticate(user=regular_user)
        url = reverse('auth-change-password')
        response = api_client.post(url, {
            'current_password': 'User@123456',
            'new_password': '123',
            'new_password_confirm': '123',
        }, format='json')
        assert response.status_code == 400

    def test_unauthenticated_cannot_change_password(self, api_client):
        url = reverse('auth-change-password')
        response = api_client.post(url, {
            'current_password': 'anything',
            'new_password': 'NewSecure@789',
            'new_password_confirm': 'NewSecure@789',
        }, format='json')
        assert response.status_code == 401

    def test_change_password_clears_must_reset_flag(self, api_client, regular_user):
        regular_user.must_reset_password = True
        regular_user.save()
        api_client.force_authenticate(user=regular_user)
        url = reverse('auth-change-password')
        api_client.post(url, {
            'current_password': 'User@123456',
            'new_password': 'NewSecure@789',
            'new_password_confirm': 'NewSecure@789',
        }, format='json')
        regular_user.refresh_from_db()
        assert regular_user.must_reset_password is False

    def test_change_password_invalidates_refresh_tokens(self, api_client, regular_user):
        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(regular_user)
        api_client.force_authenticate(user=regular_user)
        url = reverse('auth-change-password')
        api_client.post(url, {
            'current_password': 'User@123456',
            'new_password': 'NewSecure@789',
            'new_password_confirm': 'NewSecure@789',
        }, format='json')
        refresh_url = reverse('token-refresh')
        response = api_client.post(refresh_url, {'refresh': str(refresh)}, format='json')
        assert response.status_code == 401
