from django.urls import path

from .transcription_api import (
    VoiceSessionConfigAPIView, VoiceSessionTranscriptionAPIView, VoiceTranscriptionAPIView,
)
from .views import PendingProposalsAPIView, ProposalActionAPIView, VoiceAgentAPIView, VoiceAgentStreamAPIView


urlpatterns = [
    path('agent/', VoiceAgentAPIView.as_view(), name='voice-agent'),
    path('agent/stream/', VoiceAgentStreamAPIView.as_view(), name='voice-agent-stream'),
    path('transcribe/', VoiceTranscriptionAPIView.as_view(), name='voice-transcribe'),
    path('session/transcribe/', VoiceSessionTranscriptionAPIView.as_view(), name='voice-session-transcribe'),
    path('session/config/', VoiceSessionConfigAPIView.as_view(), name='voice-session-config'),
    path('proposals/pending/', PendingProposalsAPIView.as_view(), name='voice-proposals-pending'),
    path('proposals/<uuid:proposal_id>/confirm/', ProposalActionAPIView.as_view(),
         {'action': 'confirm'}, name='voice-proposal-confirm'),
    path('proposals/<uuid:proposal_id>/cancel/', ProposalActionAPIView.as_view(),
         {'action': 'cancel'}, name='voice-proposal-cancel'),
]

