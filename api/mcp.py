"""
Serveur MCP HTTP pour DataHub.

Expose les mêmes opérations que l'API REST sous forme d'outils MCP (Model
Context Protocol), sur un unique endpoint HTTP en JSON-RPC 2.0 (transport
« Streamable HTTP », mode sans session / stateless).

Authentification et permissions identiques au REST : token Bearer résolu vers
un AgentClient, scopes vérifiés par outil, opérations journalisées (audit).

ORCHESTRATION : Tous les appels doivent passer par le skill orchestrateur.
"""
import json

from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt

from .db_operations import DatabaseOperations
from .tokens import (
    resolve_client, SCOPE_DATA_READ, SCOPE_DATA_WRITE, SCOPE_TABLES, SCOPE_SKILLS,
)
from .audit import audit
from . import skills as skills_registry
from .models import SkillTask, Skill

DEFAULT_PROTOCOL_VERSION = "2025-06-18"
SERVER_INFO = {"name": "datahub", "version": "2.0.0"}

# --- Outils exposés + scope requis -----------------------------------------

TOOLS = [
    {
        "name": "list_tables",
        "description": "Lister toutes les tables.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "get_table_schema",
        "description": "Schéma (colonnes/types) d'une table.",
        "inputSchema": {
            "type": "object",
            "properties": {"table_name": {"type": "string"}},
            "required": ["table_name"], "additionalProperties": False,
        },
    },
    {
        "name": "select",
        "description": "Lire des lignes. filters (option) = égalité de colonnes, limit (option, max 1000).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "table_name": {"type": "string"},
                "filters": {"type": "object"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 1000},
            },
            "required": ["table_name"], "additionalProperties": False,
        },
    },
    {
        "name": "search",
        "description": "Recherche texte (ILIKE). table_name + q requis ; columns/limit optionnels.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "table_name": {"type": "string"},
                "q": {"type": "string"},
                "columns": {"type": "array", "items": {"type": "string"}},
                "limit": {"type": "integer", "minimum": 1, "maximum": 1000},
            },
            "required": ["table_name", "q"], "additionalProperties": False,
        },
    },
    {
        "name": "create_table",
        "description": "Créer une table. columns = {nom: type_sql}. id et created_at ajoutés automatiquement.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "table_name": {"type": "string"},
                "columns": {"type": "object", "additionalProperties": {"type": "string"}},
            },
            "required": ["table_name", "columns"], "additionalProperties": False,
        },
    },
    {
        "name": "add_column",
        "description": "Ajouter une colonne à une table.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "table_name": {"type": "string"},
                "column_name": {"type": "string"},
                "column_type": {"type": "string"},
            },
            "required": ["table_name", "column_name", "column_type"], "additionalProperties": False,
        },
    },
    {
        "name": "insert",
        "description": "Insérer une ligne. data = {colonne: valeur}. Renvoie l'enregistrement complet.",
        "inputSchema": {
            "type": "object",
            "properties": {"table_name": {"type": "string"}, "data": {"type": "object"}},
            "required": ["table_name", "data"], "additionalProperties": False,
        },
    },
    {
        "name": "update",
        "description": "Mettre à jour. data = nouvelles valeurs, filters = WHERE (obligatoire).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "table_name": {"type": "string"}, "data": {"type": "object"}, "filters": {"type": "object"},
            },
            "required": ["table_name", "data", "filters"], "additionalProperties": False,
        },
    },
    {
        "name": "delete",
        "description": "Supprimer des lignes correspondant à filters (obligatoire).",
        "inputSchema": {
            "type": "object",
            "properties": {"table_name": {"type": "string"}, "filters": {"type": "object"}},
            "required": ["table_name", "filters"], "additionalProperties": False,
        },
    },
    {
        "name": "list_skills",
        "description": "Lister les skills disponibles.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "run_skill",
        "description": "Déclencher un skill. name = nom du skill, params = objet de paramètres. Renvoie la tâche.",
        "inputSchema": {
            "type": "object",
            "properties": {"name": {"type": "string"}, "params": {"type": "object"}},
            "required": ["name"], "additionalProperties": False,
        },
    },
    {
        "name": "get_task",
        "description": "État et résultat d'une tâche de skill.",
        "inputSchema": {
            "type": "object",
            "properties": {"task_id": {"type": "string"}},
            "required": ["task_id"], "additionalProperties": False,
        },
    },
    # Outils métier spécifiques pour ChatGPT
    {
        "name": "create_document",
        "description": "Créer un document dans la table 'documents'. Champs: titre (requis), contenu, auteur, statut.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "titre": {"type": "string"},
                "contenu": {"type": "string"},
                "auteur": {"type": "string"},
                "statut": {"type": "string"},
            },
            "required": ["titre"], "additionalProperties": False,
        },
    },
    {
        "name": "create_product",
        "description": "Créer un produit dans la table 'produits'. Champs: nom (requis), prix, description, statut.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "nom": {"type": "string"},
                "prix": {"type": "number"},
                "description": {"type": "string"},
                "statut": {"type": "string"},
            },
            "required": ["nom"], "additionalProperties": False,
        },
    },
    {
        "name": "create_project",
        "description": "Créer un projet dans la table 'projets'. Champs: nom (requis), description, statut, date_debut.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "nom": {"type": "string"},
                "description": {"type": "string"},
                "statut": {"type": "string"},
                "date_debut": {"type": "string"},
            },
            "required": ["nom"], "additionalProperties": False,
        },
    },
    {
        "name": "create_task",
        "description": "Créer une tâche dans la table 'taches'. Champs: titre (requis), description, statut, priorite, projet_id.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "titre": {"type": "string"},
                "description": {"type": "string"},
                "statut": {"type": "string"},
                "priorite": {"type": "string"},
                "projet_id": {"type": "integer"},
            },
            "required": ["titre"], "additionalProperties": False,
        },
    },
    {
        "name": "update_product",
        "description": "Mettre à jour un produit dans la table 'produits'. id (requis), nom, prix, description, statut.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "integer"},
                "nom": {"type": "string"},
                "prix": {"type": "number"},
                "description": {"type": "string"},
                "statut": {"type": "string"},
            },
            "required": ["id"], "additionalProperties": False,
        },
    },
    {
        "name": "search_documents",
        "description": "Rechercher des documents dans la table 'documents'. q (requis), limit (option).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "q": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 1000},
            },
            "required": ["q"], "additionalProperties": False,
        },
    },
]

