"""
Serveur MCP HTTP pour DataHub.

Expose les mêmes opérations que l'API REST sous forme d'outils MCP (Model
Context Protocol), sur un unique endpoint HTTP en JSON-RPC 2.0 (transport
« Streamable HTTP », mode sans session / stateless).

Un agent compatible MCP peut ainsi se connecter directement au lieu de faire
des appels REST à la main. L'accès est protégé par le même token API que
l'écriture REST (Authorization: Bearer <API_TOKEN>).

Aucune dépendance externe : JSON-RPC implémenté à la main pour rester dans le
périmètre Django/Gunicorn/WSGI existant.
"""
import json
import secrets

from django.conf import settings
from django.core.exceptions import ValidationError
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt

from .db_operations import DatabaseOperations

# Version du protocole MCP annoncée par défaut si le client n'en propose pas.
DEFAULT_PROTOCOL_VERSION = "2025-06-18"

SERVER_INFO = {"name": "datahub", "version": "1.0.0"}

# --- Définition des outils exposés -----------------------------------------

TOOLS = [
    {
        "name": "list_tables",
        "description": "Lister toutes les tables de la base datahub.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "get_table_schema",
        "description": "Obtenir le schéma (colonnes et types) d'une table.",
        "inputSchema": {
            "type": "object",
            "properties": {"table_name": {"type": "string"}},
            "required": ["table_name"],
            "additionalProperties": False,
        },
    },
    {
        "name": "create_table",
        "description": (
            "Créer une table. 'columns' associe chaque nom de colonne à un type "
            "SQL autorisé (ex: {\"nom\": \"varchar(100)\", \"age\": \"integer\"}). "
            "Les colonnes id et created_at sont ajoutées automatiquement."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "table_name": {"type": "string"},
                "columns": {"type": "object", "additionalProperties": {"type": "string"}},
            },
            "required": ["table_name", "columns"],
            "additionalProperties": False,
        },
    },
    {
        "name": "add_column",
        "description": "Ajouter une colonne à une table existante.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "table_name": {"type": "string"},
                "column_name": {"type": "string"},
                "column_type": {"type": "string"},
            },
            "required": ["table_name", "column_name", "column_type"],
            "additionalProperties": False,
        },
    },
    {
        "name": "insert",
        "description": "Insérer une ligne. 'data' associe chaque colonne à sa valeur. Renvoie l'id créé.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "table_name": {"type": "string"},
                "data": {"type": "object"},
            },
            "required": ["table_name", "data"],
            "additionalProperties": False,
        },
    },
    {
        "name": "select",
        "description": (
            "Lire des lignes. 'filters' (optionnel) filtre par égalité de colonnes. "
            "'limit' (optionnel, défaut 100, max 1000)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "table_name": {"type": "string"},
                "filters": {"type": "object"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 1000},
            },
            "required": ["table_name"],
            "additionalProperties": False,
        },
    },
    {
        "name": "update",
        "description": (
            "Mettre à jour des lignes. 'data' = nouvelles valeurs, 'filters' = "
            "condition WHERE (obligatoire, par sécurité). Renvoie le nombre de lignes."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "table_name": {"type": "string"},
                "data": {"type": "object"},
                "filters": {"type": "object"},
            },
            "required": ["table_name", "data", "filters"],
            "additionalProperties": False,
        },
    },
    {
        "name": "delete",
        "description": (
            "Supprimer des lignes correspondant à 'filters' (obligatoire, par "
            "sécurité). Renvoie le nombre de lignes supprimées."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "table_name": {"type": "string"},
                "filters": {"type": "object"},
            },
            "required": ["table_name", "filters"],
            "additionalProperties": False,
        },
    },
]

TOOLS_BY_NAME = {t["name"]: t for t in TOOLS}


# --- Exécution des outils ---------------------------------------------------

