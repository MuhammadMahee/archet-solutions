"""Bounded, server-only Vercel AI Gateway integration using its compatible API."""
import json
import os
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, HTTPRedirectHandler

from api.workforce_ai import AIError

DEFAULT_MODEL = 'google/gemini-2.5-flash-lite'
GROQ_MODEL = 'llama-3.3-70b-versatile'


def provider():
    selected = os.getenv('WORKFORCE_AI_PROVIDER', 'vercel' if os.getenv('VERCEL') else 'ollama').strip().lower()
    if selected not in ('vercel', 'groq', 'ollama') or (os.getenv('VERCEL') and selected == 'ollama'):
        raise AIError('Choose vercel or groq for WORKFORCE_AI_PROVIDER on Vercel. Ollama mode is for local development.')
    return selected


def hosted():
    return provider() != 'ollama'


def default_model():
    if provider() == 'groq':
        return os.getenv('GROQ_MODEL', GROQ_MODEL)
    return os.getenv('WORKFORCE_MODEL', DEFAULT_MODEL) if hosted() else os.getenv('OLLAMA_MODEL', 'qwen3:1.7b')


def model_setting():
    return 'model:groq' if provider() == 'groq' else 'model'


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise AIError('AI Gateway redirected the request. Retry later.')


class VercelAI:
    endpoint = 'https://ai-gateway.vercel.sh/v1/chat/completions'
    label = 'AI Gateway'
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
        payload = self.prepare_payload(payload, schema)
        req = Request(self.endpoint,
                      data=json.dumps(payload).encode(), headers={
                          'Authorization': 'Bearer ' + self.key, 'Content-Type': 'application/json',
                          'Accept': 'application/json', 'User-Agent': 'ArchetWorkforce/1.0'})
        try:
            with build_opener(NoRedirect()).open(req, timeout=min(45, remaining)) as response:
                raw = response.read(1000001)
                if len(raw) > 1000000:
                    raise AIError(self.label + ' returned an oversized answer.')
                choice = json.loads(raw)['choices'][0]
                answer = choice['message']['content']
                if (choice.get('finish_reason') != 'stop' or not isinstance(answer, str)
                        or not answer.strip() or len(answer) > 12000):
                    raise AIError('The model returned an incomplete answer. Retry with a shorter request.')
                return answer.strip()
        except HTTPError as exc:
            self.http_error(exc)
        except (URLError, OSError):
            raise AIError(self.label + ' is unavailable or timed out. Retry later.') from None
        except (ValueError, KeyError, IndexError, TypeError):
            raise AIError(self.label + ' returned an invalid answer. Retry later.') from None

    def prepare_payload(self, payload, schema):
        return payload

    def http_error(self, exc):
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


class GroqAI(VercelAI):
    endpoint = 'https://api.groq.com/openai/v1/chat/completions'
    label = 'Groq'

    def __init__(self):
        # Never reuse Gateway/OIDC credentials or fall back to a paid provider.
        self.key = os.getenv('GROQ_API_KEY', '').strip()
        self.deadline = time.monotonic() + 180

    def models(self):
        configured = os.getenv('GROQ_MODELS', os.getenv('GROQ_MODEL', GROQ_MODEL))
        return list(dict.fromkeys(m.strip() for m in configured.split(',') if m.strip()))

    def local_model(self, model):
        if not self.key:
            raise AIError('Add your free Groq account API key as GROQ_API_KEY in Vercel Production, then redeploy.')
        if model not in self.models():
            raise AIError('This assignment uses a model unavailable on Groq. Send a new message or select a configured Groq model.')

    def prepare_payload(self, payload, schema):
        if schema:
            # Llama supports JSON object mode. The executor independently checks
            # every plan field, permitted action, date range and dealer value.
            payload['response_format'] = {'type': 'json_object'}
            payload['messages'][0]['content'] += '\nReturn a JSON object matching this schema exactly: ' + json.dumps(schema)
        return payload

    def http_error(self, exc):
        if exc.code == 401:
            raise AIError('Groq rejected GROQ_API_KEY (HTTP 401). Check that Vercel Production contains a valid Groq API key, then redeploy if it changed.') from None
        if exc.code == 403:
            raw = ''
            try:
                raw = exc.read(8192).decode('utf-8', errors='replace')
                detail = json.loads(raw).get('error', {})
                code = detail.get('code') if isinstance(detail, dict) else None
            except (ValueError, AttributeError, OSError):
                code = None
            if code in ('model_permission_blocked_org', 'model_permission_blocked_project'):
                raise AIError('Groq has blocked this model (HTTP 403). Enable the selected model in Groq organization/project model permissions, then retry.') from None
            if '1010' in raw:
                raise AIError('Groq blocked the app request at its network filter (HTTP 403, error 1010). Contact your administrator to check the deployed HTTP client; this does not establish that the API key is invalid.') from None
            raise AIError('Groq denied this request (HTTP 403). Check Groq account/project access or contact Groq support; the response did not identify an invalid API key.') from None
        if exc.code == 429:
            raise AIError('Groq free-tier usage limit reached. Wait for your quota to reset, then retry. No fallback provider was used.') from None
        if exc.code == 402:
            raise AIError('Groq account access needs review. Use a Free-plan account; this app does not purchase credits or upgrade your plan.') from None
        raise AIError('Groq could not process this assignment. Check the model and request limits, then retry.') from None
