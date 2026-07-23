# Informations pour l'agent distant - DataHub

## Accès

Après déploiement, l'agent recevra les informations suivantes:

```
API_URL   = https://agent.co-ned.com/api    (REST)
MCP_URL   = https://agent.co-ned.com/mcp    (Model Context Protocol, JSON-RPC)
API_TOKEN = <généré lors du déploiement>
```

Deux façons d'interagir, au choix :
- **REST** (curl / requests) — voir les endpoints ci-dessous ;
- **MCP** — connecter un client MCP à `MCP_URL` (transport HTTP) avec l'en-tête
  `Authorization: Bearer <API_TOKEN>`. Outils exposés : `list_tables`,
  `get_table_schema`, `create_table`, `add_column`, `insert`, `select`,
  `update`, `delete` (mêmes paramètres que les endpoints REST correspondants).

> Si Cloudflare Access est activé (voir CLOUDFLARE_TUNNEL.md), ajouter aussi les
> en-têtes `CF-Access-Client-Id` / `CF-Access-Client-Secret` du service token.

## Opérations disponibles (REST)

### 1. Lister les tables
```http
GET /api/tables/
Authorization: Bearer <API_TOKEN>
```

### 2. Créer une table
```http
POST /api/tables/create/
Authorization: Bearer <API_TOKEN>
Content-Type: application/json

{
  "table_name": "nom_table",
  "columns": {
    "colonne1": "varchar(100)",
    "colonne2": "integer",
    "colonne3": "boolean"
  }
}
```

### 3. Ajouter une colonne
```http
POST /api/tables/add-column/
Authorization: Bearer <API_TOKEN>
Content-Type: application/json

{
  "table_name": "nom_table",
  "column_name": "nouvelle_colonne",
  "column_type": "varchar(255)"
}
```

### 4. Insérer des données
```http
POST /api/data/insert/
Authorization: Bearer <API_TOKEN>
Content-Type: application/json

{
  "table_name": "nom_table",
  "data": {
    "colonne1": "valeur1",
    "colonne2": 123,
    "colonne3": true
  }
}
```

### 5. Lire des données
```http
GET /api/data/select/?table_name=nom_table&limit=100&colonne1=valeur1
Authorization: Bearer <API_TOKEN>
```

### 6. Mettre à jour des données
```http
PUT /api/data/update/
Authorization: Bearer <API_TOKEN>
Content-Type: application/json

{
  "table_name": "nom_table",
  "data": {
    "colonne1": "nouvelle_valeur"
  },
  "filters": {
    "colonne2": 123
  }
}
```

### 7. Supprimer des données
```http
DELETE /api/data/delete/
Authorization: Bearer <API_TOKEN>
Content-Type: application/json

{
  "table_name": "nom_table",
  "filters": {
    "colonne1": "valeur"
  }
}
```

### 8. Obtenir le schéma d'une table
```http
GET /api/tables/schema/?table_name=nom_table
Authorization: Bearer <API_TOKEN>
```

## Types SQL supportés

- `integer`, `bigint`, `smallint`
- `varchar(n)`, `text`, `char`
- `boolean`
- `decimal`, `numeric`, `real`, `double precision`
- `date`, `time`, `timestamp`
- `json`, `jsonb`
- `uuid`

## Règles de validation

- **Noms de tables/colonnes**: Seuls les caractères alphanumériques et underscore sont autorisés (ex: `ma_table`, `colonne_1`)
- **Longueur maximale**: 63 caractères pour les identifiants
- **Types SQL**: Seuls les types listés ci-dessus sont acceptés
- **Filtres obligatoires**: Les opérations UPDATE et DELETE nécessitent au moins un filtre

## Exemple de workflow complet

```python
import requests

BASE_URL = "https://agent.co-ned.com/api"
TOKEN = "votre_token_ici"
headers = {"Authorization": f"Bearer {TOKEN}"}

# 1. Créer une table
response = requests.post(
    f"{BASE_URL}/tables/create/",
    headers=headers,
    json={
        "table_name": "utilisateurs",
        "columns": {
            "nom": "varchar(100)",
            "email": "varchar(255)",
            "age": "integer"
        }
    }
)

# 2. Insérer des données
response = requests.post(
    f"{BASE_URL}/data/insert/",
    headers=headers,
    json={
        "table_name": "utilisateurs",
        "data": {
            "nom": "Jean Dupont",
            "email": "jean@example.com",
            "age": 30
        }
    }
)

# 3. Lire les données
response = requests.get(
    f"{BASE_URL}/data/select/",
    headers=headers,
    params={"table_name": "utilisateurs", "limit": 10}
)
data = response.json()

# 4. Mettre à jour
response = requests.put(
    f"{BASE_URL}/data/update/",
    headers=headers,
    json={
        "table_name": "utilisateurs",
        "data": {"age": 31},
        "filters": {"email": "jean@example.com"}
    }
)

# 5. Supprimer
response = requests.delete(
    f"{BASE_URL}/data/delete/",
    headers=headers,
    json={
        "table_name": "utilisateurs",
        "filters": {"email": "jean@example.com"}
    }
)
```

## Gestion des erreurs

L'API renvoie des codes HTTP standards:
- `200 OK`: Opération réussie
- `201 Created`: Ressource créée (insert, create_table)
- `400 Bad Request`: Erreur de validation (nom invalide, type non supporté)
- `401 Unauthorized`: Token manquant ou invalide
- `500 Internal Server Error`: Erreur serveur

Format de réponse d'erreur:
```json
{
  "error": "message d'erreur détaillé"
}
```

## Interface web de consultation

Une interface web est disponible à: `https://agent.co-ned.com/`

Elle permet de visualiser les tables, leur schéma et leurs données sans nécessiter le token API.
