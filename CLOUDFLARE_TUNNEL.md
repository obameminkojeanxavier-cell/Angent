# Configuration Cloudflare Tunnel - DataHub

Ce guide détaille la configuration du tunnel Cloudflare pour exposer DataHub via `agent.co-ned.com`.

## Prérequis

- Compte Cloudflare avec le domaine `co-ned.com`
- Accès SSH au serveur Debian
- Tunnel existant: `débain13_12`

## Installation de cloudflared

```bash
# Télécharger la dernière version
wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb

# Installer
sudo dpkg -i cloudflared-linux-amd64.deb

# Vérifier l'installation
cloudflared --version
```

## Authentification

```bash
# Authentifier avec Cloudflare
cloudflared tunnel login
```

Cela ouvrira un navigateur pour vous connecter à votre compte Cloudflare et autoriser l'accès.

## Récupération ou création du tunnel

### Si le tunnel existe déjà

```bash
# Lister les tunnels existants
cloudflared tunnel list

# Récupérer l'ID du tunnel "débain13_12"
cloudflared tunnel info débain13_12
```

Notez le `Tunnel ID` (format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)

### Si le tunnel n'existe pas

```bash
# Créer le tunnel
cloudflared tunnel create débain13_12

# Notez l'ID retourné
```

## Configuration DNS

```bash
# Configurer le DNS pour agent.co-ned.com
cloudflared tunnel route dns débain13_12 agent.co-ned.com
```

Cela créera un enregistrement CNAME dans Cloudflare DNS pointant vers le tunnel.

## Fichier de configuration

Créer le fichier de configuration:

```bash
sudo mkdir -p /etc/cloudflared
sudo nano /etc/cloudflared/config.yml
```

Contenu:

```yaml
tunnel: <TUNNEL_ID>  # Remplacer par l'ID du tunnel
credentials-file: /home/<votre_user>/.cloudflared/<TUNNEL_ID>.json

ingress:
  # Route pour DataHub
  - hostname: agent.co-ned.com
    service: http://localhost:80
  
  # Route par défaut (optionnel)
  - service: http_status:404
```

Remplacer:
- `<TUNNEL_ID>` par l'ID de votre tunnel
- `<votre_user>` par votre nom d'utilisateur

## Installation en tant que service

```bash
# Installer le service systemd
sudo cloudflared service install

# Démarrer le service
sudo systemctl start cloudflared

# Activer au démarrage
sudo systemctl enable cloudflared

# Vérifier le statut
sudo systemctl status cloudflared
```

## Vérification

```bash
# Voir les logs
sudo journalctl -u cloudflared -f

# Tester l'accès
curl -I https://agent.co-ned.com
```

## Gestion du tunnel

### Démarrer/Arrêter/Redémarrer

```bash
sudo systemctl start cloudflared
sudo systemctl stop cloudflared
sudo systemctl restart cloudflared
```

### Mettre à jour cloudflared

```bash
# Arrêter le service
sudo systemctl stop cloudflared

# Télécharger la nouvelle version
wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb

# Installer
sudo dpkg -i cloudflared-linux-amd64.deb

# Redémarrer
sudo systemctl start cloudflared
```

### Supprimer le tunnel (si nécessaire)

```bash
# Arrêter et désactiver le service
sudo systemctl stop cloudflared
sudo systemctl disable cloudflared

# Supprimer le service
sudo cloudflared service uninstall

# Supprimer le tunnel de Cloudflare
cloudflared tunnel delete débain13_12

# Supprimer les fichiers locaux
sudo rm -rf /etc/cloudflared
rm -rf ~/.cloudflared
```

## Configuration avancée

### Protéger tout le site avec Cloudflare Access (Zero Trust)

La lecture (list/select/schema) et la page web sont **publiques côté Django**.
Pour qu'elles ne soient pas ouvertes à tout Internet, on place l'ensemble du
site derrière **Cloudflare Access** : les humains se connectent (email/SSO), et
l'agent non-interactif utilise un **service token**.

