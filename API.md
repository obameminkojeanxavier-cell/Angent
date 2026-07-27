# API.md — Référence des API DataHub

Document de référence pour permettre à tout modèle LLM (ChatGPT, Claude), agent
ou skill autorisé de communiquer avec la plateforme.

- **Base URL** : `https://agent.co-ned.com`
- **API REST** : `https://agent.co-ned.com/api/`
- **Serveur MCP** : `https://agent.co-ned.com/mcp`
- **Format** : JSON (`Content-Type: application/json`)

> ⚠️ **Aucun identifiant de base de données ne figure dans ce document.** Les LLM,
> agents et skills n'accèdent **jamais** directement à la base : ils passent
> exclusivement par les API décrites ici. Toute opération est authentifiée,
> soumise à des permissions (scopes) et journalisée (audit).

---

## 1. Authentification

Chaque requête fournit un token personnel dans l'en-tête HTTP :

```
Authorization: Bearer <TOKEN_DE_L_AGENT>
```

Chaque modèle / agent / skill possède **son propre token** avec des permissions
propres. Un token maître d'administration existe aussi (variable `API_TOKEN`).

### Création d'un token d'agent (côté serveur, par un administrateur)

```bash
python manage.py create_agent \
  --name claude-prod \
  --scopes data:read,data:write,skills:trigger \
  --tables ""            # vide = toutes les tables
```

Le token en clair n'est affiché **qu'une seule fois** à la création. Il est
stocké hashé (SHA-256) en base — impossible à récupérer ensuite.

Autres commandes : `python manage.py list_agents`, `python manage.py revoke_agent --name <nom> [--delete]`.

### Où sont stockés les secrets

Aucune valeur secrète n'est écrite dans ce fichier. Les secrets vivent dans les
**variables d'environnement du serveur** (fichier `.env`, non versionné) :

| Variable | Rôle |
|---|---|
| `SECRET_KEY` | Clé secrète Django |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | Connexion PostgreSQL (jamais exposée aux agents) |
| `API_TOKEN` | Token maître (administration) |
| `REQUIRE_AUTH_FOR_READ` | `True`/`False` : exiger un token en lecture |

Les tokens des agents sont en base (hashés), pas dans `.env`.

---

## 2. Permissions (scopes)

| Scope | Autorise |
|---|---|
| `data:read` | `tables`, `tables/schema`, `data/select`, `data/search` |
| `data:write` | `data/insert`, `data/update`, `data/delete` |
| `tables:manage` | `tables/create`, `tables/add-column` |
| `skills:trigger` | `skills`, `skills/{name}/run`, `tasks/...` |
| `audit:read` | `audit` |
| `*` | tous (token maître) |

Un agent peut aussi être restreint à une **liste de tables** (`--tables`). Toute
opération sur une table hors liste renvoie `403`.

---

## 3. Endpoints REST

Résumé :

| Méthode | Chemin | Scope | Rôle |
|---|---|---|---|
| GET | `/api/tables/` | data:read¹ | Lister les tables |
| GET | `/api/tables/schema/` | data:read¹ | Schéma d'une table |
| GET | `/api/data/select/` | data:read¹ | Lire des lignes (filtres égalité) |
| GET | `/api/data/search/` | data:read¹ | Recherche texte (ILIKE) |
| POST | `/api/tables/create/` | tables:manage | Créer une table |
| POST | `/api/tables/add-column/` | tables:manage | Ajouter une colonne |
| POST | `/api/data/insert/` | data:write | Insérer une ligne |
| PUT | `/api/data/update/` | data:write | Mettre à jour |
| DELETE | `/api/data/delete/` | data:write | Supprimer |
| GET | `/api/skills/` | skills:trigger | Lister les skills |
| POST | `/api/skills/{name}/run/` | skills:trigger | Déclencher un skill |
| GET | `/api/tasks/{id}/` | skills:trigger | Suivre l'état/résultat d'une tâche |
| POST | `/api/tasks/{id}/result/` | skills:trigger | Renvoyer un résultat (agent async) |
| GET | `/api/audit/` | audit:read | Journal des opérations |

