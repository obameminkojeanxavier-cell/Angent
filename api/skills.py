"""
Registre de skills.

Un skill est une fonction nommée `fn(params: dict, client) -> dict` déclenchable
via l'API (POST /api/skills/<name>/run/) ou via MCP. Ajouter un skill = décorer
une fonction avec @register('nom').
"""
from .db_operations import DatabaseOperations
from .tokens import SCOPE_SKILLS

_REGISTRY = {}


def register(name, description='', scope=SCOPE_SKILLS):
    def deco(fn):
        _REGISTRY[name] = {
            'name': name,
            'description': description,
            'scope': scope,
            'fn': fn,
        }
        return fn
    return deco


def get_skill(name):
    return _REGISTRY.get(name)


def list_skills():
    return [
        {'name': s['name'], 'description': s['description'], 'scope': s['scope']}
        for s in _REGISTRY.values()
    ]


# --- Skills fournis par défaut ---------------------------------------------

@register('ping', 'Test de connectivité : renvoie les paramètres reçus.')
def _ping(params, client):
    return {'pong': True, 'echo': params}


@register('db.stats', 'Nombre de lignes par table accessible au client.')
def _db_stats(params, client):
    out = {}
    for table in DatabaseOperations.list_tables():
        if client.can_access_table(table):
            out[table] = DatabaseOperations.count(table)
    return {'tables': out}


@register(
    'db.search',
    "Recherche texte (ILIKE) dans une table. "
    "params: table_name (requis), q (requis), columns (option), limit (option)."
)
def _db_search(params, client):
    table = params.get('table_name')
    if not table:
        raise ValueError("param 'table_name' requis")
    if not client.can_access_table(table):
        raise PermissionError(f'Table non autorisée: {table}')
    results = DatabaseOperations.search(
        table, params.get('q', ''), params.get('columns'), params.get('limit')
    )
    return {'count': len(results), 'results': results}
