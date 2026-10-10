"""Bounded, server-only Vercel AI Gateway integration using its compatible API."""
import json
import os
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, HTTPRedirectHandler

from api.workforce_ai import AIError

DEFAULT_MODEL = 'google/gemini-2.5-flash-lite'


def hosted():
    provider = os.getenv('WORKFORCE_AI_PROVIDER', 'vercel' if os.getenv('VERCEL') else 'ollama').strip().lower()
    if provider not in ('vercel', 'ollama') or (os.getenv('VERCEL') and provider != 'vercel'):
        raise AIError('Set WORKFORCE_AI_PROVIDER=vercel on Vercel. Ollama mode is for local development.')
    return provider == 'vercel'


def default_model():
    return os.getenv('WORKFORCE_MODEL', DEFAULT_MODEL) if hosted() else os.getenv('OLLAMA_MODEL', 'qwen3:1.7b')


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise AIError('AI Gateway redirected the request. Retry later.')


class VercelAI:
    def __init__(self):
        api_key = os.getenv('AI_GATEWAY_API_KEY', '').strip()
        self.key = api_key or os.getenv('VERCEL_OIDC_TOKEN', '').strip()
        self.auth_method = 'API key' if api_key else 'automatic Vercel authentication'
        self.deadline = time.monotonic() + 180

    def models(self):
        # Explicit allowlist controls model selection and unexpected costs.
        configured = os.getenv('WORKFORCE_MODELS', os.getenv('WORKFORCE_MODEL', DEFAULT_MODEL))
        return list(dict.fromkeys(m.strip() for m in configured.split(',') if m.strip()))

    def local_model(self, model):
        # Retain the executor's provider validation interface.
        if not self.key:
            raise AIError('Enable Vercel AI Gateway or configure AI_GATEWAY_API_KEY in Vercel, then redeploy.')
        if model not in self.models():
            raise AIError('Select a configured AI Gateway model for this assignment.')

    def chat(self, model, system, content, schema=None):
        self.local_model(model)
        remaining = self.deadline - time.monotonic()
        if remaining <= 5:
            raise AIError('The assignment reached its time limit. Retry with a shorter request.')
        payload = {'model': model, 'messages': [{'role': 'system', 'content': system},
                                               {'role': 'user', 'content': content}],
                   'max_tokens': 1200, 'temperature': 0, 'stream': False}
        if schema:
            payload['response_format'] = {'type': 'json_schema', 'json_schema': {
                'name': 'workforce_plan', 'strict': True, 'schema': schema}}
        req = Request('https://ai-gateway.vercel.sh/v1/chat/completions',
                      data=json.dumps(payload).encode(), headers={
                          'Authorization': 'Bearer ' + self.key, 'Content-Type': 'application/json'})
        try:
            with build_opener(NoRedirect()).open(req, timeout=min(45, remaining)) as response:
                raw = response.read(1000001)
                if len(raw) > 1000000:
                    raise AIError('AI Gateway returned an oversized answer.')
                choice = json.loads(raw)['choices'][0]
                answer = choice['message']['content']
                if (choice.get('finish_reason') != 'stop' or not isinstance(answer, str)
                        or not answer.strip() or len(answer) > 12000):
                    raise AIError('The model returned an incomplete answer. Retry with a shorter request.')
                return answer.strip()
        except HTTPError as exc:
            if exc.code == 401:
                if self.auth_method == 'API key':
                    raise AIError('AI Gateway rejected AI_GATEWAY_API_KEY (HTTP 401). Replace it with an AI Gateway key in Vercel Production, then redeploy. A saved API key overrides automatic authentication.') from None
                raise AIError('AI Gateway rejected automatic Vercel authentication (HTTP 401). Add AI_GATEWAY_API_KEY to Vercel Production and redeploy, or check the project OIDC settings.') from None
            if exc.code == 403:
                # Classify known setup errors without exposing arbitrary upstream
                # text, credentials, request identifiers or account details.
                try:
                    detail = json.loads(exc.read(8192)).get('error', {})
                    message = (detail.get('message', '') if isinstance(detail, dict) else '').lower()
                except (ValueError, TypeError, AttributeError, OSError):
                    message = ''
                if 'credit card' in message or 'payment method' in message:
                    raise AIError('AI Gateway requires billing verification (HTTP 403). Review the payment-method requirement in your Vercel AI Gateway dashboard, then retry.') from None
                raise AIError('AI Gateway denied access (HTTP 403). Check AI Gateway access, key permissions, and billing verification for the Vercel team that owns this project.') from None
            if exc.code in (402, 429):
                raise AIError('AI Gateway credits or rate limit reached. Check usage in Vercel before retrying.') from None
            raise AIError('AI Gateway could not process the assignment. Check the configured model and retry.') from None
        except (URLError, OSError):
            raise AIError('AI Gateway is unavailable or timed out. Retry later.') from None
        except (ValueError, KeyError, IndexError, TypeError):
            raise AIError('AI Gateway returned an invalid answer. Retry later.') from None
