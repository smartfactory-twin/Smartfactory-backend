"""Client minimal de chat completions compatible OpenAI, sans journaliser les secrets."""
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings


class LLMConfigurationError(Exception):
    pass


class LLMUnavailableError(Exception):
    pass


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
        if api_key:
            headers['Authorization'] = f'Bearer {api_key}'
        request = Request(f'{base_url}/chat/completions', data=payload, headers=headers, method='POST')
        try:
            with urlopen(request, timeout=min(configured_timeout, timeout or configured_timeout)) as response:
                data = json.loads(response.read(2_000_001).decode('utf-8'))
        except (HTTPError, URLError, TimeoutError, OSError, UnicodeDecodeError, json.JSONDecodeError):
            # Do not include provider response bodies, URLs, headers, or credentials in errors.
            raise LLMUnavailableError('Le fournisseur LLM est indisponible.') from None
        if not isinstance(data, dict) or not data.get('choices'):
            raise LLMUnavailableError('Le fournisseur LLM a renvoyé une réponse invalide.')
        message = data['choices'][0].get('message')
        if not isinstance(message, dict):
            raise LLMUnavailableError('Le fournisseur LLM a renvoyé une réponse invalide.')
        return message


def get_llm_client():
    return OpenAICompatibleClient()
