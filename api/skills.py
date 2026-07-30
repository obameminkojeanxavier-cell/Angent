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


def orchestrator_active():
    """True si au moins un skill orchestrateur actif est installé."""
    try:
        from .models import Skill
        return Skill.objects.filter(is_orchestrator=True, is_active=True).exists()
    except Exception:
        return False


def get_skill(name):
    """Skill NATIF (exécutable côté serveur). None si absent."""
    return _REGISTRY.get(name)


def list_skills():
    """Catalogue complet : skills natifs + skills injectés en base.

    Chaque entrée : name, description, category, source (builtin|db).
    """
    items = [
        {'name': s['name'], 'description': s['description'],
         'category': 'builtin', 'source': 'builtin'}
        for s in _REGISTRY.values()
    ]
    try:
        from .models import Skill
        for s in Skill.objects.filter(is_active=True):
            items.append({
                'name': s.name,
                'description': s.description,
                'category': s.category or 'db',
                'source': 'db',
            })
    except Exception:
        # Base non migrée / indisponible : on renvoie au moins les natifs.
        pass
    return items


def get_definition(name):
    """Définition COMPLÈTE d'un skill (pour que l'agent le comprenne).

    Renvoie un dict avec instructions + exemple, ou None si introuvable.
    """
    s = _REGISTRY.get(name)
    if s:
        return {
            'name': s['name'],
            'description': s['description'],
            'category': 'builtin',
            'source': 'builtin',
            'executable': True,
            'instructions': (
                "Skill natif exécuté côté serveur. Déclenche-le via "
                "POST /api/skills/%s/run/ avec ses paramètres." % s['name']
            ),
            'input_example': None,
        }
    try:
        from .models import Skill
        d = Skill.objects.get(name=name, is_active=True)
    except Exception:
        return None
    files = [
        {'path': f.path, 'content_type': f.content_type, 'size': len(f.content or '')}
        for f in d.files.all()
    ]
    return {
        'name': d.name,
        'description': d.description,
        'category': d.category,
        'source': 'db',
        'executable': True,
        # Instructions principales = contenu de SKILL.md si présent.
        'instructions': d.entry_instructions,
        'input_example': d.input_example,
        # Le skill est un dossier : liste de ses fichiers (à lire via getSkillFile).
        'files': files,
    }


def get_skill_file(name, path):
    """Contenu d'un fichier d'un skill (skill = dossier). None si introuvable."""
    try:
        from .models import Skill, SkillFile
        skill = Skill.objects.get(name=name, is_active=True)
        f = SkillFile.objects.get(skill=skill, path=path)
    except Exception:
        return None
    return {'path': f.path, 'content_type': f.content_type, 'content': f.content}


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