¹ En lecture, si `REQUIRE_AUTH_FOR_READ=False` (défaut) le token est facultatif ;
s'il est fourni, le scope `data:read` et les tables autorisées sont vérifiés.

### 3.1 Lister les tables — `GET /api/tables/`
Réponse : `{"tables": ["utilisateurs", ...]}`

### 3.2 Schéma — `GET /api/tables/schema/?table_name=NOM`
Réponse : `{"schema": [{"name":"nom","type":"character varying","nullable":true}, ...]}`

### 3.3 Lire — `GET /api/data/select/`
Paramètres (query) : `table_name` (requis), `limit` (option, défaut 100, max 1000),
et tout `colonne=valeur` comme filtre d'égalité.
```
GET /api/data/select/?table_name=utilisateurs&limit=10&age=30
```
Réponse : `{"data": [ {...}, ... ]}`

### 3.4 Rechercher — `GET /api/data/search/`
Paramètres : `table_name` (requis), `q` (requis, sous-chaîne recherchée),
`columns` (option, csv ; défaut = colonnes texte), `limit` (option).
```
GET /api/data/search/?table_name=utilisateurs&q=dupont&columns=nom,email
```
Réponse : `{"count": 2, "data": [ ... ]}`

### 3.5 Créer une table — `POST /api/tables/create/`
```json
{ "table_name": "utilisateurs",
  "columns": { "nom": "varchar(100)", "email": "varchar(255)", "age": "integer" } }
```
`id` (clé primaire) et `created_at` sont ajoutés automatiquement.
Réponse `201` : `{"message": "Table utilisateurs created successfully"}`

Types SQL acceptés : `integer, bigint, smallint, varchar(n), text, char, boolean,
decimal, numeric, real, double precision, date, time, timestamp, json, jsonb, uuid`.

### 3.6 Ajouter une colonne — `POST /api/tables/add-column/`
```json
{ "table_name": "utilisateurs", "column_name": "telephone", "column_type": "varchar(20)" }
```

### 3.7 Insérer — `POST /api/data/insert/`
```json
{ "table_name": "utilisateurs", "data": { "nom": "Jean Dupont", "email": "jean@ex.com", "age": 30 } }
```
Réponse `201` : `{"message": "Data inserted successfully", "id": 1}`

### 3.8 Mettre à jour — `PUT /api/data/update/`
```json
{ "table_name": "utilisateurs", "data": { "age": 31 }, "filters": { "email": "jean@ex.com" } }
```
`filters` est **obligatoire** (sécurité). Réponse : `{"message": "1 row(s) updated"}`

### 3.9 Supprimer — `DELETE /api/data/delete/`
```json
{ "table_name": "utilisateurs", "filters": { "email": "jean@ex.com" } }
```
`filters` obligatoire. Réponse : `{"message": "1 row(s) deleted"}`

### 3.10 Lister les skills — `GET /api/skills/`
Réponse : `{"skills": [{"name":"ping","description":"...","scope":"skills:trigger"}, ...]}`

Skills fournis par défaut : `ping`, `db.stats`, `db.search`.

### 3.11 Déclencher un skill — `POST /api/skills/{name}/run/`
```json
{ "params": { "table_name": "utilisateurs", "q": "dupont" } }
```
Exécution **synchrone** ; une tâche est créée et renvoyée :
```json
{ "id": "3f2c...", "skill": "db.search", "status": "succeeded",
  "params": {...}, "result": {...}, "error": "",
  "created_at": "...", "updated_at": "..." }
```
`status` ∈ `pending | running | succeeded | failed`.

### 3.12 Suivre une tâche — `GET /api/tasks/{id}/`
Renvoie le même objet tâche (état + résultat). Un client ne voit que ses propres
tâches (le master voit tout).

