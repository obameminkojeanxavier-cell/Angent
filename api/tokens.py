import hashlib
import secrets

from django.conf import settings

# --- Scopes (permissions) ---------------------------------------------------
SCOPE_DATA_READ = 'data:read'      # lister, schéma, select, search
SCOPE_DATA_WRITE = 'data:write'    # insert, update, delete
SCOPE_TABLES = 'tables:manage'     # create_table, add_column
SCOPE_SKILLS = 'skills:trigger'    # déclencher des skills, lire/écrire ses tâches
SCOPE_AUDIT = 'audit:read'         # consulter le journal d'audit

ALL_SCOPES = [
    SCOPE_DATA_READ, SCOPE_DATA_WRITE, SCOPE_TABLES, SCOPE_SKILLS, SCOPE_AUDIT,
]


def hash_token(raw):
    """SHA-256 hex du token en clair."""
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def generate_token():
    """Nouveau token aléatoire (URL-safe)."""
    return secrets.token_urlsafe(32)


def master_client():
    """
    Client synthétique (non enregistré en base) correspondant au token maître
    défini dans .env (API_TOKEN). Il possède tous les scopes et toutes les
    tables. Sert de compte d'administration / compatibilité ascendante.
    """
    from .models import AgentClient
    return AgentClient(
        name='master',
        description='Master token (.env API_TOKEN)',
        scopes=['*'],
        allowed_tables=[],
        is_active=True,
    )


def resolve_client(raw):
    """
    Résout un token en clair vers un AgentClient.

    Ordre : token maître (.env) d'abord, puis recherche en base par hash.
    Renvoie None si le token est inconnu ou le client désactivé.
    """
    if not raw:
        return None

    master = getattr(settings, 'API_TOKEN', '')
    if master and secrets.compare_digest(raw, master):
        return master_client()

    from .models import AgentClient
    try:
        return AgentClient.objects.get(token_hash=hash_token(raw), is_active=True)
    except AgentClient.DoesNotExist:
        return None
