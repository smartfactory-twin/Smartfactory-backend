from rest_framework import status, generics
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken
from drf_spectacular.utils import extend_schema, OpenApiResponse

from .models import User
from .serializers import (
    CustomTokenObtainPairSerializer,
    RegisterSerializer,
    UserProfileSerializer,
    ChangePasswordSerializer,
)
from .permissions import IsAdminRole


# ─── Login ────────────────────────────────────────────────────────────────────
@extend_schema(tags=['Auth'])
class LoginView(TokenObtainPairView):
    """
    POST /api/v1/auth/login/
    Retourne : access token, refresh token, infos utilisateur + rôle.
    """
    serializer_class = CustomTokenObtainPairSerializer
    permission_classes = [AllowAny]


# ─── Logout ───────────────────────────────────────────────────────────────────
@extend_schema(tags=['Auth'])
class LogoutView(APIView):
    """
    POST /api/v1/auth/logout/
    Invalide le refresh token (blacklist).
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.data.get('refresh')
            if not refresh_token:
                return Response(
                    {'error': 'Le refresh token est requis.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response(
                {'message': 'Déconnexion réussie.'},
                status=status.HTTP_200_OK
            )
        except Exception:
            return Response(
                {'error': 'Token invalide ou déjà révoqué.'},
                status=status.HTTP_400_BAD_REQUEST
            )


# ─── Inscription ──────────────────────────────────────────────────────────────
@extend_schema(tags=['Auth'])
class RegisterView(generics.CreateAPIView):
    """
    POST /api/v1/auth/register/
    Crée un nouvel utilisateur (Admin uniquement en production).
    En développement : ouvert à tous.
    """
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]   # ← mettre IsAdminRole en prod

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(
            {
                'message': f'Compte créé avec succès. Rôle : {user.get_role_display()}',
                'user': {
                    'id':         user.id,
                    'email':      user.email,
                    'username':   user.username,
                    'first_name': user.first_name,
                    'last_name':  user.last_name,
                    'role':       user.role,
                    'role_label': user.get_role_display(),
                },
            },
            status=status.HTTP_201_CREATED
        )


# ─── Profil utilisateur connecté ─────────────────────────────────────────────
@extend_schema(tags=['Auth'])
class MeView(generics.RetrieveUpdateAPIView):
    """
    GET  /api/v1/auth/me/  → Récupérer le profil
    PATCH /api/v1/auth/me/ → Modifier le profil (nom, téléphone, avatar)
    """
    serializer_class = UserProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user


# ─── Changement de mot de passe ───────────────────────────────────────────────
@extend_schema(tags=['Auth'])
class ChangePasswordView(APIView):
    """POST /api/v1/auth/change-password/"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = request.user
        if not user.check_password(serializer.validated_data['old_password']):
            return Response(
                {'old_password': 'Mot de passe actuel incorrect.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        user.set_password(serializer.validated_data['new_password'])
        user.save()
        return Response(
            {'message': 'Mot de passe modifié avec succès.'},
            status=status.HTTP_200_OK
        )


# ─── Liste des utilisateurs (Admin seulement) ────────────────────────────────
@extend_schema(tags=['Users'])
class UserListView(generics.ListAPIView):
    """GET /api/v1/auth/users/ — Liste tous les utilisateurs (Admin uniquement)."""
    serializer_class = UserProfileSerializer
    permission_classes = [IsAuthenticated, IsAdminRole]
    queryset = User.objects.all()
    filterset_fields = ['role', 'is_active']
    search_fields = ['email', 'first_name', 'last_name', 'username']
