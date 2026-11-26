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
    interaction_mode = models.CharField(max_length=5, default='text')
    outils_appeles = models.JSONField(default=list, blank=True)
    resume_resultat = models.CharField(max_length=4000, blank=True, default='')
    duree_ms = models.PositiveIntegerField(default=0)
    premiere_phrase_ms = models.PositiveIntegerField(null=True, blank=True)
    statut = models.CharField(max_length=12, choices=Status.choices)
    erreur = models.CharField(max_length=120, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at', '-pk']
        indexes = [models.Index(fields=['utilisateur', '-created_at'], name='voice_req_user_created_idx')]


class VoiceActionProposal(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'En attente'
        EXECUTED = 'executed', 'Exécutée'
        CANCELLED = 'cancelled', 'Annulée'
        EXPIRED = 'expired', 'Expirée'
        FAILED = 'failed', 'Échec'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='voice_action_proposals',
    )
    conversation = models.ForeignKey(
        VoiceConversation, on_delete=models.CASCADE, related_name='action_proposals',
    )
    outil = models.CharField(max_length=40)
    parametres = models.JSONField()
    parametres_hash = models.CharField(max_length=64)
    resume = models.CharField(max_length=500)
    apercu = models.JSONField()
    spoken_summary = models.CharField(max_length=250)
    statut = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)
    executed_at = models.DateTimeField(null=True, blank=True)
    resultat = models.JSONField(null=True, blank=True)
    erreur = models.CharField(max_length=500, blank=True, default='')

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['utilisateur', 'conversation', 'statut'], name='voice_prop_user_conv_idx'),
            models.Index(fields=['utilisateur', '-created_at'], name='voice_prop_user_date_idx'),
        ]
