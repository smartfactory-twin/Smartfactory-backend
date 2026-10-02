from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth.password_validation import validate_password
from .models import User


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """JWT login — retourne access + refresh + infos utilisateur."""

    def validate(self, attrs):
        data = super().validate(attrs)
        data['user'] = {
            'id':         self.user.id,
            'email':      self.user.email,
            'username':   self.user.username,
            'first_name': self.user.first_name,
            'last_name':  self.user.last_name,
            'role':       self.user.role,
            'role_label': self.user.get_role_display(),
            'avatar':     self.user.avatar.url if self.user.avatar else None,
        }
        return data


class RegisterSerializer(serializers.ModelSerializer):
    """Inscription d'un nouvel utilisateur."""

    password = serializers.CharField(
        write_only=True, required=True,
        validators=[validate_password],
        style={'input_type': 'password'}
    )
    password2 = serializers.CharField(
        write_only=True, required=True,
        label='Confirmation du mot de passe',
        style={'input_type': 'password'}
    )

    class Meta:
        model = User
        fields = [
            'email', 'username', 'first_name', 'last_name',
            'role', 'phone', 'password', 'password2',
        ]
        extra_kwargs = {
            'first_name': {'required': True},
            'last_name':  {'required': True},
            'role':       {'required': True},
        }

    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError(
                {'password': 'Les mots de passe ne correspondent pas.'}
            )
        return attrs

    def create(self, validated_data):
        validated_data.pop('password2')
        password = validated_data.pop('password')
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class UserProfileSerializer(serializers.ModelSerializer):
    """Profil utilisateur — lecture et modification partielle."""

    role_label = serializers.CharField(source='get_role_display', read_only=True)
    avatar_url = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'email', 'username', 'first_name', 'last_name',
            'role', 'role_label', 'phone', 'avatar', 'avatar_url',
            'date_joined', 'last_login',
        ]
        read_only_fields = ['id', 'email', 'role', 'date_joined', 'last_login']

    def get_avatar_url(self, obj):
        request = self.context.get('request')
        if obj.avatar and request:
            return request.build_absolute_uri(obj.avatar.url)
        return None


class ChangePasswordSerializer(serializers.Serializer):
    """Changement de mot de passe."""

    old_password  = serializers.CharField(required=True, style={'input_type': 'password'})
    new_password  = serializers.CharField(required=True, validators=[validate_password], style={'input_type': 'password'})
    new_password2 = serializers.CharField(required=True, style={'input_type': 'password'})

    def validate(self, attrs):
        if attrs['new_password'] != attrs['new_password2']:
            raise serializers.ValidationError(
                {'new_password': 'Les mots de passe ne correspondent pas.'}
            )
        return attrs
