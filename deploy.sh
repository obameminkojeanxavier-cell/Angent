#!/bin/bash

# Déploiement in-place de DataHub.
# À exécuter en root DEPUIS le dossier du projet (ex: /opt/Angent) :
#   cd /opt/Angent && ./deploy.sh
# Le projet reste là où il est cloné ; Gunicorn et Apache pointent dessus.

set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$PROJECT_DIR/venv"
SERVICE_USER="www-data"

echo "=== Déploiement DataHub (in-place: $PROJECT_DIR) ==="

# 0. Vérifier le .env AVANT tout
if [ ! -f "$PROJECT_DIR/.env" ]; then
    echo "❌ $PROJECT_DIR/.env introuvable. Créez-le d'abord (voir README §4). Abandon."
    exit 1
fi

# 1. Répertoires de logs
echo "Préparation des logs..."
mkdir -p /var/log/gunicorn
chown $SERVICE_USER:$SERVICE_USER /var/log/gunicorn

# 2. Environnement virtuel (recréé proprement si absent/cassé)
if [ ! -x "$VENV_DIR/bin/python" ]; then
    echo "Création de l'environnement virtuel..."
    rm -rf "$VENV_DIR"
    python3 -m venv "$VENV_DIR"
fi

echo "Installation des dépendances..."
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install -r "$PROJECT_DIR/requirements.txt"

# 3. Migrations + fichiers statiques (en root, avant le chown)
echo "Migrations Django..."
"$VENV_DIR/bin/python" "$PROJECT_DIR/manage.py" migrate --noinput
echo "Collecte des fichiers statiques..."
"$VENV_DIR/bin/python" "$PROJECT_DIR/manage.py" collectstatic --noinput

# 4. Droits : Gunicorn tourne en www-data, il doit pouvoir lire tout le projet
echo "Application des droits ($SERVICE_USER)..."
chown -R $SERVICE_USER:$SERVICE_USER "$PROJECT_DIR"

# 5. Service Gunicorn (systemd)
echo "Configuration de Gunicorn..."
sed -e "s|/path/to/BD AGENT|$PROJECT_DIR|g" \
    -e "s|/path/to/venv|$VENV_DIR|g" \
    "$PROJECT_DIR/systemd/gunicorn.service" > /etc/systemd/system/gunicorn.service
systemctl daemon-reload
systemctl enable gunicorn
systemctl restart gunicorn

# 6. Apache (vhost HTTP port 80, TLS géré par Cloudflare)
echo "Configuration d'Apache..."
sed -e "s|/path/to/BD AGENT|$PROJECT_DIR|g" \
    "$PROJECT_DIR/apache/datahub.conf" > /etc/apache2/sites-available/datahub.conf
a2enmod proxy proxy_http headers rewrite
a2ensite datahub
# Désactiver le site par défaut pour qu'il ne réponde pas à la place
a2dissite 000-default 2>/dev/null || true
systemctl restart apache2

echo ""
echo "=== Déploiement terminé ==="
echo "Vérifs :"
echo "  systemctl status gunicorn --no-pager"
echo "  curl -I http://127.0.0.1:8000/            # Gunicorn/Django répond"
echo "  curl -H 'Authorization: Bearer <API_TOKEN>' http://127.0.0.1/api/tables/"
echo ""
echo "Tunnel Cloudflare : voir CLOUDFLARE_TUNNEL.md (route dns + service run)."
