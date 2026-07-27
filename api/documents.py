"""
Moteur d'exécution de documents par des skills/agents.

Un « processeur de document » reçoit le document importé + un traceur, effectue
ses opérations (lecture/écriture base, traitements) en journalisant chaque
étape, et renvoie un résultat. La trace est ensuite affichée dans l'interface.
"""
from .db_operations import DatabaseOperations


class Tracer:
    """Collecte les étapes d'exécution pour affichage en temps réel."""

    def __init__(self):
        self.steps = []

    def add(self, label, kind='step', status='ok', detail=None):
        self.steps.append({'label': label, 'kind': kind, 'status': status, 'detail': detail})

    def db(self, label, detail=None):
        self.add(label, kind='db', status='ok', detail=detail)

    def info(self, label, detail=None):
        self.add(label, kind='step', status='ok', detail=detail)

    def error(self, label, detail=None):
        self.add(label, kind='error', status='error', detail=detail)


_DOC_PROCESSORS = {}


def register_doc(name, description=''):
    def deco(fn):
        _DOC_PROCESSORS[name] = {'name': name, 'description': description, 'fn': fn}
        return fn
    return deco


def list_doc_processors():
    return [{'name': v['name'], 'description': v['description']} for v in _DOC_PROCESSORS.values()]


def get_doc_processor(name):
    return _DOC_PROCESSORS.get(name)


def run_document(name, doc, client, tracer):
    proc = get_doc_processor(name)
    if not proc:
        raise KeyError(f"Skill de document inconnu : {name}")
    return proc['fn'](doc, client, tracer)


# --- Processeurs par défaut -------------------------------------------------

@register_doc('document.ingest', "Enregistre le document dans la table 'documents' (créée automatiquement si absente).")
def _ingest(doc, client, tracer):
    tracer.info(f"Document reçu : {doc['filename']} ({doc['size']} octets)")

    tables = DatabaseOperations.list_tables()
    tracer.db("Lecture de la liste des tables", {'nb_tables': len(tables)})

    if 'documents' not in tables:
        DatabaseOperations.create_table('documents', {
            'filename': 'varchar(255)',
            'taille': 'integer',
            'apercu': 'text',
            'contenu': 'text',
        })
        tracer.db("Table 'documents' créée (filename, taille, apercu, contenu)")
    else:
        tracer.db("Table 'documents' déjà présente")

    record = DatabaseOperations.insert('documents', {
        'filename': doc['filename'],
        'taille': doc['size'],
        'apercu': doc['preview'],
        'contenu': doc['text'],
    })
    row_id = record.get('id') if isinstance(record, dict) else record
    tracer.db(f"Ligne insérée dans 'documents' (id={row_id})", {'id': row_id})
    tracer.info("Traitement terminé avec succès")
    return {'table': 'documents', 'id': row_id, 'inserted': True}


@register_doc('document.analyze', "Analyse le texte (caractères, mots, lignes) sans rien écrire en base.")
def _analyze(doc, client, tracer):
    tracer.info(f"Document reçu : {doc['filename']} ({doc['size']} octets)")
    text = doc['text']
    stats = {
        'caracteres': len(text),
        'mots': len(text.split()),
        'lignes': (text.count('\n') + 1) if text else 0,
    }
    tracer.info("Analyse du contenu effectuée", stats)
    return stats
