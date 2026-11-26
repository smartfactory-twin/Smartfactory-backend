import io
import json
import wave
from urllib.error import HTTPError

import pytest
from django.conf import settings
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import AuditLog, Utilisateur
from apps.voice.models import VoiceActionProposal, VoiceAgentRequest, VoiceConversation


@pytest.fixture(autouse=True)
def transcription_config(monkeypatch):
    monkeypatch.setattr(settings, 'TRANSCRIPTION_API_KEY', 'test-transcription-secret')
    monkeypatch.setattr(settings, 'TRANSCRIPTION_BASE_URL', 'https://api.groq.com/openai/v1')


@pytest.fixture
def transcription_user(db):
    return Utilisateur.objects.create_user(
        email='transcribe-operator@test.local', password='Test@123456', role='OPERATEUR',
        nom='Operator', prenom='Transcription',
    )


def auth_client(user=None):
    client = APIClient()
    if user:
        token = str(RefreshToken.for_user(user).access_token)
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
    return client


def wav_bytes(seconds=1):
    output = io.BytesIO()
    with wave.open(output, 'wb') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(8000)
        wav_file.writeframes(b'\0\0' * 8000 * seconds)
    return output.getvalue()


def audio_upload(content=None, content_type='audio/wav', name='phrase.wav'):
    return SimpleUploadedFile(name, content if content is not None else wav_bytes(), content_type=content_type)


class ProviderResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def fake_success(monkeypatch, expected_text='Acquitte l’alerte AL-000004'):
    monkeypatch.setattr(
        'apps.voice.transcription.urlopen',
        lambda request, timeout: ProviderResponse(json.dumps({'text': expected_text}).encode()),
    )


@pytest.mark.django_db
def test_transcription_requires_jwt():
    response = auth_client().post(
        '/api/voice/transcribe/', {'audio': audio_upload()}, format='multipart',
    )
    assert response.status_code == 401


@pytest.mark.django_db
def test_existing_operator_role_can_use_transcription(transcription_user, monkeypatch):
    fake_success(monkeypatch)
    response = auth_client(transcription_user).post(
        '/api/voice/transcribe/', {'audio': audio_upload()}, format='multipart',
    )
    assert response.status_code == 200