TOOLS_BY_NAME = {t["name"]: t for t in TOOLS}

TOOL_SCOPES = {
    'list_tables': SCOPE_DATA_READ, 'get_table_schema': SCOPE_DATA_READ,
    'select': SCOPE_DATA_READ, 'search': SCOPE_DATA_READ,
    'create_table': SCOPE_TABLES, 'add_column': SCOPE_TABLES,
    'insert': SCOPE_DATA_WRITE, 'update': SCOPE_DATA_WRITE, 'delete': SCOPE_DATA_WRITE,
    'list_skills': SCOPE_SKILLS, 'run_skill': SCOPE_SKILLS, 'get_task': SCOPE_SKILLS,
    # Outils métier - tous nécessitent data:write sauf search_documents (data:read)
    'create_document': SCOPE_DATA_WRITE, 'create_product': SCOPE_DATA_WRITE,
    'create_project': SCOPE_DATA_WRITE, 'create_task': SCOPE_DATA_WRITE,
    'update_product': SCOPE_DATA_WRITE, 'search_documents': SCOPE_DATA_READ,
}


# --- Exécution des outils ---------------------------------------------------

def _needs_table(name, args, client):
    table = args.get('table_name')
    if table and not client.can_access_table(table):
        raise PermissionError(f'Table non autorisée: {table}')


def _get_active_orchestrator():
    """Récupère le skill orchestrateur actif."""
    try:
        return Skill.objects.filter(is_orchestrator=True, is_active=True).first()
    except Exception:
        return None


def _find_competent_skill(action, table=None):
    """Recherche un skill de compétence compatible avec l'action demandée."""
    try:
        # Recherche basique : compétences dont la catégorie ou le nom correspond à l'action/table
        skills = Skill.objects.filter(is_active=True, is_orchestrator=False)
        for skill in skills:
            # Vérification simple : si la catégorie contient le mot-clé de l'action
            if action.lower() in skill.category.lower() or action.lower() in skill.name.lower():
                return skill
            # Si une table est spécifiée, vérifier si le skill mentionne cette table
            if table and table.lower() in skill.description.lower():
                return skill
    except Exception:
        pass
    return None