### 3.13 Renvoyer un résultat — `POST /api/tasks/{id}/result/`
Pour un agent qui traite une tâche en arrière-plan et renvoie son résultat :
```json
{ "status": "succeeded", "result": { "...": "..." } }
```

### 3.14 Audit — `GET /api/audit/?limit=100`
Réponse : `{"count": n, "audit": [{"client":"claude-prod","action":"insert","target":"utilisateurs","status":"success","ip":"...","created_at":"..."}, ...]}`

---

## 4. Serveur MCP — `POST /mcp`

Transport HTTP Streamable (JSON-RPC 2.0). Même authentification (`Authorization:
Bearer <TOKEN>`) et mêmes scopes que le REST. Idéal pour brancher un client MCP
(Claude, etc.) directement.

Outils exposés : `list_tables, get_table_schema, select, search, create_table,
add_column, insert, update, delete, list_skills, run_skill, get_task`.

Exemples de messages :
```json
{ "jsonrpc": "2.0", "id": 1, "method": "tools/list" }
```
```json
{ "jsonrpc": "2.0", "id": 2, "method": "tools/call",
  "params": { "name": "insert",
    "arguments": { "table_name": "utilisateurs", "data": { "nom": "Jean" } } } }
```

---

## 5. Format des réponses & erreurs

Succès : objet JSON propre à l'endpoint (voir ci-dessus).

Erreur : `{ "error": "message détaillé" }` avec un code HTTP :

