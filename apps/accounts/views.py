from rest_framework import status, generics
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.throttling import AnonRateThrottle
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from drf_spectacular.utils import extend_schema, OpenApiExample, OpenApiResponse
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.conf import settings
from django.db import transaction
import secrets
import string

from .serializers import (
    CustomTokenObtainPairSerializer,
    RegisterSerializer,
    UserSerializer,
    PasswordResetSerializer,
    PasswordResetConfirmSerializer,
    LogoutSerializer,
    AdminUserCreateSerializer,
    AdminUserListSerializer,
    UpdateProfileSerializer,
    ChangePasswordSerializer,
)
from .permissions import IsAdmin
from .throttles import LoginThrottle, PasswordResetThrottle
from .email_utils import send_html_email, LOGO_CID

User = get_user_model()


# Champs d'affectation acceptés dans le payload `perimetres`.
_SCOPE_TARGETS = ('usine', 'zone', 'ligne', 'machine')


class PerimetreInvalide(Exception):
    """Signale une affectation refusée ; utilisé pour annuler la transaction."""

    def __init__(self, message):
        super().__init__(message)
        self.message = message


def _valider_perimetres(perimetres):
    """Valide le payload `perimetres` SANS rien créer.

    Format : [{ "usine": 1 }, { "zone": 2 }, { "ligne": 3 }, { "machine": 4 }]
    Retourne (liste de payloads, None) ou (None, message d'erreur).
    """
    from apps.equipements.serializers import UserScopeSerializer

    if not perimetres:  # liste vide = aucune affectation demandée
        return [], None

    payloads = []
    for index, item in enumerate(perimetres):
        if not isinstance(item, dict):
            return None, f"Affectation #{index + 1} : format invalide (objet attendu)."

        payload = {k: v for k, v in item.items()
                   if k in _SCOPE_TARGETS and v not in (None, '')}
        if len(payload) != 1:
            return None, (f"Affectation #{index + 1} : renseignez exactement un niveau "
                          f"parmi {', '.join(_SCOPE_TARGETS)}.")

        # `partial=True` : `utilisateur` sera renseigné à la création de l'user,
        # les 4 niveaux cibles étant de toute façon optionnels.
        serializer = UserScopeSerializer(data=payload, partial=True)
        if not serializer.is_valid():
            messages = '; '.join(
                f"{k} : {v[0] if isinstance(v, list) else v}"
                for k, v in serializer.errors.items()
            )
            return None, f"Affectation #{index + 1} : {messages}"
        payloads.append(payload)
    return payloads, None


def _appliquer_perimetres(user, payloads):
    """Crée les `UserScope`. Lève `PerimetreInvalide` pour annuler la transaction."""
    from apps.equipements.serializers import UserScopeSerializer

    for index, payload in enumerate(payloads):
        serializer = UserScopeSerializer(
            data={'utilisateur': user.id, **payload}
        )
        if not serializer.is_valid():
            raise PerimetreInvalide(f"Affectation #{index + 1} : invalide.")
        try:
            serializer.save()
        except Exception as exc:  # doublon, contrainte BDD…
            raise PerimetreInvalide(f"Affectation #{index + 1} : {exc}")


def generate_strong_password(length: int = 14) -> str:
    """Génère un mot de passe aléatoire fort (lettres + chiffres + symboles)."""
    alphabet = string.ascii_letters + string.digits + string.punctuation
    # Garantir au moins une lettre, un chiffre et un symbole pour les validateurs
    while True:
        password = ''.join(secrets.choice(alphabet) for _ in range(length))
        if (
            any(c.isalpha() for c in password)
            and any(c.isdigit() for c in password)
            and any(c in string.punctuation for c in password)
        ):
            return password


