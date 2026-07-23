#!/bin/bash

# Script de configuration PostgreSQL pour DataHub
# À exécuter en tant qu'utilisateur postgres ou avec sudo

set -e

echo "=== Configuration PostgreSQL pour DataHub ==="

# Variables
DB_NAME="datahub"
DB_USER="datahub_user"

# Générer un mot de passe sécurisé
DB_PASSWORD=$(openssl rand -base64 32)

echo "Base de données: $DB_NAME"
echo "Utilisateur: $DB_USER"
echo "Mot de passe: $DB_PASSWORD"
echo ""
echo "Sauvegardez ces informations dans votre fichier .env"
echo ""

# Exécuter les commandes PostgreSQL
sudo -u postgres psql <<EOF
-- Créer la base de données
CREATE DATABASE $DB_NAME;

-- Créer l'utilisateur dédié, explicitement sans privilèges d'administration
-- (il ne peut ni créer d'autres bases, ni d'autres rôles, ni être superuser).
CREATE USER $DB_USER WITH PASSWORD '$DB_PASSWORD' NOSUPERUSER NOCREATEDB NOCREATEROLE;

-- Donner les privilèges sur la base cible uniquement
GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;

-- Se connecter à la base pour donner les privilèges sur le schéma
\c $DB_NAME

-- Donner les privilèges sur le schéma public.
-- NB PostgreSQL 15+ : le privilège CREATE sur le schéma public n'est plus
-- accordé par défaut à PUBLIC ; ce GRANT est donc indispensable pour que
-- l'agent puisse créer des tables.
GRANT ALL ON SCHEMA public TO $DB_USER;

-- Donner les privilèges par défaut pour les futures tables
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO $DB_USER;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO $DB_USER;

-- Quitter
\q
EOF

echo "=== Configuration PostgreSQL terminée ==="
echo ""
echo "Ajoutez ceci à votre fichier .env:"
echo "DB_NAME=$DB_NAME"
echo "DB_USER=$DB_USER"
echo "DB_PASSWORD=$DB_PASSWORD"
echo "DB_HOST=localhost"
echo "DB_PORT=5432"
