#!/bin/bash

# Script de déploiement pour DataHub
# À exécuter sur le serveur Debian

set -e

echo "=== Déploiement DataHub ==="

# Variables
PROJECT_DIR="/var/www/datahub"
VENV_DIR="$PROJECT_DIR/venv"
SERVICE_USER="www-data"

# 1. Créer les répertoires
echo "Création des répertoires..."
sudo mkdir -p $PROJECT_DIR
sudo mkdir -p /var/log/gunicorn
sudo chown $SERVICE_USER:$SERVICE_USER /var/log/gunicorn

# 2. Copier les fichiers
echo "Copie des fichiers..."
sudo cp -r . $PROJECT_DIR/
sudo chown -R $SERVICE_USER:$SERVICE_USER $PROJECT_DIR

# 3. Créer l'environnement virtuel
echo "Création de l'environnement virtuel..."
sudo -u $SERVICE_USER python3 -m venv $VENV_DIR

# 4. Installer les dépendances
echo "Installation des dépendances..."
sudo -u $SERVICE_USER $VENV_DIR/bin/pip install --upgrade pip
sudo -u $SERVICE_USER $VENV_DIR/bin/pip install -r $PROJECT_DIR/requirements.txt

# 5. Configuration .env
if [ ! -f "$PROJECT_DIR/.env" ]; then
    echo "Création du fichier .env..."
    sudo -u $SERVICE_USER cp $PROJECT_DIR/.env.example $PROJECT_DIR/.env
    echo "⚠️  Éditez $PROJECT_DIR/.env avec vos configurations"
    sudo -u $SERVICE_USER nano $PROJECT_DIR/.env
fi

# 6. Migrations Django
echo "Exécution des migrations Django..."
sudo -u $SERVICE_USER $VENV_DIR/bin/python $PROJECT_DIR/manage.py makemigrations
sudo -u $SERVICE_USER $VENV_DIR/bin/python $PROJECT_DIR/manage.py migrate

# 7. Fichiers statiques
echo "Collecte des fichiers statiques..."
sudo -u $SERVICE_USER $VENV_DIR/bin/python $PROJECT_DIR/manage.py collectstatic --noinput

# 8. Configuration Gunicorn
echo "Configuration de Gunicorn..."
sed "s|/path/to/BD AGENT|$PROJECT_DIR|g" $PROJECT_DIR/systemd/gunicorn.service | \
sed "s|/path/to/venv|$VENV_DIR|g" | \
sudo tee /etc/systemd/system/gunicorn.service > /dev/null

sudo systemctl daemon-reload
sudo systemctl enable gunicorn

# 9. Configuration Apache
echo "Configuration Apache..."
sed "s|/path/to/BD AGENT|$PROJECT_DIR|g" $PROJECT_DIR/apache/datahub.conf | \
sudo tee /etc/apache2/sites-available/datahub.conf > /dev/null

sudo a2enmod ssl proxy proxy_http headers rewrite
sudo a2ensite datahub

# 10. Redémarrage des services
echo "Redémarrage des services..."
sudo systemctl restart gunicorn
sudo systemctl restart apache2

echo "=== Déploiement terminé ==="
echo ""
echo "Actions restantes:"
echo "1. Configurer SSL avec: sudo certbot --apache -d agent.co-ned.com"
echo "2. Configurer Cloudflare Tunnel (voir CLOUDFLARE_TUNNEL.md)"
echo "3. Vérifier: curl -I https://agent.co-ned.com"
