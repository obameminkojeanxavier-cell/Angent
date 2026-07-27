"""
Schéma OpenAPI 3.1 de l'API DataHub, servi sur /openapi.json.

Destiné aux « Actions » d'un GPT personnalisé (ChatGPT) : le modèle importe ce
schéma, configure l'authentification Bearer, puis appelle l'API tout seul.

Le schéma décrit UNIQUEMENT les routes réellement exposées par le backend.
"""
from django.conf import settings
from django.http import JsonResponse


def _json_obj(properties=None, required=None):
    schema = {"type": "object", "additionalProperties": True}
    if properties:
        schema["properties"] = properties
    if required:
        schema["required"] = required
    return schema


def _ok(description="Succès"):
    return {
        "200": {
            "description": description,
            "content": {"application/json": {"schema": {"type": "object", "additionalProperties": True}}},
        }
    }


def _created(description="Créé"):
    return {
        "201": {
            "description": description,
            "content": {"application/json": {"schema": {"type": "object", "additionalProperties": True}}},
        }
    }


def _body(schema):
    return {"required": True, "content": {"application/json": {"schema": schema}}}


def build_schema(base_url):
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "DataHub API",
            "description": (
                "API sécurisée pour lire et écrire dans la base DataHub. "
                "Toutes les requêtes exigent un token Bearer. Aucun accès direct "
                "à la base : uniquement ces opérations cadrées."
            ),
            "version": "1.0.0",
        },
        "servers": [{"url": base_url}],
        "security": [{"bearerAuth": []}],
        "components": {
            "securitySchemes": {
                "bearerAuth": {"type": "http", "scheme": "bearer"}
            }
        },
        "paths": {
            "/api/tables/": {
                "get": {
                    "operationId": "listTables",
                    "summary": "Lister toutes les tables de la base.",
                    "responses": _ok("Liste des tables"),
                }
            },
            "/api/tables/schema/": {
                "get": {
                    "operationId": "getTableSchema",
                    "summary": "Obtenir les colonnes et types d'une table.",
                    "parameters": [
                        {"name": "table_name", "in": "query", "required": True,
                         "schema": {"type": "string"}, "description": "Nom de la table."}
                    ],
                    "responses": _ok("Schéma de la table"),
                }
            },
            "/api/data/select/": {
                "get": {
                    "operationId": "selectData",
                    "summary": "Lire des lignes d'une table (les plus récentes).",
                    "parameters": [
                        {"name": "table_name", "in": "query", "required": True,
                         "schema": {"type": "string"}, "description": "Nom de la table."},
                        {"name": "limit", "in": "query", "required": False,
                         "schema": {"type": "integer", "minimum": 1, "maximum": 1000},
                         "description": "Nombre max de lignes (défaut 100, max 1000)."},
                    ],
                    "responses": _ok("Lignes trouvées"),
                }
            },
            "/api/data/search/": {
                "get": {
                    "operationId": "searchData",
                    "summary": "Rechercher un texte dans une table (insensible à la casse).",
                    "parameters": [
                        {"name": "table_name", "in": "query", "required": True,
                         "schema": {"type": "string"}, "description": "Nom de la table."},
                        {"name": "q", "in": "query", "required": True,
                         "schema": {"type": "string"}, "description": "Texte recherché."},
                        {"name": "columns", "in": "query", "required": False,
                         "schema": {"type": "string"},
                         "description": "Colonnes où chercher, séparées par des virgules (défaut : colonnes texte)."},
                        {"name": "limit", "in": "query", "required": False,
                         "schema": {"type": "integer", "minimum": 1, "maximum": 1000},
                         "description": "Nombre max de lignes."},
                    ],
                    "responses": _ok("Résultats de recherche"),
                }
            },
            "/api/tables/create/": {
                "post": {
                    "operationId": "createTable",
                    "summary": "Créer une nouvelle table (id et created_at ajoutés automatiquement).",
                    "requestBody": _body(_json_obj(
                        properties={
                            "table_name": {"type": "string"},
                            "columns": {
                                "type": "object",
                                "additionalProperties": {"type": "string"},
                                "description": "Association nom_colonne -> type SQL (ex: {\"nom\":\"varchar(100)\",\"prix\":\"numeric\"}).",
                            },
                        },
                        required=["table_name", "columns"],
                    )),
                    "responses": _created("Table créée"),
                }
            },
            "/api/tables/add-column/": {
                "post": {
                    "operationId": "addColumn",
                    "summary": "Ajouter une colonne à une table existante.",
                    "requestBody": _body(_json_obj(
                        properties={
                            "table_name": {"type": "string"},
                            "column_name": {"type": "string"},
                            "column_type": {"type": "string"},
                        },
                        required=["table_name", "column_name", "column_type"],
                    )),
                    "responses": _ok("Colonne ajoutée"),
                }
            },
            "/api/data/insert/": {
                "post": {
                    "operationId": "insertData",
                    "summary": "Insérer une ligne. Renvoie l'enregistrement complet créé.",
                    "requestBody": _body(_json_obj(
                        properties={
                            "table_name": {"type": "string"},
                            "data": {"type": "object", "additionalProperties": True,
                                     "description": "Association colonne -> valeur."},
                        },
                        required=["table_name", "data"],
                    )),
                    "responses": _created("Ligne insérée"),
                }
            },
            "/api/data/update/": {
                "put": {
                    "operationId": "updateData",
                    "summary": "Mettre à jour des lignes. 'filters' est obligatoire (sécurité).",
                    "requestBody": _body(_json_obj(
                        properties={
                            "table_name": {"type": "string"},
                            "data": {"type": "object", "additionalProperties": True,
                                     "description": "Nouvelles valeurs."},
                            "filters": {"type": "object", "additionalProperties": True,
                                        "description": "Condition WHERE (égalité), obligatoire."},
                        },
                        required=["table_name", "data", "filters"],
                    )),
                    "responses": _ok("Lignes mises à jour"),
                }
            },
            "/api/data/delete/": {
                "delete": {
                    "operationId": "deleteData",
                    "summary": "Supprimer des lignes. 'filters' est obligatoire (sécurité).",
                    "requestBody": _body(_json_obj(
                        properties={
                            "table_name": {"type": "string"},
                            "filters": {"type": "object", "additionalProperties": True,
                                        "description": "Condition WHERE (égalité), obligatoire."},
                        },
                        required=["table_name", "filters"],
                    )),
                    "responses": _ok("Lignes supprimées"),
                }
            },
            "/api/skills/": {
                "get": {
                    "operationId": "listSkills",
                    "summary": "Lister les skills disponibles.",
                    "responses": _ok("Liste des skills"),
                }
            },
            "/api/skills/{name}/run/": {
                "post": {
                    "operationId": "runSkill",
                    "summary": "Déclencher un skill et récupérer la tâche (résultat inclus).",
                    "parameters": [
                        {"name": "name", "in": "path", "required": True,
                         "schema": {"type": "string"}, "description": "Nom du skill."}
                    ],
                    "requestBody": _body(_json_obj(
                        properties={"params": {"type": "object", "additionalProperties": True}},
                    )),
                    "responses": _ok("Tâche exécutée"),
                }
            },
            "/api/tasks/{id}/": {
                "get": {
                    "operationId": "getTask",
                    "summary": "Suivre l'état et le résultat d'une tâche.",
                    "parameters": [
                        {"name": "id", "in": "path", "required": True,
                         "schema": {"type": "string"}, "description": "Identifiant de la tâche."}
                    ],
                    "responses": _ok("État de la tâche"),
                }
            },
            "/api/audit/": {
                "get": {
                    "operationId": "listAudit",
                    "summary": "Consulter le journal d'audit des opérations.",
                    "parameters": [
                        {"name": "limit", "in": "query", "required": False,
                         "schema": {"type": "integer", "minimum": 1, "maximum": 1000},
                         "description": "Nombre d'entrées (défaut 100)."}
                    ],
                    "responses": _ok("Journal d'audit"),
                }
            },
        },
    }


def openapi_schema(request):
    # Base URL : configurable via OPENAPI_BASE_URL, sinon reconstruite depuis la requête.
    base = getattr(settings, 'OPENAPI_BASE_URL', '') or f"{request.scheme}://{request.get_host()}"
    return JsonResponse(build_schema(base))