> ⚠️ Point clé : un agent (MCP ou REST) ne peut pas faire le login navigateur
> d'Access. Sans service token, Access **bloquerait** tous ses appels. Il faut
> donc créer un service token et une politique qui l'accepte.

**1. Créer l'application Access**

1. Dashboard Cloudflare → **Zero Trust** → **Access** → **Applications** → *Add an application* → **Self-hosted**.
2. Application domain : `agent.co-ned.com` (couvre `/`, `/api`, `/mcp`).

**2. Créer un service token pour l'agent**

1. Zero Trust → **Access** → **Service Auth** → **Service Tokens** → *Create*.
2. Notez `Client ID` et `Client Secret` (le secret n'est affiché qu'une fois).

**3. Définir les politiques de l'application**

- Politique *Humains* — **Allow** : `Emails ending in @co-ned.com` (ou SSO) → accès à la page de consultation.
- Politique *Agent* — **Service Auth** (Allow, non-identity) : sélectionner le service token créé → accès programmatique.

**4. Côté agent : envoyer les deux niveaux de secret**

L'agent ajoute les en-têtes du service token Cloudflare **en plus** du token API :

```bash
curl https://agent.co-ned.com/api/tables/ \
  -H "CF-Access-Client-Id: <CLIENT_ID>.access" \
  -H "CF-Access-Client-Secret: <CLIENT_SECRET>" \
  -H "Authorization: Bearer <API_TOKEN>"
```

Pour le MCP, le client MCP doit être configuré avec ces mêmes en-têtes HTTP
personnalisés sur l'endpoint `https://agent.co-ned.com/mcp`.

> Alternative plus simple (moins stricte) : au lieu d'un service token, ajouter
> une politique **Bypass** sur les chemins `/api` et `/mcp`. La page web reste
> protégée par login Access, mais l'API/MCP ne sont plus gardées que par le
> token API. À n'utiliser que si gérer un service token côté agent est trop lourd.

### Authenticated Origin Pulls (optionnel, défense en profondeur)

1. Dashboard Cloudflare → domaine `co-ned.com` → **SSL/TLS → Edge Certificates**
2. Activer **Authenticated Origin Pulls** pour garantir que l'origine n'accepte que le trafic Cloudflare.

### Compression

Ajouter au fichier `config.yml`:

```yaml
warp-routing:
  enabled: true
```

### Logs détaillés

Modifier le service systemd pour activer les logs:

```bash
sudo systemctl edit cloudflared
```

Ajouter:

```ini
[Service]
Environment="TUNNEL_LOGLEVEL=debug"
```

## Dépannage

### Le tunnel ne démarre pas

```bash
# Vérifier les logs
sudo journalctl -u cloudflared -n 100

# Vérifier la configuration
cloudflared tunnel ingress validate

# Tester la configuration
cloudflared --config /etc/cloudflared/config.yml tunnel run débain13_12
```

### Erreur de certificat

```bash
# Vérifier que le fichier de credentials existe
ls -la ~/.cloudflared/

# Recréer les credentials si nécessaire
cloudflared tunnel token débain13_12
```

### DNS ne propage pas

```bash
# Vérifier la configuration DNS
cloudflared tunnel route dns débain13_12

# Forcer la propagation (via dashboard Cloudflare)
```

### Erreur 502/503

Vérifier qu'Apache écoute sur le port 80:

```bash
sudo netstat -tlnp | grep :80
sudo systemctl status apache2
```

## Sécurité

- Le tunnel utilise TLS automatique
- Activez "Authenticated Origin Pulls" dans Cloudflare
- Utilisez des règles Zero Trust pour restreindre l'accès si nécessaire
- Gardez cloudflared à jour

## Architecture finale

```
Internet → Cloudflare Edge → Cloudflare Tunnel (débain13_12) → Apache (443/80) → Gunicorn (8000) → Django → PostgreSQL
```

L'agent distant accède à la base via :
- API REST : `https://agent.co-ned.com/api/`
- Serveur MCP : `https://agent.co-ned.com/mcp`

(les deux protégés par le token API ; et par le service token Cloudflare Access
si la protection Zero Trust est activée).