@pytest.mark.django_db
def test_unsupported_content_type_is_rejected_before_provider(transcription_user, monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail('Le fournisseur ne doit pas être appelé pour un format refusé.')

    monkeypatch.setattr('apps.voice.transcription.urlopen', unexpected)
    response = auth_client(transcription_user).post(
        '/api/voice/transcribe/',
        {'audio': audio_upload(b'not audio', 'application/pdf', 'voice.pdf')}, format='multipart',
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_oversized_audio_returns_413_before_provider(transcription_user, monkeypatch, settings):
    settings.VOICE_MAX_AUDIO_BYTES = 10

    def unexpected(*args, **kwargs):
        pytest.fail('Le fournisseur ne doit pas être appelé pour un fichier trop gros.')

    monkeypatch.setattr('apps.voice.transcription.urlopen', unexpected)
    response = auth_client(transcription_user).post(
        '/api/voice/transcribe/', {'audio': audio_upload(b'x' * 11)}, format='multipart',
    )
    assert response.status_code == 413


@pytest.mark.django_db
def test_wav_duration_over_limit_returns_413(transcription_user, monkeypatch, settings):
    settings.VOICE_MAX_AUDIO_SECONDS = 0.5

    def unexpected(*args, **kwargs):
        pytest.fail('Le fournisseur ne doit pas être appelé pour un WAV trop long.')

    monkeypatch.setattr('apps.voice.transcription.urlopen', unexpected)
    response = auth_client(transcription_user).post(
        '/api/voice/transcribe/', {'audio': audio_upload(wav_bytes(seconds=1))}, format='multipart',
    )
    assert response.status_code == 413


@pytest.mark.django_db
@pytest.mark.parametrize('failure', ['http', 'timeout'])
def test_provider_failure_returns_transcription_unavailable(transcription_user, monkeypatch, failure):
    def fail(*args, **kwargs):
        if failure == 'http':
            raise HTTPError('https://api.groq.com', 403, 'blocked', {}, io.BytesIO(b'provider refused'))
        raise TimeoutError('do not expose exception message')

    monkeypatch.setattr('apps.voice.transcription.urlopen', fail)
    response = auth_client(transcription_user).post(
        '/api/voice/transcribe/', {'audio': audio_upload()}, format='multipart',
    )
    assert response.status_code == 503
    assert response.data['code'] == 'transcription_unavailable'


@pytest.mark.django_db
def test_provider_response_and_user_agent_are_forwarded(transcription_user, monkeypatch, settings):
    seen = {}

    def respond(request, timeout):
        seen['request'] = request
        seen['timeout'] = timeout
        return ProviderResponse(json.dumps({'text': 'Transcription textuelle'}).encode())

    settings.LLM_USER_AGENT = 'SmartFactoryTwin/test-agent'
    monkeypatch.setattr('apps.voice.transcription.urlopen', respond)
    response = auth_client(transcription_user).post(
        '/api/voice/transcribe/', {'audio': audio_upload()}, format='multipart',
    )
    assert response.status_code == 200
    assert response.data == {
        'text': 'Transcription textuelle', 'engine': 'groq-whisper',
        'model': settings.TRANSCRIPTION_MODEL, 'language': settings.TRANSCRIPTION_LANGUAGE,
        'processing_ms': response.data['processing_ms'],
    }
    assert response.data['processing_ms'] >= 0
    request = seen['request']
    assert request.get_header('User-agent') == 'SmartFactoryTwin/test-agent'
    assert request.get_header('Authorization') == 'Bearer test-transcription-secret'
    assert request.full_url == 'https://api.groq.com/openai/v1/audio/transcriptions'
    assert b'name="model"' in request.data and settings.TRANSCRIPTION_MODEL.encode() in request.data
    assert b'name="language"' in request.data and settings.TRANSCRIPTION_LANGUAGE.encode() in request.data
    assert settings.TRANSCRIPTION_PROMPT.encode() in request.data


@pytest.mark.django_db
def test_transcription_rate_limit_is_per_user(transcription_user, monkeypatch):
    cache.clear()
    fake_success(monkeypatch)
    monkeypatch.setattr('apps.voice.throttles.VoiceTranscriptionThrottle.THROTTLE_RATES', {
        'voice_transcribe': '1/min',
    })
    client = auth_client(transcription_user)
    assert client.post('/api/voice/transcribe/', {'audio': audio_upload()}, format='multipart').status_code == 200
    assert client.post('/api/voice/transcribe/', {'audio': audio_upload()}, format='multipart').status_code == 429


@pytest.mark.django_db
def test_audio_is_not_persisted_and_upload_is_closed(transcription_user, monkeypatch):
    captured = {}

    def respond(upload):
        captured['upload'] = upload
        return 'texte', 'whisper-large-v3-turbo', 'fr'

    monkeypatch.setattr('apps.voice.transcription_api.transcribe', respond)
    response = auth_client(transcription_user).post(
        '/api/voice/transcribe/', {'audio': audio_upload()}, format='multipart',
    )
    assert response.status_code == 200
    assert captured['upload'].closed
    assert VoiceAgentRequest.objects.count() == 0
    assert VoiceConversation.objects.count() == 0
    assert VoiceActionProposal.objects.count() == 0
    audit_details = AuditLog.objects.latest('pk').details
    assert 'audio' not in audit_details


@pytest.mark.django_db
def test_provider_key_is_absent_from_response_and_logs(transcription_user, monkeypatch, settings):
    key = 'gsk_test_transcription_secret_123456789'
    settings.TRANSCRIPTION_API_KEY = key
    messages = []
    monkeypatch.setattr(
        'apps.voice.transcription.logger.warning',
        lambda *args: messages.append(' '.join(str(value) for value in args)),
    )
    monkeypatch.setattr(
        'apps.voice.transcription.urlopen',
        lambda *args, **kwargs: (_ for _ in ()).throw(HTTPError(
            'https://api.groq.com', 401, 'unauthorized', {}, io.BytesIO(f'api_key={key}'.encode()),
        )),
    )
    response = auth_client(transcription_user).post(
        '/api/voice/transcribe/', {'audio': audio_upload()}, format='multipart',
    )
    assert response.status_code == 503
    assert key not in json.dumps(response.data)
    assert key not in ' '.join(messages)