| Code | Signification |
|---|---|
| 200 | OK |
| 201 | Ressource créée (insert, create_table) |
| 400 | Validation (nom d'identifiant/type invalide, filtre manquant, JSON malformé) |
| 401 | Token manquant ou invalide |
| 403 | Scope insuffisant ou table non autorisée |
| 404 | Skill ou tâche introuvable |
| 500 | Erreur serveur |

Côté MCP, les erreurs métier sont renvoyées dans le résultat avec `"isError": true`.

Règles de validation : identifiants `^[a-zA-Z_][a-zA-Z0-9_]*$` (≤ 63 car.) ; types
SQL en liste blanche ; `update`/`delete` exigent un `filters` non vide ; requêtes
toujours paramétrées (aucun SQL brut n'est accepté).

---

## 6. Exemples d'utilisation

### 6.1 cURL
```bash
# Lecture
curl -H "Authorization: Bearer $TOKEN" \
  "https://agent.co-ned.com/api/data/select/?table_name=utilisateurs&limit=5"

# Écriture
curl -X POST https://agent.co-ned.com/api/data/insert/ \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"table_name":"utilisateurs","data":{"nom":"Jean","email":"jean@ex.com"}}'
```

### 6.2 Python (ChatGPT / agent de skill)
```python
import requests

BASE = "https://agent.co-ned.com/api"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}   # TOKEN depuis l'environnement

# Rechercher
r = requests.get(f"{BASE}/data/search/",
                 headers=HEADERS,
                 params={"table_name": "utilisateurs", "q": "dupont"})
print(r.json())

# Déclencher un skill puis suivre la tâche
run = requests.post(f"{BASE}/skills/db.stats/run/", headers=HEADERS, json={"params": {}}).json()
task = requests.get(f"{BASE}/tasks/{run['id']}/", headers=HEADERS).json()
print(task["status"], task["result"])
```

### 6.3 Claude via MCP
Configurer un serveur MCP HTTP pointant sur `https://agent.co-ned.com/mcp` avec
l'en-tête `Authorization: Bearer <TOKEN>`. Claude découvre les outils via
`tools/list` puis les appelle (`insert`, `select`, `run_skill`, …).

> Si Cloudflare Access protège le site, ajouter aussi les en-têtes du service
> token : `CF-Access-Client-Id` et `CF-Access-Client-Secret` (voir
> CLOUDFLARE_TUNNEL.md).

---

## 7. Intégration ChatGPT avec DataHub

### 7.1 Objectif

Permettre à ChatGPT de créer, lire, rechercher, modifier et supprimer des données dans la base de données DataHub depuis une conversation.

ChatGPT ne doit jamais accéder directement à PostgreSQL. Toutes les opérations doivent obligatoirement passer par le serveur MCP ou les API REST sécurisées de DataHub.

### 7.2 Configuration du serveur MCP

Le serveur MCP est publiquement accessible à l'adresse suivante :

```
https://agent.co-ned.com/mcp
```

Il accepte des requêtes HTTP POST au format JSON-RPC 2.0.

### 7.3 Création de l'agent ChatGPT

Créer un agent réservé à ChatGPT avec un token distinct :

```bash
python manage.py create_agent \
  --name chatgpt-agent \
  --scopes data:read,data:write,skills:trigger \
  --tables documents,produits,projets,taches
```

Le token généré doit être :
- **Jamais** enregistré dans le code frontend
- **Jamais** stocké dans le fichier API.md
- **Jamais** dans GitHub ou une page HTML publique
- Conservé dans les secrets du serveur ou la configuration sécurisée du connecteur MCP

### 7.4 Outils MCP disponibles

Le serveur MCP expose les outils suivants :

#### Outils génériques
- `list_tables` - Lister toutes les tables
- `get_table_schema` - Schéma d'une table
- `select` - Lire des lignes
- `search` - Recherche texte (ILIKE)
- `create_table` - Créer une table
- `add_column` - Ajouter une colonne
- `insert` - Insérer une ligne (retourne l'enregistrement complet)
- `update` - Mettre à jour
- `delete` - Supprimer
- `list_skills` - Lister les skills
- `run_skill` - Déclencher un skill
- `get_task` - État d'une tâche

#### Outils métier spécifiques
- `create_document` - Créer un document (table `documents`)
- `create_product` - Créer un produit (table `produits`)
- `create_project` - Créer un projet (table `projets`)
- `create_task` - Créer une tâche (table `taches`)
- `update_product` - Mettre à jour un produit
- `search_documents` - Rechercher des documents

### 7.5 Format des réponses

Après une création, l'outil retourne l'enregistrement complet :

```json
{
  "success": true,
  "operation": "insert",
  "table": "produits",
  "id": 25,
  "data": {
    "id": 25,
    "nom": "Ordinateur HP",
    "prix": 350000,
    "statut": "actif",
    "created_at": "2026-07-27T11:45:00+01:00"
  }
}
```

### 7.6 Format des erreurs

Les erreurs sont structurées :

```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Le champ nom est obligatoire.",
    "field": "nom"
  }
}
```

Codes d'erreur possibles :
- `UNAUTHORIZED` - Token absent ou invalide
- `PERMISSION_DENIED` - Scope insuffisant ou table interdite
- `VALIDATION_ERROR` - Champ obligatoire absent ou type invalide
- `UNKNOWN_TOOL` - Outil MCP inconnu
- `RATE_LIMIT_EXCEEDED` - Trop de requêtes
- `INTERNAL_ERROR` - Erreur serveur

### 7.7 Sécurité

Règles appliquées :
- Aucun accès direct à PostgreSQL depuis ChatGPT
- Aucun SQL brut accepté
- Requêtes SQL toujours paramétrées
- Filtres obligatoires pour les mises à jour
- Filtres obligatoires pour les suppressions
- Limitation du nombre de lignes retournées (max 1000)
- Limitation du nombre de requêtes par minute (60 par défaut)
- Audit de toutes les opérations

### 7.8 Rate Limiting

Le serveur applique une limitation de débit :
- **Par défaut** : 60 requêtes/minute, 1000/heure
- **Configurable** via les variables d'environnement `RATE_LIMIT_PER_MINUTE` et `RATE_LIMIT_PER_HOUR`
- **Par IP et par client** : combiné pour un suivi précis
- **Réponse** : HTTP 429 avec erreur structurée

### 7.9 Audit

Chaque action enregistre :
- Le nom de l'agent
- L'outil appelé
- La table concernée
- L'identifiant de l'enregistrement
- Le statut
- L'adresse IP
- La date et l'heure
- Le code d'erreur (en cas d'échec)

### 7.10 Cloudflare Access

Si Cloudflare Access protège le serveur, créer un Service Token dédié au connecteur MCP.

Le connecteur doit pouvoir transmettre :
- `Authorization: Bearer TOKEN_DATAHUB`
- `CF-Access-Client-Id`
- `CF-Access-Client-Secret`

L'endpoint MCP ne doit jamais retourner une page HTML de connexion Cloudflare. Il doit toujours retourner une réponse JSON-RPC exploitable.

### 7.11 Exemple de flux de conversation

Une fois connecté, l'utilisateur peut écrire :

**Utilisateur** : "Crée un produit nommé Ordinateur HP au prix de 350 000."

**ChatGPT** :
1. Identifie l'outil `create_product`
2. Envoie les données au serveur MCP
3. Le serveur enregistre dans PostgreSQL
4. Reçoit la réponse de l'API
5. Affiche dans la conversation :
   ```
   Produit créé avec succès.
   Identifiant : 25
   Nom : Ordinateur HP
   Prix : 350000
   Table : produits
   Statut de l'opération : success
   ```

### 7.12 Intégration avec d'autres LLM (Claude, etc.)

Pour connecter d'autres LLM via MCP :

1. Configurer le client MCP avec l'URL `https://agent.co-ned.com/mcp`
2. Ajouter l'en-tête `Authorization: Bearer <TOKEN>`
3. Le client découvrira automatiquement les outils disponibles
4. Utiliser les mêmes outils que pour ChatGPT

Pour l'intégration via API REST classique, voir les exemples dans la section 6.

---

## 8. Ajouter un nouveau skill (côté serveur)

Dans `api/skills.py` :
```python
@register('mon.skill', 'Description du skill.')
def _mon_skill(params, client):
    # params: dict fourni par l'appelant ; client: l'AgentClient authentifié
    return {"ok": True}
```
Il devient immédiatement disponible via `/api/skills/mon.skill/run/` et l'outil
MCP `run_skill`.

---

## 9. Connecter ChatGPT via une « Action » (GPT personnalisé)

ChatGPT peut appeler cette API **tout seul** dans une conversation, sans copier-coller,
en tant qu'« Action » d'un **GPT personnalisé**. Un schéma OpenAPI est fourni :

```
GET https://agent.co-ned.com/openapi.json
```

### Étapes (côté ChatGPT — compte Plus/Team)
1. ChatGPT → **Explorer les GPT** → **+ Créer** → onglet **Configurer**.
2. Section **Actions** → **Créer une nouvelle action**.
3. **Schéma** : coller l'URL `https://agent.co-ned.com/openapi.json`
   (ou coller le contenu JSON renvoyé par cette URL).
4. **Authentification** → type **Clé API** :
   - Type d'authentification : **API Key**
   - **Auth Type** : *Bearer*
   - **Clé API** : le token de l'agent ChatGPT (voir ci-dessous).
5. Enregistrer. ChatGPT liste alors les opérations (`insertData`, `selectData`,
   `searchData`, `createTable`, `updateData`, `deleteData`, `runSkill`, …).

### Token dédié à ChatGPT (côté serveur)
```bash
python manage.py create_agent \
  --name chatgpt \
  --scopes data:read,data:write,skills:trigger \
  --tables ""          # ou "produits,documents,projets" pour restreindre
```
Copier le token affiché (une seule fois) et le mettre dans le champ **Clé API**
de l'Action. Ne jamais l'écrire dans le schéma ni dans une instruction publique.

### Exemple d'usage dans la conversation
> « Crée dans la table `produits` un produit nommé *Ordinateur HP* à 350000. »

ChatGPT appellera `insertData` avec
`{"table_name":"produits","data":{"nom":"Ordinateur HP","prix":350000}}`
et affichera l'enregistrement créé (id inclus).

> Prérequis : la table doit exister (sinon demander à ChatGPT d'appeler
> `createTable` d'abord, ce qui exige le scope `tables:manage`).
