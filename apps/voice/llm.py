"""Client minimal de chat completions compatible OpenAI, sans journaliser les secrets."""
import json
import logging
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings


logger = logging.getLogger(__name__)
_JWT_PATTERN = re.compile(r'\beyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\b')
_CREDENTIAL_PATTERN = re.compile(
    r'(?i)(authorization|api[_-]?key|secret|token)(\s*[:=]\s*["\']?)[^"\'\s,}]+',
)
_BEARER_PATTERN = re.compile(r'(?i)Bearer\s+[^\s,;"\']+')


class LLMConfigurationError(Exception):
    pass


class LLMUnavailableError(Exception):
    pass


def _safe_error_body(error_body, api_key):
    """Bound and redact provider error text before it reaches server logs."""
    if isinstance(error_body, bytes):
        text = error_body.decode('utf-8', errors='replace')
    else:
        text = str(error_body or '')
    if api_key:
        text = text.replace(api_key, '[REDACTED]')
    text = _BEARER_PATTERN.sub('Bearer [REDACTED]', text)
    text = _JWT_PATTERN.sub('[REDACTED JWT]', text)
    text = _CREDENTIAL_PATTERN.sub(r'\1\2[REDACTED]', text)
    return ' '.join(text.split())[:500]


def _configuration():
    provider = (settings.LLM_PROVIDER or '').strip()
    base_url = (settings.LLM_BASE_URL or '').strip().rstrip('/')
    model = (settings.LLM_MODEL or '').strip()
    api_key = (settings.LLM_API_KEY or '').strip()
    timeout = settings.LLM_TIMEOUT_SECONDS
    if not provider or not base_url or not model or timeout <= 0:
        raise LLMConfigurationError('Configuration LLM incomplète ou invalide.')
    if not api_key and provider.lower() not in {'ollama', 'local'}:
        raise LLMConfigurationError('La clé API LLM est absente.')
    if not base_url.startswith(('https://', 'http://localhost', 'http://127.0.0.1')):
        raise LLMConfigurationError('LLM_BASE_URL doit être HTTPS, sauf pour un fournisseur local.')
    return base_url, model, api_key, timeout


class OpenAICompatibleClient:
    def complete(self, messages, tools, timeout=None):
        base_url, model, api_key, configured_timeout = _configuration()
        payload = json.dumps({
            'model': model,
            'messages': messages,
            'tools': tools,
            'tool_choice': 'auto',
            'max_tokens': 700,
            'temperature': 0,
        }).encode('utf-8')
        headers = {'Content-Type': 'application/json'}
        headers['User-Agent'] = settings.LLM_USER_AGENT or 'SmartFactoryTwin/1.0'
        if api_key:
            headers['Authorization'] = f'Bearer {api_key}'
        request = Request(f'{base_url}/chat/completions', data=payload, headers=headers, method='POST')
        try:
            with urlopen(request, timeout=min(configured_timeout, timeout or configured_timeout)) as response:
                data = json.loads(response.read(2_000_001).decode('utf-8'))
        except HTTPError as exc:
            try:
                error_body = exc.read(5001)
            except Exception:
                error_body = ''
            logger.warning(
                'LLM provider request failed exception_type=%s http_status=%s provider_body=%s',
                type(exc).__name__, exc.code, _safe_error_body(error_body, api_key),
            )
            # The client response intentionally stays generic; diagnostics stay server-side.
            raise LLMUnavailableError('Le fournisseur LLM est indisponible.') from None
        except (URLError, TimeoutError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            logger.warning('LLM provider request failed exception_type=%s', type(exc).__name__)
            raise LLMUnavailableError('Le fournisseur LLM est indisponible.') from None
        if not isinstance(data, dict) or not data.get('choices'):
            logger.warning('LLM provider response invalid exception_type=InvalidProviderResponse reason=missing_choices')
            raise LLMUnavailableError('Le fournisseur LLM a renvoyé une réponse invalide.')
        message = data['choices'][0].get('message')
        if not isinstance(message, dict):
            logger.warning('LLM provider response invalid exception_type=InvalidProviderResponse reason=missing_message')
            raise LLMUnavailableError('Le fournisseur LLM a renvoyé une réponse invalide.')
        return message


def get_llm_client():
    return OpenAICompatibleClient()
