import uuid

from django.conf import settings
from django.db import models


class VoiceConversation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='voice_conversations',
    )
    messages = models.JSONField(default=list, blank=True)
    expires_at = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        indexes = [models.Index(fields=['utilisateur', 'expires_at'], name='voice_conv_user_exp_idx')]


class VoiceAgentRequest(models.Model):
    class Status(models.TextChoices):
        SUCCESS = 'success', 'Réussie'
        ERROR = 'error', 'Erreur'

    utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='voice_agent_requests',
    )
    conversation_id = models.UUIDField(null=True, blank=True, db_index=True)
    texte = models.CharField(max_length=2000)
    outils_appeles = models.JSONField(default=list, blank=True)
    resume_resultat = models.CharField(max_length=4000, blank=True, default='')
    duree_ms = models.PositiveIntegerField(default=0)
    statut = models.CharField(max_length=12, choices=Status.choices)
    erreur = models.CharField(max_length=120, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at', '-pk']
        indexes = [models.Index(fields=['utilisateur', '-created_at'], name='voice_req_user_created_idx')]
