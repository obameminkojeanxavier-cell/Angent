# DataHub - Base de données PostgreSQL avec API sécurisée

Projet Django permettant la gestion d'une base PostgreSQL via une API REST sécurisée avec authentification par token.

> 📘 **La référence complète des API pour les LLM/agents/skills est dans [API.md](API.md).**
> Elle décrit chaque endpoint (rôle, méthode, paramètres, auth, scopes, erreurs,
> exemples ChatGPT/Claude/MCP). Le présent README couvre l'installation et le déploiement.

Fonctionnalités clés : identifiants par agent (ChatGPT, Claude, skills), permissions
granulaires (scopes), restriction par table, journal d'audit de toutes les
opérations, déclenchement de skills avec suivi de tâches, API REST **et** serveur MCP.

## Architecture

- **Backend**: Django 5.0 + Django REST Framework
- **Interfaces agent**: API REST (`/api/`) **et** serveur MCP HTTP (`/mcp`), mêmes opérations
- **Base de données**: PostgreSQL (user dédié isolé)
- **Serveur web**: Gunicorn + Apache
- **Tunnel**: Cloudflare Tunnel (débain13_12 → agent.co-ned.com)
- **Sécurité**: Token API, validation SQL, pas d'exécution SQL brute, option Cloudflare Access

## Fonctionnalités API

L'agent distant peut effectuer les opérations suivantes via l'API.

**Écriture — token obligatoire** (`Authorization: Bearer <API_TOKEN>`) :

- `POST /api/tables/create/` - Créer une table
- `POST /api/tables/add-column/` - Ajouter une colonne
- `POST /api/data/insert/` - Insérer des données
- `PUT /api/data/update/` - Mettre à jour des données
- `DELETE /api/data/delete/` - Supprimer des données

