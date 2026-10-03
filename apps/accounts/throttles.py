from rest_framework.throttling import AnonRateThrottle


class LoginThrottle(AnonRateThrottle):
    """Limite les tentatives de connexion à 5 par minute par IP."""

    scope = 'login'


class PasswordResetThrottle(AnonRateThrottle):
    """Limite les demandes de réinitialisation à 3 par heure par IP."""

    scope = 'password_reset'
