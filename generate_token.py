#!/usr/bin/env python3
"""
Générateur de token API pour DataHub
"""

import secrets

def generate_token():
    """Génère un token sécurisé de 32 octets en base64"""
    token = secrets.token_urlsafe(32)
    return token

if __name__ == "__main__":
    token = generate_token()
    print("=== Token API généré ===")
    print(f"API_TOKEN={token}")
    print("")
    print("Ajoutez cette valeur à votre fichier .env")