**Lecture — publique** (accessible sans token, pour la page de consultation ;
le token reste accepté s'il est fourni) :

- `GET /api/tables/` - Lister les tables
- `GET /api/tables/schema/` - Obtenir le schéma d'une table
- `GET /api/data/select/` - Lire des données (max 1000 lignes/requête)

## Installation

### 1. Prérequis

- Debian 12 (Bookworm)
- Python 3.11+
- PostgreSQL 15+
- Apache 2.4+
- Cloudflare Tunnel (cloudflared)

### 2. Configuration PostgreSQL

```bash
# Se connecter à PostgreSQL
sudo -u postgres psql

# Créer la base de données
CREATE DATABASE datahub;

# Créer l'utilisateur dédié
CREATE USER datahub_user WITH PASSWORD 'votre_mot_de_passe_securise';

# Donner les privilèges
GRANT ALL PRIVILEGES ON DATABASE datahub TO datahub_user;
GRANT ALL ON SCHEMA public TO datahub_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO datahub_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO datahub_user;

\q
```

### 3. Installation du projet

```bash
# Cloner/copier le projet
cd /path/to/BD AGENT

# Créer l'environnement virtuel
python3 -m venv venv
source venv/bin/activate

# Installer les dépendances
pip install -r requirements.txt

# Copier et configurer .env
cp .env.example .env
nano .env
```

### 4. Configuration .env

Générez d'abord les secrets, puis collez les valeurs obtenues dans `.env` :

```bash
# SECRET_KEY
python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'
# API_TOKEN
python -c 'import secrets; print(secrets.token_urlsafe(32))'
```

Contenu de `.env` (remplacez par vos valeurs réelles) :

```env
SECRET_KEY=<coller la valeur générée>
DB_NAME=datahub
DB_USER=datahub_user
DB_PASSWORD=votre_mot_de_passe_securise
DB_HOST=localhost
DB_PORT=5432
API_TOKEN=<coller la valeur générée>
DEBUG=False
ALLOWED_HOSTS=agent.co-ned.com,localhost,127.0.0.1
```

> ⚠️ Si `API_TOKEN` est vide, le serveur **refuse** toute requête authentifiée
> (aucun accès n'est ouvert sans token configuré).

### 5. Initialisation Django

```bash
# Migrations
python manage.py makemigrations
python manage.py migrate

# Collecter les fichiers statiques
python manage.py collectstatic

# Créer un superutilisateur (optionnel, pour l'admin Django)
python manage.py createsuperuser
```

### 6. Configuration Gunicorn

```bash
# Créer les répertoires de logs
sudo mkdir -p /var/log/gunicorn
sudo chown www-data:www-data /var/log/gunicorn

# Modifier le fichier systemd pour le bon chemin
sudo nano systemd/gunicorn.service
# Remplacer /path/to/BD AGENT par le chemin réel
# Remplacer /path/to/venv par le chemin réel du venv

# Installer le service
sudo cp systemd/gunicorn.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable gunicorn
sudo systemctl start gunicorn
```

### 7. Configuration Apache

```bash
# Activer les modules requis
sudo a2enmod ssl
sudo a2enmod proxy
sudo a2enmod proxy_http
sudo a2enmod headers
sudo a2enmod rewrite

# Modifier la configuration Apache
sudo nano apache/datahub.conf
# Remplacer /path/to/BD AGENT par le chemin réel
# Configurer les certificats SSL

# Activer le site
sudo cp apache/datahub.conf /etc/apache2/sites-available/datahub.conf
sudo a2ensite datahub
sudo systemctl reload apache
```

### 8. Configuration Cloudflare Tunnel

```bash
# Installer cloudflared
wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
sudo dpkg -i cloudflared-linux-amd64.deb

# Authentifier
cloudflared tunnel login

# Créer le tunnel (si non existant)
cloudflared tunnel create débain13_12

# Configurer le tunnel
cloudflared tunnel route dns débain13_12 agent.co-ned.com

# Créer la configuration
sudo nano /etc/cloudflared/config.yml
```

Contenu de `/etc/cloudflared/config.yml`:
```yaml
tunnel: <tunnel-id>
credentials-file: /home/<user>/.cloudflared/<tunnel-id>.json

ingress:
  - hostname: agent.co-ned.com
    service: http://localhost:80
  - service: http_status:404
```

```bash
# Installer le service
sudo cloudflared service install
sudo systemctl start cloudflared
sudo systemctl enable cloudflared
```

## Utilisation de l'API

### Authentification

Toutes les requêtes API doivent inclure le header:
```
Authorization: Bearer <API_TOKEN>
```

### Exemples de requêtes

#### Lister les tables
```bash
curl -H "Authorization: Bearer <API_TOKEN>" https://agent.co-ned.com/api/tables/
```

#### Créer une table
```bash
curl -X POST https://agent.co-ned.com/api/tables/create/ \
  -H "Authorization: Bearer <API_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "table_name": "utilisateurs",
    "columns": {
      "nom": "varchar(100)",
      "email": "varchar(255)",
      "age": "integer"
    }
  }'
```

#### Insérer des données
```bash
curl -X POST https://agent.co-ned.com/api/data/insert/ \
  -H "Authorization: Bearer <API_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "table_name": "utilisateurs",
    "data": {
      "nom": "Jean Dupont",
      "email": "jean@example.com",
      "age": 30
    }
  }'
```

#### Lire des données
```bash
curl -H "Authorization: Bearer <API_TOKEN>" \
  "https://agent.co-ned.com/api/data/select/?table_name=utilisateurs&limit=10"
```

#### Mettre à jour des données
```bash
curl -X PUT https://agent.co-ned.com/api/data/update/ \
  -H "Authorization: Bearer <API_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "table_name": "utilisateurs",
    "data": {
      "age": 31
    },
    "filters": {
      "email": "jean@example.com"
    }
  }'
```

#### Supprimer des données
```bash
curl -X DELETE https://agent.co-ned.com/api/data/delete/ \
  -H "Authorization: Bearer <API_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "table_name": "utilisateurs",
    "filters": {
      "email": "jean@example.com"
    }
  }'
```

## Types SQL supportés

- `integer`, `bigint`, `smallint`
- `varchar(n)`, `text`, `char`
- `boolean`
- `decimal`, `numeric`, `real`, `double precision`
- `date`, `time`, `timestamp`
- `json`, `jsonb`
- `uuid`

## Sécurité

- **Token API**: Requis pour toutes les opérations
- **Validation des identifiants**: Noms de tables/colonnes validés (regex)
- **Types SQL restreints**: Liste blanche de types autorisés
- **Pas de SQL brut**: Toutes les requêtes sont paramétrées
- **User PostgreSQL isolé**: Accès limité à la base `datahub`
- **HTTPS obligatoire**: Redirect HTTP vers HTTPS
- **Headers de sécurité**: X-Frame-Options, X-Content-Type-Options, etc.

## Interface web

L'interface de consultation est disponible à: `https://agent.co-ned.com/`

Elle permet de:
- Lister toutes les tables
- Voir le schéma d'une table
- Consulter les données avec filtres (via l'endpoint `select`, colonne = valeur)

> ℹ️ L'onglet « Requête » n'exécute **pas** de SQL libre : il ne fait qu'un
> `select` filtré par égalité de colonnes. Aucune requête SQL brute n'est
> possible depuis l'interface, conformément au principe de sécurité.

## Maintenance

### Redémarrer Gunicorn
```bash
sudo systemctl restart gunicorn
```

### Voir les logs Gunicorn
```bash
sudo journalctl -u gunicorn -f
# ou
sudo tail -f /var/log/gunicorn/datahub-error.log
```

### Voir les logs Apache
```bash
sudo tail -f /var/log/apache2/datahub_error.log
```

### Mettre à jour le projet
```bash
cd /path/to/BD AGENT
source venv/bin/activate
git pull  # ou copier les nouveaux fichiers
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
sudo systemctl restart gunicorn
```

## Dépannage

### Erreur de connexion PostgreSQL
```bash
# Vérifier que PostgreSQL tourne
sudo systemctl status postgresql

# Vérifier la connexion
psql -h localhost -U datahub_user -d datahub
```

### Erreur 502 Bad Gateway
```bash
# Vérifier Gunicorn
sudo systemctl status gunicorn
sudo journalctl -u gunicorn -n 50
```

### Erreur de certificat SSL
```bash
# Vérifier les certificats
sudo certbot certificates
# ou renouveler
sudo certbot renew
```

## Informations pour l'agent distant

Après déploiement, fournissez à l'agent:

```
API_URL   = https://agent.co-ned.com/api
API_TOKEN = <votre_token_généré>
```

L'agent peut ensuite utiliser les endpoints décrits ci-dessus pour interagir avec la base de données de manière sécurisée.
