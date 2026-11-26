"""Client HTTP minimal pour la transcription Groq compatible OpenAI."""
import json
import logging
import re
import uuid
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from django.conf import settings


logger = logging.getLogger(__name__)
_BEARER_PATTERN = re.compile(r'(?i)Bearer\s+[^\s,;]+')
_JWT_PATTERN = re.compile(r'\beyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\b')
_SECRET_PATTERN = re.compile(r'(?i)(api[_-]?key|authorization|secret|token)(\s*[:=]\s*)[^\s,;]+')


class TranscriptionConfigurationError(Exception):
    pass


class TranscriptionUnavailableError(Exception):
    pass


def _safe_error_body(body, api_key):
    text = body.decode('utf-8', errors='replace') if isinstance(body, bytes) else str(body or '')
    if api_key:
        text = text.replace(api_key, '[REDACTED]')
    text = _BEARER_PATTERN.sub('Bearer [REDACTED]', text)
    text = _JWT_PATTERN.sub('[REDACTED JWT]', text)
    text = _SECRET_PATTERN.sub(r'\1\2[REDACTED]', text)
    return ' '.join(text.split())[:500]


def _configuration():
    base_url = (settings.TRANSCRIPTION_BASE_URL or settings.LLM_BASE_URL or '').strip().rstrip('/')
    api_key = (settings.TRANSCRIPTION_API_KEY or settings.LLM_API_KEY or '').strip()
    model = (settings.TRANSCRIPTION_MODEL or 'whisper-large-v3-turbo').strip()
    language = (settings.TRANSCRIPTION_LANGUAGE or 'fr').strip()
    prompt = (settings.TRANSCRIPTION_PROMPT or '').strip()
    user_agent = (settings.LLM_USER_AGENT or 'SmartFactoryTwin/1.0').strip()
    timeout = settings.LLM_TIMEOUT_SECONDS
    if not base_url or not model or not language or not api_key or timeout <= 0:
        raise TranscriptionConfigurationError('Configuration de transcription incomplète ou invalide.')
    if not base_url.startswith(('https://', 'http://localhost', 'http://127.0.0.1')):
        raise TranscriptionConfigurationError('TRANSCRIPTION_BASE_URL doit être HTTPS, sauf fournisseur local.')
    if not user_agent:
        raise TranscriptionConfigurationError('LLM_USER_AGENT ne peut pas être vide.')
    return base_url, api_key, model, language, prompt, user_agent, timeout


def _multipart_body(audio_bytes, filename, content_type, model, language, prompt, boundary):
    safe_name = str(filename or 'audio.bin').replace('\\', '/').split('/')[-1].replace('"', '')[:120]
    chunks = []
    fields = {'model': model, 'language': language, 'prompt': prompt, 'response_format': 'json'}
    for name, value in fields.items():
        chunks.extend((
            f'--{boundary}\r\n'.encode(),
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
            str(value).encode('utf-8'), b'\r\n',
        ))
    chunks.extend((
        f'--{boundary}\r\n'.encode(),
        f'Content-Disposition: form-data; name="file"; filename="{safe_name}"\r\n'.encode(),
        f'Content-Type: {content_type}\r\n\r\n'.encode(),
        audio_bytes, b'\r\n', f'--{boundary}--\r\n'.encode(),
    ))
    return b''.join(chunks)


def transcribe(audio_file):
    base_url, api_key, model, language, prompt, user_agent, timeout = _configuration()
    try:
        audio_file.seek(0)
        audio_bytes = audio_file.read()
        boundary = f'----SmartFactoryTwin{uuid.uuid4().hex}'
        body = _multipart_body(
            audio_bytes, getattr(audio_file, 'name', 'audio.bin'),
            getattr(audio_file, 'content_type', None) or 'application/octet-stream',
            model, language, prompt, boundary,
        )
        request = Request(
            f'{base_url}/audio/transcriptions', data=body, method='POST',
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': f'multipart/form-data; boundary={boundary}',
                'User-Agent': user_agent,
            },
        )
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read(1_000_001).decode('utf-8'))
    except HTTPError as exc:
        try:
            error_body = exc.read(5001)
        except Exception:
            error_body = b''
        logger.warning(
            'Transcription provider failed exception_type=%s http_status=%s provider_body=%s',
            type(exc).__name__, exc.code, _safe_error_body(error_body, api_key),
        )
        raise TranscriptionUnavailableError from None
    except Exception as exc:
        logger.warning('Transcription provider failed exception_type=%s', type(exc).__name__)
        raise TranscriptionUnavailableError from None
    if not isinstance(payload, dict) or not isinstance(payload.get('text'), str):
        logger.warning('Transcription provider response invalid exception_type=%s', 'InvalidResponse')
        raise TranscriptionUnavailableError from None
    return payload['text'], model, language