def _run_tool(name, args, client):
    _needs_table(name, args, client)

    # Vérifier l'orchestrateur pour les outils sensibles (accès DB)
    sensitive_tools = ['list_tables', 'get_table_schema', 'select', 'search', 
                      'create_table', 'add_column', 'insert', 'update', 'delete']
    if name in sensitive_tools:
        orchestrator = _get_active_orchestrator()
        if not orchestrator:
            raise PermissionError(
                "Aucun skill orchestrateur actif. Les agents doivent passer par l'orchestrateur "
                "pour accéder au système. Importez et activez un orchestrateur depuis l'administration."
            )
        
        # Log de délégation (simplifié pour l'instant)
        # Dans une version complète, l'orchestrateur analyserait la demande et déléguerait
        # Pour l'instant, on autorise l'accès si l'orchestrateur est actif

    if name == "list_tables":
        return {"tables": DatabaseOperations.list_tables()}
    if name == "get_table_schema":
        return {"schema": DatabaseOperations.get_table_schema(args["table_name"])}
    if name == "select":
        return {"data": DatabaseOperations.select(args["table_name"], args.get("filters"), args.get("limit"))}
    if name == "search":
        rows = DatabaseOperations.search(args["table_name"], args.get("q", ""), args.get("columns"), args.get("limit"))
        return {"count": len(rows), "data": rows}
    if name == "create_table":
        DatabaseOperations.create_table(args["table_name"], args["columns"])
        return {"message": f"Table {args['table_name']} created"}
    if name == "add_column":
        DatabaseOperations.add_column(args["table_name"], args["column_name"], args["column_type"])
        return {"message": f"Column {args['column_name']} added"}
    if name == "insert":
        record = DatabaseOperations.insert(args["table_name"], args["data"])
        return {
            "success": True,
            "operation": "insert",
            "table": args["table_name"],
            "id": record.get("id"),
            "data": record
        }
    if name == "update":
        updated = DatabaseOperations.update(args["table_name"], args["data"], args["filters"])
        return {
            "success": True,
            "operation": "update",
            "table": args["table_name"],
            "updated_count": updated
        }
    if name == "delete":
        deleted = DatabaseOperations.delete(args["table_name"], args["filters"])
        return {
            "success": True,
            "operation": "delete",
            "table": args["table_name"],
            "deleted_count": deleted
        }
    if name == "list_skills":
        return {"skills": skills_registry.list_skills()}
    if name == "run_skill":
        return _run_skill(args, client)
    if name == "get_task":
        return _get_task(args, client)

    # Outils métier spécifiques
    if name == "create_document":
        table = "documents"
        if not client.can_access_table(table):
            raise PermissionError(f'Table non autorisée: {table}')
        record = DatabaseOperations.insert(table, args)
        return {
            "success": True,
            "operation": "insert",
            "table": table,
            "id": record.get("id"),
            "data": record
        }
    if name == "create_product":
        table = "produits"
        if not client.can_access_table(table):
            raise PermissionError(f'Table non autorisée: {table}')
        record = DatabaseOperations.insert(table, args)
        return {
            "success": True,
            "operation": "insert",
            "table": table,
            "id": record.get("id"),
            "data": record
        }
    if name == "create_project":
        table = "projets"
        if not client.can_access_table(table):
            raise PermissionError(f'Table non autorisée: {table}')
        record = DatabaseOperations.insert(table, args)
        return {
            "success": True,
            "operation": "insert",
            "table": table,
            "id": record.get("id"),
            "data": record
        }
    if name == "create_task":
        table = "taches"
        if not client.can_access_table(table):
            raise PermissionError(f'Table non autorisée: {table}')
        record = DatabaseOperations.insert(table, args)
        return {
            "success": True,
            "operation": "insert",
            "table": table,
            "id": record.get("id"),
            "data": record
        }
    if name == "update_product":
        table = "produits"
        if not client.can_access_table(table):
            raise PermissionError(f'Table non autorisée: {table}')
        product_id = args.pop("id")
        updated = DatabaseOperations.update(table, args, {"id": product_id})
        return {
            "success": True,
            "operation": "update",
            "table": table,
            "updated_count": updated
        }
    if name == "search_documents":
        table = "documents"
        if not client.can_access_table(table):
            raise PermissionError(f'Table non autorisée: {table}')
        rows = DatabaseOperations.search(table, args.get("q", ""), None, args.get("limit"))
        return {"count": len(rows), "data": rows}

    raise KeyError(name)


def _run_skill(args, client):
    skill = skills_registry.get_skill(args["name"])
    if not skill:
        raise KeyError(f"Skill inconnu: {args['name']}")
    params = args.get("params") or {}
    task = SkillTask.objects.create(
        client=client if getattr(client, 'pk', None) else None,
        skill=args["name"], params=params, status='running',
    )
    try:
        task.result = skill['fn'](params, client)
        task.status = 'succeeded'
    except Exception as e:
        task.status = 'failed'
        task.error = str(e)
    task.save()
    return _task_dict(task)


