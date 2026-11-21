from django.urls import path

from .views import PendingProposalsAPIView, ProposalActionAPIView, VoiceAgentAPIView


urlpatterns = [
    path('agent/', VoiceAgentAPIView.as_view(), name='voice-agent'),
    path('proposals/pending/', PendingProposalsAPIView.as_view(), name='voice-proposals-pending'),
    path('proposals/<uuid:proposal_id>/confirm/', ProposalActionAPIView.as_view(),
         {'action': 'confirm'}, name='voice-proposal-confirm'),
    path('proposals/<uuid:proposal_id>/cancel/', ProposalActionAPIView.as_view(),
         {'action': 'cancel'}, name='voice-proposal-cancel'),
]