def _run_tool(name, args):
    """Exécute un outil et renvoie une valeur JSON-sérialisable."""
    if name == "list_tables":
        return {"tables": DatabaseOperations.list_tables()}
    if name == "get_table_schema":
        return {"schema": DatabaseOperations.get_table_schema(args["table_name"])}
    if name == "create_table":
        DatabaseOperations.create_table(args["table_name"], args["columns"])
        return {"message": f"Table {args['table_name']} created"}
    if name == "add_column":
        DatabaseOperations.add_column(
            args["table_name"], args["column_name"], args["column_type"]
        )
        return {"message": f"Column {args['column_name']} added to {args['table_name']}"}
    if name == "insert":
        row_id = DatabaseOperations.insert(args["table_name"], args["data"])
        return {"id": row_id}
    if name == "select":
        rows = DatabaseOperations.select(
            args["table_name"], args.get("filters"), args.get("limit")
        )
        return {"data": rows}
    if name == "update":
        count = DatabaseOperations.update(
            args["table_name"], args["data"], args["filters"]
        )
        return {"updated": count}
    if name == "delete":
        count = DatabaseOperations.delete(args["table_name"], args["filters"])
        return {"deleted": count}
    raise KeyError(name)


# --- Cadre JSON-RPC ---------------------------------------------------------

def _result(req_id, result):
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _error(req_id, code, message):
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def _handle_message(msg):
    """Traite un message JSON-RPC. Renvoie un dict de réponse, ou None pour une notification."""
    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
        return _error(None, -32600, "Invalid Request")

    method = msg.get("method")
    req_id = msg.get("id")
    params = msg.get("params") or {}

    # Notifications (pas d'id) : on ne répond pas.
    if req_id is None:
        return None

    if method == "initialize":
        client_version = params.get("protocolVersion") or DEFAULT_PROTOCOL_VERSION
        return _result(req_id, {
            "protocolVersion": client_version,
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
        try:
            value = _run_tool(name, args)
        except (ValidationError, ValueError, KeyError) as e:
            # Erreur métier : renvoyée comme résultat isError (convention MCP),
            # pas comme erreur de protocole.
            return _result(req_id, {
                "content": [{"type": "text", "text": f"Error: {e}"}],
                "isError": True,
            })
        except Exception as e:  # pragma: no cover - filet de sécurité
            return _result(req_id, {
                "content": [{"type": "text", "text": f"Server error: {e}"}],
                "isError": True,
            })
        return _result(req_id, {
            "content": [{"type": "text", "text": json.dumps(value, default=str)}],
            "structuredContent": value,
            "isError": False,
        })

    return _error(req_id, -32601, f"Method not found: {method}")


def _authorized(request):
    """Vérifie le token Bearer en temps constant (comme l'API REST)."""
    header = request.META.get("HTTP_AUTHORIZATION", "")
    if not header.startswith("Bearer "):
        return False
    token = header[len("Bearer "):].strip()
    expected = settings.API_TOKEN
    if not expected or not token:
        return False
    return secrets.compare_digest(token, expected)


@csrf_exempt
def mcp_view(request):
    """Endpoint MCP unique (Streamable HTTP, stateless)."""
    if request.method != "POST":
        # Pas de flux serveur->client en mode stateless.
        resp = HttpResponse(status=405)
        resp["Allow"] = "POST"
        return resp

    if not _authorized(request):
        resp = JsonResponse(
            _error(None, -32001, "Unauthorized: valid Bearer token required"),
            status=401,
        )
        resp["WWW-Authenticate"] = "Bearer"
        return resp

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return JsonResponse(_error(None, -32700, "Parse error"), status=400)

    # JSON-RPC autorise un objet unique ou un lot (array).
    if isinstance(payload, list):
        responses = [r for r in (_handle_message(m) for m in payload) if r is not None]
        if not responses:
            return HttpResponse(status=202)  # que des notifications
        return JsonResponse(responses, safe=False)

    response = _handle_message(payload)
    if response is None:
        return HttpResponse(status=202)  # notification
    return JsonResponse(response)
