"""
Client minimal pour les agents IA externes (DeepSeek, OpenAI, Mistral, Ollama…).

Utilise uniquement la bibliothèque standard (urllib) : aucune dépendance
supplémentaire à installer sur le serveur. L'API visée est celle, très répandue,
des « chat completions » compatibles OpenAI — ce que DeepSeek expose aussi.

Anthropic a un format différent ; il est géré à part.
"""
import json
import urllib.error
import urllib.request

TIMEOUT = 30


def _post_json(url, payload, headers, timeout=TIMEOUT):
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, method='POST')
    req.add_header('Content-Type', 'application/json')
    for k, v in headers.items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode('utf-8', errors='replace')
    return json.loads(body) if body else {}


def _endpoint(provider):
    base = (provider.base_url or '').rstrip('/')
    if provider.provider == 'anthropic':
        return f'{base}/messages'
    # DeepSeek, OpenAI, Mistral, Ollama… exposent /chat/completions.
    if base.endswith('/v1'):
        return f'{base}/chat/completions'
    return f'{base}/v1/chat/completions'


def chat(provider, messages, max_tokens=512, temperature=0.2):
    """
    Envoie une conversation à l'agent IA et renvoie (texte, brut).

    `messages` : liste de {'role': 'system'|'user'|'assistant', 'content': str}
    Lève une exception en cas d'erreur réseau ou HTTP.
    """
    url = _endpoint(provider)

    if provider.provider == 'anthropic':
        headers = {'x-api-key': provider.api_key, 'anthropic-version': '2023-06-01'}
        system = ' '.join(m['content'] for m in messages if m.get('role') == 'system')
        payload = {
            'model': provider.model,
            'max_tokens': max_tokens,
            'messages': [m for m in messages if m.get('role') != 'system'],
        }
        if system:
            payload['system'] = system
        raw = _post_json(url, payload, headers)
        parts = raw.get('content') or []
        text = ''.join(p.get('text', '') for p in parts if isinstance(p, dict))
        return text, raw

    headers = {'Authorization': f'Bearer {provider.api_key}'}
    payload = {
        'model': provider.model,
        'messages': messages,
        'max_tokens': max_tokens,
        'temperature': temperature,
    }
    raw = _post_json(url, payload, headers)
    choices = raw.get('choices') or []
    text = ''
    if choices:
        text = (choices[0].get('message') or {}).get('content', '') or ''
    return text, raw


def test_connection(provider):
    """
    Vérifie la configuration par un appel réel très court.
    Renvoie (ok: bool, detail: str) — jamais d'exception.
    """
    try:
        text, raw = chat(
            provider,
            [{'role': 'user', 'content': "Réponds uniquement par : OK"}],
            max_tokens=16,
        )
    except urllib.error.HTTPError as e:
        body = ''
        try:
            body = e.read().decode('utf-8', errors='replace')[:300]
        except Exception:
            pass
        hint = {
            401: "clé API invalide ou révoquée",
            403: "accès refusé (clé sans droit sur ce modèle)",
            404: "URL ou modèle introuvable — vérifiez base_url et model",
            429: "quota ou limite de débit atteint",
        }.get(e.code, '')
        return False, f'HTTP {e.code} {hint} {body}'.strip()
    except urllib.error.URLError as e:
        return False, f"Serveur injoignable : {e.reason}"
    except Exception as e:
        return False, f'{type(e).__name__}: {e}'

    model = (raw or {}).get('model') or provider.model
    return True, f'Connexion réussie (modèle {model}) — réponse : {(text or "").strip()[:80]}'
