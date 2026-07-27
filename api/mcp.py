"""
Serveur MCP HTTP pour DataHub.

Expose les mêmes opérations que l'API REST sous forme d'outils MCP (Model
Context Protocol), sur un unique endpoint HTTP en JSON-RPC 2.0 (transport
« Streamable HTTP », mode sans session / stateless).

Authentification et permissions identiques au REST : token Bearer résolu vers
un AgentClient, scopes vérifiés par outil, opérations journalisées (audit).
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
from .models import SkillTask

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
        "description": "Insérer une ligne. data = {colonne: valeur}. Renvoie l'id.",
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
]

TOOLS_BY_NAME = {t["name"]: t for t in TOOLS}

TOOL_SCOPES = {
    'list_tables': SCOPE_DATA_READ, 'get_table_schema': SCOPE_DATA_READ,
    'select': SCOPE_DATA_READ, 'search': SCOPE_DATA_READ,
    'create_table': SCOPE_TABLES, 'add_column': SCOPE_TABLES,
    'insert': SCOPE_DATA_WRITE, 'update': SCOPE_DATA_WRITE, 'delete': SCOPE_DATA_WRITE,
    'list_skills': SCOPE_SKILLS, 'run_skill': SCOPE_SKILLS, 'get_task': SCOPE_SKILLS,
}


# --- Exécution des outils ---------------------------------------------------

def _needs_table(name, args, client):
    table = args.get('table_name')
    if table and not client.can_access_table(table):
        raise PermissionError(f'Table non autorisée: {table}')


def _run_tool(name, args, client):
    _needs_table(name, args, client)

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
        return {"id": DatabaseOperations.insert(args["table_name"], args["data"])}
    if name == "update":
        return {"updated": DatabaseOperations.update(args["table_name"], args["data"], args["filters"])}
    if name == "delete":
        return {"deleted": DatabaseOperations.delete(args["table_name"], args["filters"])}
    if name == "list_skills":
        return {"skills": skills_registry.list_skills()}
    if name == "run_skill":
        return _run_skill(args, client)
    if name == "get_task":
        return _get_task(args, client)
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


def _error(req_id, code, message):
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


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
            return _error(req_id, -32602, f"Unknown tool: {name}")
        # Vérification du scope
        if not client.has_scope(TOOL_SCOPES.get(name)):
            audit(request, f'mcp.{name}', args.get('table_name', ''), 'denied')
            return _result(req_id, {
                "content": [{"type": "text", "text": f"Permission refusée : scope {TOOL_SCOPES.get(name)} requis"}],
                "isError": True,
            })
        try:
            value = _run_tool(name, args, client)
            audit(request, f'mcp.{name}', args.get('table_name', args.get('name', '')))
        except Exception as e:
            audit(request, f'mcp.{name}', args.get('table_name', ''), 'error', {'error': str(e)})
            return _result(req_id, {
                "content": [{"type": "text", "text": f"Error: {e}"}],
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
