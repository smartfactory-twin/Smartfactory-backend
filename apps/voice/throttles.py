from rest_framework.throttling import ScopedRateThrottle


class VoiceAgentThrottle(ScopedRateThrottle):
    scope = 'voice_agent'


class VoiceTranscriptionThrottle(ScopedRateThrottle):
    scope = 'voice_transcribe'
