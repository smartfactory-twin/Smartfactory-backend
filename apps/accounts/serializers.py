from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    """Sérialiseur de base pour les infos utilisateur (sans le mot de passe)."""

    role_label = serializers.CharField(source='get_role_display', read_only=True)

    class Meta:
        model = User
        fields = ['id', 'nom', 'prenom', 'email', 'role', 'role_label', 'actif', 'date_joined']
        read_only_fields = ['id', 'date_joined']


class RegisterSerializer(serializers.ModelSerializer):
    """Inscription d'un nouvel utilisateur."""

    password = serializers.CharField(
        write_only=True, required=True,
        validators=[validate_password],
        style={'input_type': 'password'}
    )
    password_confirm = serializers.CharField(
        write_only=True, required=True,
        style={'input_type': 'password'}
    )

    class Meta:
        model = User
        fields = ['nom', 'prenom', 'email', 'role', 'password', 'password_confirm']
        extra_kwargs = {
            'role': {'required': False, 'default': User.Role.OPERATEUR},
        }

    def validate(self, attrs):
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError(
                {'password_confirm': 'Les mots de passe ne correspondent pas.'}
            )
        return attrs

    def create(self, validated_data):
        validated_data.pop('password_confirm')
        password = validated_data.pop('password')
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """JWT login — retourne access + refresh + infos utilisateur."""

    def validate(self, attrs):
        from django.contrib.auth import authenticate
        from rest_framework.exceptions import AuthenticationFailed

        email = attrs.get('email', '').lower()
        password = attrs.get('password', '')

        # Vérifier si le compte existe et est inactif avant d'appeler super()
        try:
            user = User.objects.get(email=email)
            if not user.actif and user.check_password(password):
                raise AuthenticationFailed(
                    'inactive_account',
                    code='inactive_account'
                )
        except User.DoesNotExist:
            pass

        data = super().validate(attrs)
        data['user'] = {
            'id': self.user.id,
            'nom': self.user.nom,
            'prenom': self.user.prenom,
            'email': self.user.email,
            'role': self.user.role,
            'role_label': self.user.get_role_display(),
        }
        return data

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['role'] = user.role
        token['email'] = user.email
        return token


class PasswordResetSerializer(serializers.Serializer):
    """Demande de réinitialisation de mot de passe."""

    email = serializers.EmailField(required=True)


class PasswordResetConfirmSerializer(serializers.Serializer):
    """Confirmation de réinitialisation de mot de passe."""

    uid = serializers.CharField(required=True)
    token = serializers.CharField(required=True)
    new_password = serializers.CharField(
        write_only=True, required=True,
        validators=[validate_password],
        style={'input_type': 'password'}
    )
    new_password_confirm = serializers.CharField(
        write_only=True, required=True,
        style={'input_type': 'password'}
    )

    def validate(self, attrs):
        if attrs['new_password'] != attrs['new_password_confirm']:
            raise serializers.ValidationError(
                {'new_password_confirm': 'Les mots de passe ne correspondent pas.'}
            )
        return attrs


class LogoutSerializer(serializers.Serializer):
    """Corps de la requête de déconnexion : le refresh token à révoquer."""

    refresh = serializers.CharField(required=True)
