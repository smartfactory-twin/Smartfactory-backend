"""Authenticated upload endpoint for hosted speech transcription."""
import io
import logging
import time
import wave

from django.conf import settings
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .throttles import VoiceSessionTranscriptionThrottle, VoiceTranscriptionThrottle
from .transcription import (
    TranscriptionConfigurationError,
    TranscriptionUnavailableError,
    transcribe,
)


logger = logging.getLogger(__name__)

ALLOWED_CONTENT_TYPES = {
    'audio/webm', 'audio/ogg', 'application/ogg',
    'audio/wav', 'audio/x-wav', 'audio/wave', 'audio/vnd.wave',
    'audio/mp4', 'video/mp4', 'audio/x-m4a',
    'audio/mpeg', 'audio/mp3', 'audio/x-mpeg', 'audio/mpga',
}
WAV_CONTENT_TYPES = {'audio/wav', 'audio/x-wav', 'audio/wave', 'audio/vnd.wave'}


def _wav_duration_seconds(audio_file):
    audio_file.seek(0)
    raw = audio_file.read()
    audio_file.seek(0)
    try:
        with wave.open(io.BytesIO(raw), 'rb') as wav_file:
            rate = wav_file.getframerate()
            if rate <= 0:
                raise wave.Error('invalid sample rate')
            return wav_file.getnframes() / rate
    except (wave.Error, EOFError) as exc:
        raise ValueError('Le fichier WAV est invalide.') from exc


class VoiceTranscriptionAPIView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    throttle_classes = [VoiceTranscriptionThrottle]
    throttle_scope = 'voice_transcribe'

    def post(self, request):
        audio_file = request.FILES.get('audio')
        if audio_file is None:
            return Response({'detail': 'Le champ multipart « audio » est obligatoire.'},
                            status=status.HTTP_400_BAD_REQUEST)

        started = time.monotonic()
        try:
            content_type = (getattr(audio_file, 'content_type', '') or '').split(';', 1)[0].strip().lower()
            if content_type not in ALLOWED_CONTENT_TYPES:
                return Response({'detail': 'Format audio non accepté.'}, status=status.HTTP_400_BAD_REQUEST)
            max_bytes = settings.VOICE_MAX_AUDIO_BYTES
            if audio_file.size <= 0:
                return Response({'detail': 'Le fichier audio est vide.'}, status=status.HTTP_400_BAD_REQUEST)
            if audio_file.size > max_bytes:
                return Response({'detail': 'Le fichier audio dépasse la taille maximale autorisée.'},
                                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)

            if content_type in WAV_CONTENT_TYPES:
                try:
                    duration = _wav_duration_seconds(audio_file)
                except ValueError as exc:
                    return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
                max_seconds = settings.VOICE_MAX_AUDIO_SECONDS
                if max_seconds > 0 and duration > max_seconds:
                    return Response({'detail': 'Le fichier audio dépasse la durée maximale autorisée.'},
                                    status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)

            try:
                text, model, language = transcribe(audio_file)
            except (TranscriptionConfigurationError, TranscriptionUnavailableError) as exc:
                logger.warning('Voice transcription unavailable exception_type=%s', type(exc).__name__)
                return Response({
                    'code': 'transcription_unavailable',
                    'detail': 'Le service de transcription est indisponible.',
                }, status=status.HTTP_503_SERVICE_UNAVAILABLE)
            return Response({
                'text': text,
                'engine': 'groq-whisper',
                'model': model,
                'language': language,
                'processing_ms': max(0, int((time.monotonic() - started) * 1000)),
            })
        finally:
            # Django's temporary upload handler removes spooled files when closed.
            audio_file.close()


class VoiceSessionTranscriptionAPIView(VoiceTranscriptionAPIView):
    """Separate transcription quota reserved for realtime voice sessions."""
    throttle_classes = [VoiceSessionTranscriptionThrottle]
    throttle_scope = 'voice_session_transcribe'


class VoiceSessionConfigAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({'max_seconds': settings.VOICE_SESSION_MAX_SECONDS})
