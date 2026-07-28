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
    # Pas de schéma de réponse : évite les warnings ChatGPT « object schema
    # missing properties » (le corps de réponse reste du JSON libre).
    return {"200": {"description": description}}


def _created(description="Créé"):
    return {"201": {"description": description}}


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
            # schemas vide mais présent : évite le warning
            # « components.schemas subsection is not an object ».
            "schemas": {},
            "securitySchemes": {
                "bearerAuth": {"type": "http", "scheme": "bearer"}
            },
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
                                "type": "string",
                                "description": "Objet JSON encodé en CHAÎNE, associant nom_colonne -> type SQL. "
                                               "Exemple exact : {\"nom\":\"varchar(150)\",\"prix\":\"numeric\",\"statut\":\"varchar(30)\"}",
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
                            "data": {"type": "string",
                                     "description": "Objet JSON encodé en CHAÎNE, colonne -> valeur. "
                                                    "Exemple : {\"nom\":\"Clavier sans fil\",\"prix\":15000,\"statut\":\"actif\"}"},
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
                            "data": {"type": "string",
                                     "description": "Objet JSON (chaîne) des nouvelles valeurs. Ex: {\"prix\":18000}"},
                            "filters": {"type": "string",
                                        "description": "Objet JSON (chaîne) condition WHERE (égalité), obligatoire. Ex: {\"id\":25}"},
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
                            "filters": {"type": "string",
                                        "description": "Objet JSON (chaîne) condition WHERE (égalité), obligatoire. Ex: {\"id\":25}"},
                        },
                        required=["table_name", "filters"],
                    )),
                    "responses": _ok("Lignes supprimées"),
                }
            },
            "/api/skills/": {
                "get": {
                    "operationId": "listSkills",
                    "summary": "Lister les skills disponibles (catalogue : nom, description, catégorie).",
                    "responses": _ok("Liste des skills"),
                }
            },
            "/api/skills/{name}/": {
                "get": {
                    "operationId": "getSkillDefinition",
                    "summary": "Lire la définition complète d'un skill (instructions détaillées + exemple) "
                               "afin de comprendre comment l'utiliser.",
                    "parameters": [
                        {"name": "name", "in": "path", "required": True,
                         "schema": {"type": "string"}, "description": "Nom du skill."}
                    ],
                    "responses": _ok("Définition du skill"),
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
                        properties={"params": {"type": "string",
                                               "description": "Objet JSON (chaîne) des paramètres du skill. Ex: {\"table_name\":\"produits\",\"q\":\"clavier\"}"}},
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
            "/api/artifacts/create/": {
                "post": {
                    "operationId": "createArtifact",
                    "summary": "Publier un fichier/contenu produit (HTML, texte, CSV, JSON, Markdown, SVG) "
                               "et obtenir une URL publique à donner à l'utilisateur.",
                    "requestBody": _body(_json_obj(
                        properties={
                            "content": {"type": "string", "description": "Le contenu complet du fichier (ex: le code HTML)."},
                            "name": {"type": "string", "description": "Nom lisible (optionnel)."},
                            "content_type": {"type": "string",
                                             "description": "Type MIME : text/html (défaut), text/plain, text/csv, application/json, text/markdown, image/svg+xml."},
                        },
                        required=["content"],
                    )),
                    "responses": _created("Artefact créé (renvoie slug + url)"),
                }
            },
            "/api/artifacts/": {
                "get": {
                    "operationId": "listArtifacts",
                    "summary": "Lister les artefacts récents (métadonnées + URL).",
                    "parameters": [
                        {"name": "limit", "in": "query", "required": False,
                         "schema": {"type": "integer", "minimum": 1, "maximum": 500}}
                    ],
                    "responses": _ok("Liste des artefacts"),
                }
            },
            "/api/artifacts/{slug}/": {
                "get": {
                    "operationId": "getArtifact",
                    "summary": "Récupérer un artefact (métadonnées + contenu + URL).",
                    "parameters": [
                        {"name": "slug", "in": "path", "required": True,
                         "schema": {"type": "string"}}
                    ],
                    "responses": _ok("Artefact"),
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
