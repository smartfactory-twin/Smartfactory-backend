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
from django.core.mail import send_mail
from django.conf import settings

from .serializers import (
    CustomTokenObtainPairSerializer,
    RegisterSerializer,
    UserSerializer,
    PasswordResetSerializer,
    PasswordResetConfirmSerializer,
    LogoutSerializer,
)
from .permissions import IsAdmin
from .throttles import LoginThrottle, PasswordResetThrottle

User = get_user_model()


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

        # Vérifier l'inactivité avant la validation JWT pour retourner 403
        try:
            candidate = User.objects.get(email=email)
            if not candidate.actif and candidate.check_password(password):
                return Response(
                    {'error': 'Ce compte est inactif.'},
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
        # Copie mutable des données (QueryDict est immutable en POST multipart)
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)

        # Si l'utilisateur n'est pas admin, forcer le rôle OPERATEUR
        if not (request.user and request.user.is_authenticated and request.user.role == User.Role.ADMIN):
            data['role'] = User.Role.OPERATEUR

        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(
            UserSerializer(user).data,
            status=status.HTTP_201_CREATED
        )


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
            reset_url = f"{settings.FRONTEND_URL}/reset-password?uid={uid}&token={token}"

            send_mail(
                subject='Réinitialisation de mot de passe — SmartFactory Twin',
                message=f'Bonjour {user.prenom},\n\nPour réinitialiser votre mot de passe, cliquez sur le lien suivant :\n{reset_url}\n\nSi vous n\'avez pas demandé cette réinitialisation, ignorez cet email.\n\nL\'équipe SmartFactory Twin',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
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

        user.set_password(serializer.validated_data['new_password'])
        user.save()

        # Blacklister tous les refresh tokens existants de l'utilisateur
        from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken
        for outstanding in OutstandingToken.objects.filter(user=user):
            BlacklistedToken.objects.get_or_create(token=outstanding)

        return Response(
            {'message': 'Mot de passe réinitialisé avec succès.'},
            status=status.HTTP_200_OK
        )