def _get_task(args, client):
    task = SkillTask.objects.get(pk=args["task_id"])
    if not client.has_scope('*') and task.client_id and getattr(client, 'pk', None) and task.client_id != client.pk:
        raise PermissionError("Tâche d'un autre client")
    return _task_dict(task)


def _task_dict(task):
    return {
        'id': str(task.id), 'skill': task.skill, 'status': task.status,
        'params': task.params, 'result': task.result, 'error': task.error,
    }


# --- Cadre JSON-RPC ---------------------------------------------------------

def _result(req_id, result):
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _error(req_id, code, message, error_code=None, field=None):
    """Format d'erreur structuré pour ChatGPT."""
    error_obj = {"code": code, "message": message}
    if error_code:
        error_obj["error_code"] = error_code
    if field:
        error_obj["field"] = field
    return {"jsonrpc": "2.0", "id": req_id, "error": error_obj}


def _handle_message(msg, client, request):
    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
        return _error(None, -32600, "Invalid Request")

    method = msg.get("method")
    req_id = msg.get("id")
    params = msg.get("params") or {}

    if req_id is None:
        return None  # notification

    if method == "initialize":
        return _result(req_id, {
            "protocolVersion": params.get("protocolVersion") or DEFAULT_PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": SERVER_INFO,
        })
    if method == "ping":
        return _result(req_id, {})
    if method == "tools/list":
        return _result(req_id, {"tools": TOOLS})
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        if name not in TOOLS_BY_NAME:
            return _error(req_id, -32602, f"Unknown tool: {name}", "UNKNOWN_TOOL")
        # Vérification du scope
        if not client.has_scope(TOOL_SCOPES.get(name)):
            audit(request, f'mcp.{name}', args.get('table_name', ''), 'denied')
            return _result(req_id, {
                "success": False,
                "error": {
                    "code": "PERMISSION_DENIED",
                    "message": f"Scope {TOOL_SCOPES.get(name)} requis",
                    "scope_required": TOOL_SCOPES.get(name)
                },
                "isError": True,
            })
        try:
            value = _run_tool(name, args, client)
            audit(request, f'mcp.{name}', args.get('table_name', args.get('name', '')))
        except ValueError as e:
            audit(request, f'mcp.{name}', args.get('table_name', ''), 'error', {'error': str(e)})
            return _result(req_id, {
                "success": False,
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": str(e)
                },
                "isError": True,
            })
        except PermissionError as e:
            audit(request, f'mcp.{name}', args.get('table_name', ''), 'denied', {'error': str(e)})
            return _result(req_id, {
                "success": False,
                "error": {
                    "code": "PERMISSION_DENIED",
                    "message": str(e)
                },
                "isError": True,
            })
        except Exception as e:
            audit(request, f'mcp.{name}', args.get('table_name', ''), 'error', {'error': str(e)})
            return _result(req_id, {
                "success": False,
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": str(e)
                },
                "isError": True,
            })
        return _result(req_id, {
            "content": [{"type": "text", "text": json.dumps(value, default=str)}],
            "structuredContent": value,
            "isError": False,
        })

    return _error(req_id, -32601, f"Method not found: {method}")


def _bearer(request):
    header = request.META.get("HTTP_AUTHORIZATION", "")
    if not header.startswith("Bearer "):
        return None
    return header[len("Bearer "):].strip()


@csrf_exempt
def mcp_view(request):
    """Endpoint MCP unique (Streamable HTTP, stateless)."""
    if request.method != "POST":
        resp = HttpResponse(status=405)
        resp["Allow"] = "POST"
        return resp

    client = resolve_client(_bearer(request))
    if client is None:
        resp = JsonResponse(_error(None, -32001, "Unauthorized: valid Bearer token required"), status=401)
        resp["WWW-Authenticate"] = "Bearer"
        return resp

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return JsonResponse(_error(None, -32700, "Parse error"), status=400)

    if isinstance(payload, list):
        responses = [r for r in (_handle_message(m, client, request) for m in payload) if r is not None]
        if not responses:
            return HttpResponse(status=202)
        return JsonResponse(responses, safe=False)

    response = _handle_message(payload, client, request)
    if response is None:
        return HttpResponse(status=202)
    return JsonResponse(response)
