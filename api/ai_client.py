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
    except Exception as e:
        return False, _explain(e)

    model = (raw or {}).get('model') or provider.model
    return True, f'Connexion réussie (modèle {model}) — réponse : {(text or "").strip()[:80]}'


def _explain(exc):
    """Traduit une exception réseau/HTTP en message compréhensible."""
    if isinstance(exc, urllib.error.HTTPError):
        body = ''
        try:
            body = exc.read().decode('utf-8', errors='replace')[:300]
        except Exception:
            pass
        hint = {
            401: "clé API invalide ou révoquée",
            402: "crédit insuffisant sur le compte du fournisseur",
            403: "accès refusé (clé sans droit sur ce modèle)",
            404: "URL ou modèle introuvable — vérifiez l'URL de base et le modèle",
            422: "requête refusée (paramètre invalide)",
            429: "quota ou limite de débit atteint",
        }.get(exc.code, '')
        return f'HTTP {exc.code} — {hint} {body}'.strip()
    if isinstance(exc, urllib.error.URLError):
        return f"serveur injoignable : {exc.reason}"
    return f'{type(exc).__name__}: {exc}'


def verify(provider, message=None):
    """
    Système de vérification d'un agent IA : enchaîne plusieurs contrôles et
    renvoie un rapport détaillé (jamais d'exception).

    Renvoie {'ok': bool, 'checks': [{'name', 'ok', 'detail'}], 'reply': str}
    """
    import time

    checks = []
    reply = ''

    def add(name, ok, detail=''):
        checks.append({'name': name, 'ok': bool(ok), 'detail': detail})
        return ok

    # 1. Configuration
    missing = [f for f, v in (
        ("URL de base", provider.base_url),
        ("modèle", provider.model),
    ) if not str(v or '').strip()]
    add("Configuration complète", not missing,
        f"champs manquants : {', '.join(missing)}" if missing
        else f'{provider.provider} · {provider.model} · {provider.base_url}')

    # 2. Clé API présente
    add("Clé API renseignée", provider.has_key,
        provider.key_masked or "aucune clé enregistrée")

    # 3. Instructions principales
    prompt = (provider.system_prompt or '').strip()
    add("Instructions principales définies", bool(prompt),
        f'{len(prompt)} caractères' if prompt
        else "aucune instruction : l'agent n'aura pas de cadre de fonctionnement")

    # 4. Agent actif
    add("Agent actif", provider.is_active,
        "actif" if provider.is_active else "désactivé : il ne sera pas utilisé")

    if not provider.has_key or missing:
        return {'ok': False, 'checks': checks, 'reply': reply}

    # 5. Appel réel, avec les instructions configurées
    messages = []
    if prompt:
        messages.append({'role': 'system', 'content': prompt})
    messages.append({'role': 'user', 'content': message or provider.test_message
                     or "Ceci est un test. Indique ton rôle en une phrase."})

    started = time.monotonic()
    try:
        reply, raw = chat(provider, messages,
                          max_tokens=min(provider.max_tokens or 256, 256),
                          temperature=provider.temperature)
    except Exception as e:
        add("Authentification et appel du modèle", False, _explain(e))
        return {'ok': False, 'checks': checks, 'reply': ''}

    elapsed = int((time.monotonic() - started) * 1000)
    model = (raw or {}).get('model') or provider.model
    add("Authentification et appel du modèle", True, f'modèle {model} · {elapsed} ms')

    # 6. Réponse exploitable
    add("Réponse reçue", bool((reply or '').strip()),
        f'{len(reply or "")} caractères'
        if (reply or '').strip() else "réponse vide : vérifiez le modèle choisi")

    usage = (raw or {}).get('usage') or {}
    if usage:
        add("Consommation de jetons", True,
            f"entrée {usage.get('prompt_tokens', '?')} · "
            f"sortie {usage.get('completion_tokens', '?')}")

    return {'ok': all(c['ok'] for c in checks), 'checks': checks, 'reply': reply or ''}
