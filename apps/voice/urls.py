from django.urls import path

from .views import VoiceAgentAPIView


urlpatterns = [
    path('agent/', VoiceAgentAPIView.as_view(), name='voice-agent'),
]
