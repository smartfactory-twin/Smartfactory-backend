from rest_framework.throttling import ScopedRateThrottle


class VoiceAgentThrottle(ScopedRateThrottle):
    scope = 'voice_agent'
