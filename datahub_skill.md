# DataHub — Document d'intégration pour skill / agent IA

> **But de ce document.** Fichier unique et autonome à déposer dans une skill
> (Claude, ChatGPT, agent). Il contient **tout** ce qu'il faut pour communiquer
> avec la base de données DataHub **via les API** : consulter, rechercher,
> créer, insérer, modifier, supprimer des données, et déclencher des skills.
>
> L'agent **ne se connecte jamais directement à la base**. Il n'a **ni**
> l'adresse de la base, **ni** l'utilisateur, **ni** le mot de passe. Il utilise
> uniquement l'URL de l'API et un **token** personnel.

---

## 1. Ce que l'agent doit connaître

Deux valeurs, à fournir à l'agent (jamais écrites en dur dans une skill publique) :

| Variable | Description | Exemple |
|---|---|---|
| `DATAHUB_API_URL` | Base des API REST | `https://agent.co-ned.com/api` |
| `DATAHUB_API_TOKEN` | Token personnel de l'agent | *(fourni séparément)* |

En test local : `DATAHUB_API_URL = http://127.0.0.1:8000/api`

Toute requête inclut l'en-tête :
```
Authorization: Bearer <DATAHUB_API_TOKEN>
Content-Type: application/json
```

> Le token définit ce que l'agent a le droit de faire (voir §2). Les
> informations sensibles (adresse base, utilisateur, mot de passe, clés) sont
> stockées côté serveur (variables d'environnement) et **jamais** exposées ici.

---

## 2. Permissions (scopes)

Chaque token porte un ou plusieurs droits. Si le droit manque → réponse `403`.

| Scope | Ce qu'il autorise |
|---|---|
| `data:read` | lister les tables, voir un schéma, lire (`select`), rechercher (`search`) |
| `data:write` | insérer, mettre à jour, supprimer |
| `tables:manage` | créer une table, ajouter une colonne |
| `skills:trigger` | déclencher des skills, suivre les tâches |
| `audit:read` | consulter le journal des opérations |

Un token peut aussi être limité à certaines tables ; toute opération sur une
autre table renvoie `403`.

---

## 3. Comment communiquer avec la base — les opérations

Base des chemins : `{DATAHUB_API_URL}` (ex. `https://agent.co-ned.com/api`).

### 3.1 Lister les tables — `GET /tables/`
Réponse : `{"tables": ["utilisateurs", ...]}`

### 3.2 Voir le schéma d'une table — `GET /tables/schema/?table_name=NOM`
Réponse : `{"schema": [{"name":"nom","type":"character varying","nullable":true}, ...]}`

### 3.3 Lire des données — `GET /data/select/`
Paramètres : `table_name` (requis), `limit` (option, défaut 100, max 1000), et
n'importe quel `colonne=valeur` comme filtre d'égalité.
Exemple : `GET /data/select/?table_name=utilisateurs&limit=10&age=30`
Réponse : `{"data": [ { ... }, ... ]}`

### 3.4 Rechercher — `GET /data/search/`
Paramètres : `table_name` (requis), `q` (requis, texte cherché), `columns`
(option, csv), `limit` (option).
Exemple : `GET /data/search/?table_name=utilisateurs&q=dupont`
Réponse : `{"count": 1, "data": [ ... ]}`

### 3.5 Créer une table — `POST /tables/create/`  *(scope tables:manage)*
```json
{ "table_name": "utilisateurs",
  "columns": { "nom": "varchar(100)", "email": "varchar(255)", "age": "integer" } }
```
`id` (clé primaire) et `created_at` sont ajoutés automatiquement.
Types acceptés : `integer, bigint, smallint, varchar(n), text, char, boolean,
decimal, numeric, real, double precision, date, time, timestamp, json, jsonb, uuid`.

### 3.6 Ajouter une colonne — `POST /tables/add-column/`  *(tables:manage)*
```json
{ "table_name": "utilisateurs", "column_name": "telephone", "column_type": "varchar(20)" }
```

### 3.7 Insérer des données — `POST /data/insert/`  *(data:write)*
```json
{ "table_name": "utilisateurs", "data": { "nom": "Jean Dupont", "email": "jean@ex.com", "age": 30 } }
```
Réponse : `{"message": "Data inserted successfully", "id": 1}`

### 3.8 Mettre à jour — `PUT /data/update/`  *(data:write)*
```json
{ "table_name": "utilisateurs", "data": { "age": 31 }, "filters": { "email": "jean@ex.com" } }
```
`filters` est **obligatoire** (sécurité).

### 3.9 Supprimer — `DELETE /data/delete/`  *(data:write)*
```json
{ "table_name": "utilisateurs", "filters": { "email": "jean@ex.com" } }
```
`filters` obligatoire.

### 3.10 Skills
- `GET /skills/` → liste des skills disponibles *(skills:trigger)*
- `POST /skills/{name}/run/` avec `{"params": { ... }}` → exécute, renvoie une tâche
- `GET /tasks/{id}/` → état + résultat d'une tâche
- `POST /tasks/{id}/result/` → renvoyer un résultat (agent asynchrone)

Skills fournis : `ping`, `db.stats` (nb de lignes par table), `db.search`.

### 3.11 Audit — `GET /audit/?limit=100`  *(audit:read)*
Historique de toutes les opérations (qui, quoi, quand, statut).

---

## 4. Codes de réponse

| Code | Sens |
|---|---|
| 200 / 201 | Succès / créé |
| 400 | Requête invalide (nom/type invalide, `filters` manquant, JSON malformé) |
| 401 | Token manquant ou invalide |
| 403 | Droit (scope) insuffisant, ou table non autorisée |
| 404 | Skill ou tâche introuvable |
| 500 | Erreur serveur |

Erreur : `{ "error": "message" }`.
Règles : noms de tables/colonnes en `[a-zA-Z_][a-zA-Z0-9_]*` (≤ 63 car.) ;
`update`/`delete` exigent un `filters` non vide ; aucune requête SQL brute
n'est acceptée (opérations cadrées uniquement).

---

## 5. Exemples prêts à l'emploi

### cURL
```bash
# Insérer
curl -X POST "$DATAHUB_API_URL/data/insert/" \
  -H "Authorization: Bearer $DATAHUB_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"table_name":"utilisateurs","data":{"nom":"Jean","email":"jean@ex.com","age":30}}'

# Lire
curl -H "Authorization: Bearer $DATAHUB_API_TOKEN" \
  "$DATAHUB_API_URL/data/select/?table_name=utilisateurs&limit=10"
```

### Python
```python
import os, requests

BASE = os.environ["DATAHUB_API_URL"]
H = {"Authorization": f"Bearer {os.environ['DATAHUB_API_TOKEN']}"}

# Créer une table
requests.post(f"{BASE}/tables/create/", headers=H, json={
    "table_name": "utilisateurs",
    "columns": {"nom": "varchar(100)", "email": "varchar(255)", "age": "integer"},
})

# Insérer une ligne
requests.post(f"{BASE}/data/insert/", headers=H, json={
    "table_name": "utilisateurs",
    "data": {"nom": "Jean Dupont", "email": "jean@ex.com", "age": 30},
})

# Rechercher
r = requests.get(f"{BASE}/data/search/", headers=H,
                 params={"table_name": "utilisateurs", "q": "dupont"})
print(r.json())
```

---

## 6. Bloc d'instructions à coller dans la skill

> Copier tel quel dans les instructions de la skill (adapter l'URL si besoin) :

```
Tu peux lire et écrire dans la base DataHub UNIQUEMENT via son API REST.
- Base : {DATAHUB_API_URL}   Auth : en-tête "Authorization: Bearer {DATAHUB_API_TOKEN}".
- Ne demande jamais et n'utilise jamais d'identifiants de base de données directs.
- Pour lire : GET /data/select/?table_name=... (filtres colonne=valeur, limit).
- Pour chercher : GET /data/search/?table_name=...&q=...
- Pour ajouter : POST /data/insert/ {table_name, data:{...}}.
- Pour modifier : PUT /data/update/ {table_name, data:{...}, filters:{...}} (filters obligatoire).
- Pour supprimer : DELETE /data/delete/ {table_name, filters:{...}} (filters obligatoire).
- Pour créer une table : POST /tables/create/ {table_name, columns:{nom:type_sql}}.
- Vérifie toujours le schéma via GET /tables/schema/?table_name=... avant d'insérer.
- Respecte les erreurs : 401=token, 403=droit manquant, 400=données invalides.
```

---

## 7. MCP (optionnel)

Un serveur MCP expose les mêmes opérations comme outils, sur
`{base}/mcp` (ex. `https://agent.co-ned.com/mcp`), avec le même
`Authorization: Bearer <token>`. Outils : `list_tables, get_table_schema,
select, search, create_table, add_column, insert, update, delete, list_skills,
run_skill, get_task`. À utiliser si la skill parle nativement le protocole MCP ;
sinon, utiliser l'API REST ci-dessus.