# ─── Login ────────────────────────────────────────────────────────────────────
@extend_schema(
    tags=['Authentification'],
    summary='Connexion utilisateur',
    description="Authentifie un utilisateur avec email + mot de passe et retourne un token JWT (access + refresh).",
    examples=[
        OpenApiExample(
            'Exemple de requête',
            value={'email': 'user@example.com', 'password': 'MonMotDePasse123'},
            request_only=True,
        ),
        OpenApiExample(
            'Exemple de réponse (200)',
            value={
                'access': 'eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...',
                'refresh': 'eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...',
                'user': {
                    'id': 1,
                    'nom': 'Dupont',
                    'prenom': 'Jean',
                    'email': 'user@example.com',
                    'role': 'OPERATEUR',
                    'role_label': 'Opérateur',
                },
            },
            response_only=True,
        ),
        OpenApiExample(
            'Premier login — changement de mot de passe requis (200, sans JWT)',
            value={
                'must_reset_password': True,
                'uid': 'MQ',
                'token': 'abc123-def456',
                'detail': 'Vous devez changer votre mot de passe avant de continuer.',
            },
            response_only=True,
        ),
    ],
    responses={
        200: OpenApiResponse(description='Connexion réussie'),
        401: OpenApiResponse(description='Identifiants invalides'),
        403: OpenApiResponse(description='Compte inactif'),
    },
)
class LoginView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer
    permission_classes = [AllowAny]
    throttle_classes = [LoginThrottle]

    def post(self, request, *args, **kwargs):
        email = request.data.get('email', '').lower()
        password = request.data.get('password', '')

        try:
            candidate = User.objects.get(email=email)
            if candidate.check_password(password):
                # Forçage du changement de mot de passe au premier login
                if candidate.must_reset_password:
                    # Vérifier si le délai de 48h a expiré
                    if candidate.is_temp_password_expired:
                        if candidate.actif:
                            candidate.actif = False
                            candidate.save(update_fields=['actif'])
                        return Response(
                            {
                                'error': 'Le délai de 48 heures pour définir votre mot de passe a expiré. Votre compte est inactif. Veuillez contacter un administrateur.'
                            },
                            status=status.HTTP_403_FORBIDDEN
                        )
                    # Premier login autorisé dans le délai de 48h
                    uid = urlsafe_base64_encode(force_bytes(candidate.pk))
                    token = default_token_generator.make_token(candidate)
                    return Response(
                        {
                            'must_reset_password': True,
                            'uid': uid,
                            'token': token,
                            'detail': 'Vous devez changer votre mot de passe avant de continuer.',
                        },
                        status=status.HTTP_200_OK
                    )

                # Compte inactif classique
                if not candidate.actif:
                    return Response(
                        {'error': 'Ce compte est inactif. Contactez un administrateur.'},
                        status=status.HTTP_403_FORBIDDEN
                    )
        except User.DoesNotExist:
            pass

        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except Exception:
            return Response(
                {'error': 'Identifiants invalides.'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        return Response(serializer.validated_data, status=status.HTTP_200_OK)



# ─── Logout ───────────────────────────────────────────────────────────────────
@extend_schema(
    tags=['Authentification'],
    summary='Déconnexion utilisateur',
    description="Invalide le refresh token (blacklist) pour déconnecter l'utilisateur.",
    request=LogoutSerializer,
    examples=[
        OpenApiExample(
            'Exemple de requête',
            value={'refresh': 'eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...'},
            request_only=True,
        ),
    ],
    responses={
        205: OpenApiResponse(description='Déconnexion réussie'),
        400: OpenApiResponse(description='Token invalide ou manquant'),
    },
)
class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get('refresh')
        if not refresh_token:
            return Response(
                {'error': 'Le refresh token est requis.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response(
                {'message': 'Déconnexion réussie.'},
                status=status.HTTP_205_RESET_CONTENT
            )
        except TokenError:
            return Response(
                {'error': 'Token invalide ou déjà révoqué.'},
                status=status.HTTP_400_BAD_REQUEST
            )


# ─── Token Refresh ────────────────────────────────────────────────────────────
@extend_schema(
    tags=['Authentification'],
    summary='Rafraîchir le token d\'accès',
    description="Rafraîchit l'access token. L'ancien refresh token est blacklisté (rotation).",
    examples=[
        OpenApiExample(
            'Exemple de requête',
            value={'refresh': 'eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...'},
            request_only=True,
        ),
        OpenApiExample(
            'Exemple de réponse (200)',
            value={'access': 'eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...'},
            response_only=True,
        ),
    ],
    responses={
        200: OpenApiResponse(description='Token rafraîchi'),
        401: OpenApiResponse(description='Token invalide ou expiré'),
    },
)
class CustomTokenRefreshView(TokenRefreshView):
    permission_classes = [AllowAny]


# ─── Inscription ──────────────────────────────────────────────────────────────
@extend_schema(
    tags=['Authentification'],
    summary='Inscription utilisateur',
    description=(
        "Crée un nouvel utilisateur. Une inscription publique crée toujours un OPERATEUR. "
        "Le champ role n'est pris en compte que si la requête est faite par un ADMIN authentifié."
    ),
    examples=[
        OpenApiExample(
            'Exemple de requête',
            value={
                'nom': 'Dupont',
                'prenom': 'Jean',
                'email': 'jean.dupont@example.com',
                'password': 'MonMotDePasse123',
                'password_confirm': 'MonMotDePasse123',
            },
            request_only=True,
        ),
        OpenApiExample(
            'Exemple de réponse (201)',
            value={
                'id': 1,
                'nom': 'Dupont',
                'prenom': 'Jean',
                'email': 'jean.dupont@example.com',
                'role': 'OPERATEUR',
                'role_label': 'Opérateur',
                'actif': True,
                'date_joined': '2024-01-01T12:00:00Z',
            },
            response_only=True,
        ),
    ],
    responses={
        201: OpenApiResponse(description='Compte créé avec succès'),
        400: OpenApiResponse(description='Données invalides'),
    },
)
class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)

        if not (request.user and request.user.is_authenticated and request.user.role == User.Role.ADMIN):
            data['role'] = User.Role.OPERATEUR

        # Règle : un seul ADMIN autorisé
        if data.get('role') == User.Role.ADMIN and User.objects.filter(role=User.Role.ADMIN).exists():
            return Response(
                {'error': 'Un administrateur existe déjà. Un seul compte ADMIN est autorisé.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


# ─── Profil utilisateur connecté ─────────────────────────────────────────────
@extend_schema(
    tags=['Authentification'],
    summary='Profil utilisateur connecté',
    description="Retourne le profil de l'utilisateur authentifié (sert à vérifier le JWT dans Swagger).",
    responses={
        200: OpenApiResponse(description='Profil utilisateur'),
        401: OpenApiResponse(description='Non authentifié'),
    },
)
class MeView(generics.RetrieveAPIView):
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user


# ─── Demande de réinitialisation de mot de passe ─────────────────────────────
@extend_schema(
    tags=['Authentification'],
    summary='Demande de réinitialisation de mot de passe',
    description=(
        "Envoie un email avec un lien de réinitialisation. "
        "Réponse TOUJOURS 200 avec un message générique, que l'email existe ou non (pas d'énumération des comptes)."
    ),
    request=PasswordResetSerializer,
    examples=[
        OpenApiExample(
            'Exemple de requête',
            value={'email': 'user@example.com'},
            request_only=True,
        ),
        OpenApiExample(
            'Exemple de réponse (200)',
            value={'message': 'Si un compte existe avec cette adresse, un email de réinitialisation a été envoyé.'},
            response_only=True,
        ),
    ],
    responses={
        200: OpenApiResponse(description='Demande traitée'),
        429: OpenApiResponse(description='Trop de requêtes'),
    },
)
class PasswordResetView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [PasswordResetThrottle]

    def post(self, request):
        serializer = PasswordResetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data['email'].lower()
        try:
            user = User.objects.get(email=email, actif=True)
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            reset_url  = f"{settings.FRONTEND_URL}/reset-password?uid={uid}&token={token}"
            reset_html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>Réinitialisation de mot de passe — SmartFactory Twin</title>
</head>
<body style="margin:0;padding:0;background-color:#f1f5f9;font-family:'Segoe UI',Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9;padding:40px 0;">
    <tr>
      <td align="center">
        <table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08);">
          <tr>
            <td style="background:linear-gradient(135deg,#0f172a 0%,#1e3a8a 100%);padding:32px 40px;text-align:center;">
              <img src="cid:{LOGO_CID}" alt="Logo" width="52" height="52"
                   style="display:inline-block;border-radius:10px;margin-bottom:12px;vertical-align:middle;" />
              <h1 style="margin:0;color:#ffffff;font-size:24px;font-weight:700;letter-spacing:-0.5px;">
                SmartFactory <span style="color:#60a5fa;">Twin</span>
              </h1>
              <p style="margin:6px 0 0;color:#93c5fd;font-size:12px;letter-spacing:2px;text-transform:uppercase;">
                Industrial Intelligence Platform
              </p>
            </td>
          </tr>
          <tr>
            <td style="padding:40px 40px 32px;">
              <div style="text-align:center;margin-bottom:28px;">
                <div style="display:inline-block;background:#eff6ff;border-radius:50%;padding:18px;">
                  <svg width="36" height="36" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <rect width="24" height="24" rx="12" fill="#dbeafe"/>
                    <rect x="11" y="6" width="2" height="7" rx="1" fill="#2563eb"/>
                    <circle cx="12" cy="17" r="1.2" fill="#2563eb"/>
                  </svg>
                </div>
              </div>
              <h2 style="margin:0 0 8px;color:#0f172a;font-size:22px;font-weight:700;text-align:center;">
                Réinitialisation de mot de passe
              </h2>
              <p style="margin:0 0 28px;color:#64748b;font-size:15px;text-align:center;line-height:1.6;">
                Bonjour <strong>{user.prenom}</strong>, vous avez demandé à réinitialiser votre mot de passe.
              </p>
              <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:12px;padding:20px 24px;margin-bottom:28px;">
                <p style="margin:0 0 8px;color:#475569;font-size:13px;line-height:1.6;">
                  Cliquez sur le bouton ci-dessous pour définir un nouveau mot de passe. Ce lien est valable <strong>24 heures</strong>.
                </p>
                <p style="margin:0;color:#94a3b8;font-size:12px;">
                  Si vous n'êtes pas à l'origine de cette demande, ignorez simplement cet email.
                </p>
              </div>
              <div style="text-align:center;margin-bottom:28px;">
                <a href="{reset_url}"
                   style="display:inline-block;background:#2563eb;color:#ffffff;text-decoration:none;
                          font-size:15px;font-weight:600;padding:14px 36px;border-radius:10px;">
                  Réinitialiser mon mot de passe →
                </a>
              </div>
              <p style="margin:0 0 4px;color:#94a3b8;font-size:12px;text-align:center;">
                Si le bouton ne fonctionne pas, copiez ce lien :
              </p>
              <p style="margin:0;word-break:break-all;font-size:11px;color:#2563eb;text-align:center;">
                <a href="{reset_url}" style="color:#2563eb;">{reset_url}</a>
              </p>
            </td>
          </tr>
          <tr><td style="padding:0 40px;"><hr style="border:none;border-top:1px solid #f1f5f9;"/></td></tr>
          <tr>
            <td style="padding:24px 40px;text-align:center;">
              <p style="margin:0 0 6px;color:#94a3b8;font-size:12px;">
                &#x25CF; Connexion sécurisée · SmartFactory Twin v2.4.1
              </p>
              <p style="margin:0;color:#94a3b8;font-size:12px;">
                <a href="mailto:support@smartfactory.dz" style="color:#2563eb;">Contacter le support</a>
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""
            send_html_email(
                subject='Réinitialisation de mot de passe — SmartFactory Twin',
                text_body=f'Bonjour {user.prenom},\n\nPour réinitialiser votre mot de passe :\n{reset_url}\n\nCe lien expire dans 24 heures.',
                html_body=reset_html,
                to_email=user.email,
                fail_silently=True,
            )
        except User.DoesNotExist:
            pass

        return Response(
            {'message': 'Si un compte existe avec cette adresse, un email de réinitialisation a été envoyé.'},
            status=status.HTTP_200_OK
        )


# ─── Confirmation de réinitialisation de mot de passe ────────────────────────
@extend_schema(
    tags=['Authentification'],
    summary='Confirmation de réinitialisation de mot de passe',
    description=(
        "Vérifie le token, applique les validateurs de mot de passe, enregistre le nouveau mot de passe, "
        "et invalide tous les refresh tokens existants de l'utilisateur."
    ),
    request=PasswordResetConfirmSerializer,
    examples=[
        OpenApiExample(
            'Exemple de requête',
            value={
                'uid': 'MQ',
                'token': 'abc123-def456',
                'new_password': 'NouveauMotDePasse123',
                'new_password_confirm': 'NouveauMotDePasse123',
            },
            request_only=True,
        ),
        OpenApiExample(
            'Exemple de réponse (200)',
            value={'message': 'Mot de passe réinitialisé avec succès.'},
            response_only=True,
        ),
    ],
    responses={
        200: OpenApiResponse(description='Mot de passe réinitialisé'),
        400: OpenApiResponse(description='Token invalide ou expiré'),
    },
)
class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        uid = serializer.validated_data['uid']
        token = serializer.validated_data['token']

        try:
            uid_decoded = force_str(urlsafe_base64_decode(uid))
            user = User.objects.get(pk=uid_decoded)
        except (ValueError, TypeError, OverflowError, User.DoesNotExist):
            return Response(
                {'error': 'Lien de réinitialisation invalide.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not default_token_generator.check_token(user, token):
            return Response(
                {'error': 'Lien de réinitialisation invalide ou expiré.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if user.must_reset_password and user.is_temp_password_expired:
            user.actif = False
            user.save(update_fields=['actif'])
            return Response(
                {'error': 'Le délai de 48 heures pour définir votre mot de passe a expiré. Votre compte est inactif.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        user.set_password(serializer.validated_data['new_password'])
        user.must_reset_password = False
        user.actif = True  # Activé avec succès dès le premier login / changement de mot de passe
        user.save()

        # Blacklister tous les refresh tokens existants de l'utilisateur
        from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken
        for outstanding in OutstandingToken.objects.filter(user=user):
            BlacklistedToken.objects.get_or_create(token=outstanding)

        return Response(
            {'message': 'Mot de passe réinitialisé avec succès.'},
            status=status.HTTP_200_OK
        )


# ─── Création d'utilisateur par un ADMIN ────────────────────────────────────
@extend_schema(
    tags=['Authentification'],
    summary='Création d\'utilisateur par un administrateur',
    description=(
        "Réservé aux ADMIN. Génère un mot de passe temporaire valable 48h, crée l'utilisateur avec "
        "le statut inactif par défaut et l'obligation de changer son mot de passe au premier login. "
        "Seuls les rôles TECHNICIEN et OPERATEUR peuvent être créés."
    ),
    request=AdminUserCreateSerializer,
    examples=[
        OpenApiExample(
            'Exemple de requête',
            value={
                'nom': 'Technique',
                'prenom': 'Ali',
                'email': 'ali@example.com',
                'role': 'TECHNICIEN',
            },
            request_only=True,
        ),
        OpenApiExample(
            'Exemple de réponse (201)',
            value={
                'id': 5,
                'nom': 'Technique',
                'prenom': 'Ali',
                'email': 'ali@example.com',
                'role': 'TECHNICIEN',
                'role_label': 'Technicien',
                'actif': False,
                'must_reset_password': True,
                'date_joined': '2024-01-01T12:00:00Z',
            },
            response_only=True,
        ),
    ],
    responses={
        201: OpenApiResponse(description='Utilisateur créé, email envoyé'),
        400: OpenApiResponse(description='Données invalides'),
        401: OpenApiResponse(description='Non authentifié'),
        403: OpenApiResponse(description='Réservé aux administrateurs'),
    },
)
class AdminUserCreateView(generics.CreateAPIView):
    serializer_class = AdminUserCreateSerializer
    permission_classes = [IsAuthenticated, IsAdmin]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        role = serializer.validated_data.get('role', User.Role.OPERATEUR)
        # Seuls TECHNICIEN et OPERATEUR sont autorisés à la création
        if role == User.Role.ADMIN:
            return Response(
                {'error': "Seuls les rôles Technicien et Opérateur peuvent être créés par l'administrateur."},
                status=status.HTTP_400_BAD_REQUEST
            )

        password = generate_strong_password()

        # Affectations / périmètre d'accès (UserScope) : validées AVANT toute
        # création, pour ne jamais laisser un utilisateur sans ses affectations.
        perimetres = request.data.get('perimetres')
        scope_payloads = []
        if perimetres is not None:
            if not isinstance(perimetres, (list, tuple)):
                return Response(
                    {'perimetres': ["Le champ « perimetres » doit être une liste."]},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            scope_payloads, erreur = _valider_perimetres(perimetres)
            if erreur:
                return Response({'perimetres': [erreur]}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                user = User.objects.create_user(
                    email=serializer.validated_data['email'],
                    password=password,
                    nom=serializer.validated_data['nom'],
                    prenom=serializer.validated_data['prenom'],
                    role=role,
                    must_reset_password=True,
                    actif=False,  # Inactif par défaut jusqu'au premier login (changement de mot de passe)
                )
                if scope_payloads:
                    _appliquer_perimetres(user, scope_payloads)
        except PerimetreInvalide as exc:
            # L'exception annule la transaction : l'utilisateur n'est pas créé.
            return Response({'perimetres': [exc.message]}, status=status.HTTP_400_BAD_REQUEST)

        login_url  = f"{settings.FRONTEND_URL}/login"
        send_html_email(
            subject='Votre compte SmartFactory Twin a été créé',
            text_body=(
                f"Bonjour {user.prenom},\n\n"
                f"Un compte a été créé pour vous sur SmartFactory Twin avec le rôle {user.get_role_display()}.\n\n"
                f"Email : {user.email}\n"
                f"Mot de passe temporaire : {password}\n\n"
                f"Connectez-vous ici : {login_url}\n\n"
                f"Important : Vous disposez de 48 heures pour vous connecter et définir votre nouveau mot de passe. Passé ce délai, votre mot de passe temporaire expirera et votre compte restera inactif.\n\n"
                f"L'équipe SmartFactory Twin"
            ),

            html_body=f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>Votre compte SmartFactory Twin</title>
</head>
<body style="margin:0;padding:0;background-color:#f1f5f9;font-family:'Segoe UI',Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9;padding:40px 0;">
    <tr>
      <td align="center">
        <table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08);">

          <!-- Header -->
          <tr>
            <td style="background:linear-gradient(135deg,#0f172a 0%,#1e3a8a 100%);padding:32px 40px;text-align:center;">
              <img src="cid:{LOGO_CID}"
                   alt="SmartFactory Twin"
                   width="52" height="52"
                   style="display:inline-block;border-radius:10px;margin-bottom:12px;vertical-align:middle;" />
              <h1 style="margin:0;color:#ffffff;font-size:24px;font-weight:700;letter-spacing:-0.5px;">
                SmartFactory <span style="color:#60a5fa;">Twin</span>
              </h1>
              <p style="margin:6px 0 0;color:#93c5fd;font-size:12px;letter-spacing:2px;text-transform:uppercase;">
                Industrial Intelligence Platform
              </p>
            </td>
          </tr>

          <!-- Body -->
          <tr>
            <td style="padding:40px 40px 32px;">
              <!-- Icône -->
              <div style="text-align:center;margin-bottom:28px;">
                <div style="display:inline-block;background:#eff6ff;border-radius:50%;padding:18px;">
                  <svg width="36" height="36" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <circle cx="12" cy="12" r="11" stroke="#2563eb" stroke-width="1.5" fill="#dbeafe"/>
                    <path d="M7 12.5l3.5 3.5 6.5-7" stroke="#2563eb" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                  </svg>
                </div>
              </div>

              <h2 style="margin:0 0 8px;color:#0f172a;font-size:22px;font-weight:700;text-align:center;">
                Bienvenue, {user.prenom} !
              </h2>
              <p style="margin:0 0 28px;color:#64748b;font-size:15px;text-align:center;line-height:1.6;">
                Votre compte SmartFactory Twin a été créé par un administrateur.
              </p>

              <!-- Credentials box -->
              <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:12px;padding:24px;margin-bottom:28px;">
                <p style="margin:0 0 16px;color:#475569;font-size:13px;font-weight:600;text-transform:uppercase;letter-spacing:1px;">
                  Vos identifiants de connexion
                </p>
                <table width="100%" cellpadding="0" cellspacing="0">
                  <tr>
                    <td style="padding:10px 0;border-bottom:1px solid #e2e8f0;">
                      <span style="color:#64748b;font-size:13px;">Adresse e-mail</span><br/>
                      <strong style="color:#0f172a;font-size:15px;">{user.email}</strong>
                    </td>
                  </tr>
                  <tr>
                    <td style="padding:10px 0;">
                      <span style="color:#64748b;font-size:13px;">Mot de passe temporaire</span><br/>
                      <strong style="color:#0f172a;font-size:15px;font-family:monospace;background:#e0f2fe;padding:2px 8px;border-radius:4px;">{password}</strong>
                    </td>
                  </tr>
                </table>
              </div>

              <!-- Warning -->
              <div style="background:#fff7ed;border:1px solid #fed7aa;border-radius:10px;padding:14px 18px;margin-bottom:28px;display:flex;align-items:flex-start;gap:10px;">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" style="flex-shrink:0;margin-top:1px;">
                  <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" stroke="#c2410c" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" fill="#fff7ed"/>
                  <line x1="12" y1="9" x2="12" y2="13" stroke="#c2410c" stroke-width="2" stroke-linecap="round"/>
                  <circle cx="12" cy="17" r="1" fill="#c2410c"/>
                </svg>
                <p style="margin:0;color:#9a3412;font-size:13px;line-height:1.6;">
                  <strong>Sécurité :</strong> vous devrez changer ce mot de passe temporaire lors de votre première connexion. Il ne pourra pas être ignoré.
                </p>
              </div>

              <!-- CTA Button -->
              <div style="text-align:center;margin-bottom:28px;">
                <a href="{login_url}"
                   style="display:inline-block;background:#2563eb;color:#ffffff;text-decoration:none;
                          font-size:15px;font-weight:600;padding:14px 36px;border-radius:10px;
                          letter-spacing:0.3px;">
                  Se connecter maintenant →
                </a>
              </div>

              <!-- Role badge -->
              <p style="margin:0;text-align:center;color:#64748b;font-size:13px;">
                Rôle attribué :
                <span style="background:#eff6ff;color:#1d4ed8;padding:3px 10px;border-radius:20px;font-weight:600;font-size:12px;">
                  {user.get_role_display()}
                </span>
              </p>
            </td>
          </tr>

          <!-- Divider -->
          <tr>
            <td style="padding:0 40px;">
              <hr style="border:none;border-top:1px solid #f1f5f9;"/>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="padding:24px 40px;text-align:center;">
              <p style="margin:0 0 6px;color:#94a3b8;font-size:12px;">
                &#x25CF; Connexion sécurisée · SmartFactory Twin v2.4.1
              </p>
              <p style="margin:0;color:#94a3b8;font-size:12px;">
                Si vous n'êtes pas à l'origine de cette demande, ignorez cet email ou
                <a href="mailto:support@smartfactory.dz" style="color:#2563eb;">contactez le support</a>.
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>""",
            to_email=user.email,
            fail_silently=False,
        )

        return Response(
            UserSerializer(user).data,
            status=status.HTTP_201_CREATED
        )


# ─── Liste des utilisateurs (ADMIN) ─────────────────────────────────────────
@extend_schema(
    tags=['Authentification'],
    summary='Liste des utilisateurs (ADMIN)',
    description=(
        "Retourne la liste paginée des utilisateurs. "
        "Paramètres de requête : `search` (nom/prénom/email), `role` (ADMIN/TECHNICIEN/OPERATEUR), "
        "`actif` (true/false), `ordering` (date_joined/-date_joined/nom/email)."
    ),
    responses={
        200: OpenApiResponse(description='Liste paginée des utilisateurs'),
        401: OpenApiResponse(description='Non authentifié'),
        403: OpenApiResponse(description='Réservé aux administrateurs'),
    },
)
class AdminUserListView(generics.ListAPIView):
    """Liste paginée des utilisateurs — accessible aux ADMIN uniquement."""

    serializer_class = AdminUserListSerializer
    permission_classes = [IsAuthenticated, IsAdmin]

    def get_queryset(self):
        # Exclure l'admin connecté de sa propre liste
        qs = User.objects.exclude(pk=self.request.user.pk).order_by('-date_joined')

        # Recherche full-text sur nom, prénom, email
        search = self.request.query_params.get('search', '').strip()
        if search:
            from django.db.models import Q
            qs = qs.filter(
                Q(nom__icontains=search)
                | Q(prenom__icontains=search)
                | Q(email__icontains=search)
            )

        # Filtre par rôle
        role = self.request.query_params.get('role', '').strip().upper()
        if role in [r[0] for r in User.Role.choices]:
            qs = qs.filter(role=role)

        # Filtre par actif
        actif = self.request.query_params.get('actif', '').strip().lower()
        if actif == 'true':
            qs = qs.filter(actif=True)
        elif actif == 'false':
            qs = qs.filter(actif=False)

        # Tri
        ordering = self.request.query_params.get('ordering', '-date_joined')
        allowed  = ['date_joined', '-date_joined', 'nom', '-nom', 'email', '-email']
        if ordering in allowed:
            qs = qs.order_by(ordering)

        return qs


# ─── Mise à jour du profil (nom, prénom, téléphone) ─────────────────────────
@extend_schema(
    tags=['Authentification'],
    summary='Mettre à jour son profil',
    description=(
        "Permet à l'utilisateur connecté de modifier son nom, prénom et numéro de téléphone. "
        "Méthode PATCH — seuls les champs fournis sont mis à jour."
    ),
    request=UpdateProfileSerializer,
    examples=[
        OpenApiExample(
            'Exemple de requête',
            value={'nom': 'Dupont', 'prenom': 'Jean', 'telephone': '+213 555 123 456'},
            request_only=True,
        ),
        OpenApiExample(
            'Exemple de réponse (200)',
            value={
                'id': 1, 'nom': 'Dupont', 'prenom': 'Jean',
                'email': 'jean@example.com', 'role': 'OPERATEUR',
                'telephone': '+213 555 123 456', 'actif': True,
            },
            response_only=True,
        ),
    ],
    responses={
        200: OpenApiResponse(description='Profil mis à jour'),
        400: OpenApiResponse(description='Données invalides'),
        401: OpenApiResponse(description='Non authentifié'),
    },
)
class UpdateProfileView(generics.UpdateAPIView):
    """Mise à jour partielle du profil (nom, prénom, téléphone, photo)."""

    serializer_class = UpdateProfileSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ['patch']

    def get_object(self):
        return self.request.user

    def update(self, request, *args, **kwargs):
        kwargs['partial'] = True
        instance = self.get_object()
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        serializer = self.get_serializer(instance, data=data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        # Passer request dans le contexte pour que UserSerializer génère l'URL absolue de la photo
        return Response(
            UserSerializer(instance, context={'request': request}).data,
            status=status.HTTP_200_OK
        )


# ─── Changement de mot de passe direct (connecté, sans token email) ──────────
@extend_schema(
    tags=['Authentification'],
    summary='Changer son mot de passe (connecté)',
    description=(
        "Permet à l'utilisateur connecté de changer son mot de passe directement, "
        "sans passer par le flux email. Requiert le mot de passe actuel. "
        "Invalide tous les refresh tokens existants après le changement."
    ),
    request=ChangePasswordSerializer,
    examples=[
        OpenApiExample(
            'Exemple de requête',
            value={
                'current_password': 'AncienMotDePasse123',
                'new_password': 'NouveauMotDePasse456!',
                'new_password_confirm': 'NouveauMotDePasse456!',
            },
            request_only=True,
        ),
        OpenApiExample(
            'Exemple de réponse (200)',
            value={'message': 'Mot de passe changé avec succès.'},
            response_only=True,
        ),
    ],
    responses={
        200: OpenApiResponse(description='Mot de passe changé'),
        400: OpenApiResponse(description='Mot de passe actuel incorrect ou validation échouée'),
        401: OpenApiResponse(description='Non authentifié'),
    },
)
class ChangePasswordView(APIView):
    """Changement de mot de passe direct pour un utilisateur authentifié."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(
            data=request.data, context={'request': request}
        )
        serializer.is_valid(raise_exception=True)

        user = request.user
        user.set_password(serializer.validated_data['new_password'])
        user.must_reset_password = False
        user.actif = True
        user.save()


        # Invalider tous les refresh tokens existants
        from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken
        for token in OutstandingToken.objects.filter(user=user):
            BlacklistedToken.objects.get_or_create(token=token)

        return Response(
            {'message': 'Mot de passe changé avec succès.'},
            status=status.HTTP_200_OK
        )


# ─── Suppression d'un utilisateur (ADMIN) ───────────────────────────────────
@extend_schema(
    tags=['Authentification'],
    summary='Supprimer un utilisateur (ADMIN)',
    description="Supprime un utilisateur par son ID. Réservé aux ADMIN. Un admin ne peut pas se supprimer lui-même.",
    responses={
        204: OpenApiResponse(description='Utilisateur supprimé'),
        400: OpenApiResponse(description='Impossible de se supprimer soi-même'),
        401: OpenApiResponse(description='Non authentifié'),
        403: OpenApiResponse(description='Réservé aux administrateurs'),
        404: OpenApiResponse(description='Utilisateur introuvable'),
    },
)
class AdminUserDeleteView(generics.DestroyAPIView):
    """Suppression d'un utilisateur — ADMIN uniquement."""

    permission_classes = [IsAuthenticated, IsAdmin]
    queryset = User.objects.all()

    def destroy(self, request, *args, **kwargs):
        user_to_delete = self.get_object()
        if user_to_delete.pk == request.user.pk:
            return Response(
                {'error': 'Vous ne pouvez pas supprimer votre propre compte.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        user_to_delete.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ─── Mise à jour d'un utilisateur par l'ADMIN ───────────────────────────────
@extend_schema(
    tags=['Authentification'],
    summary='Modifier un utilisateur (ADMIN)',
    description="Permet à un ADMIN de modifier le rôle, le statut actif, le nom et le prénom d'un utilisateur.",
    responses={
        200: OpenApiResponse(description='Utilisateur mis à jour'),
        400: OpenApiResponse(description='Données invalides'),
        401: OpenApiResponse(description='Non authentifié'),
        403: OpenApiResponse(description='Réservé aux administrateurs'),
        404: OpenApiResponse(description='Utilisateur introuvable'),
    },
)
class AdminUserUpdateView(generics.UpdateAPIView):
    """Modification d'un utilisateur par l'admin (rôle, actif, nom, prénom)."""

    permission_classes = [IsAuthenticated, IsAdmin]
    queryset = User.objects.all()
    http_method_names = ['patch']

    def get_serializer_class(self):
        return UserSerializer

    def patch(self, request, *args, **kwargs):
        user_to_update = self.get_object()
        allowed_fields = {'role', 'actif', 'nom', 'prenom', 'telephone'}
        data = {k: v for k, v in request.data.items() if k in allowed_fields}

        # Valider le rôle
        if 'role' in data:
            valid_roles = [r[0] for r in User.Role.choices]
            if data['role'] not in valid_roles:
                return Response(
                    {'role': [f"Rôle invalide. Valeurs acceptées : {', '.join(valid_roles)}"]},
                    status=status.HTTP_400_BAD_REQUEST
                )

        for field, value in data.items():
            setattr(user_to_update, field, value)
        user_to_update.save()

        return Response(UserSerializer(user_to_update).data, status=status.HTTP_200_OK)
