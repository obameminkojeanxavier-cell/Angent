"""
Rate limiting middleware pour protéger l'API et le serveur MCP contre les abus.
Utilise un cache en mémoire pour suivre les requêtes par IP et par client.
"""
from django.core.cache import cache
from django.http import JsonResponse
from django.conf import settings
import time


class RateLimitMiddleware:
    """
    Middleware qui limite le nombre de requêtes par minute par IP et par client.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        # Limites par défaut (surchargeables dans settings)
        self.requests_per_minute = getattr(settings, 'RATE_LIMIT_PER_MINUTE', 60)
        self.requests_per_hour = getattr(settings, 'RATE_LIMIT_PER_HOUR', 1000)
    
    def __call__(self, request):
        # Identifier la clé de rate limiting
        client_ip = self._get_client_ip(request)
        client_id = self._get_client_id(request)
        
        # Clé combinée IP + client pour un suivi plus précis
        cache_key = f"rate_limit:{client_ip}:{client_id}"
        
        # Récupérer l'historique des requêtes
        history = cache.get(cache_key, [])
        now = time.time()
        
        # Nettoyer les requêtes anciennes (plus d'une heure)
        history = [t for t in history if now - t < 3600]
        
        # Vérifier limite par minute
        minute_ago = now - 60
        recent_requests = [t for t in history if t > minute_ago]
        if len(recent_requests) >= self.requests_per_minute:
            return self._rate_limit_response("Too many requests (per minute limit exceeded)")
        
        # Vérifier limite par heure
        if len(history) >= self.requests_per_hour:
            return self._rate_limit_response("Too many requests (per hour limit exceeded)")
        
        # Ajouter cette requête à l'historique
        history.append(now)
        cache.set(cache_key, history, 3600)  # Garder 1 heure
        
        return self.get_response(request)
    
    def _get_client_ip(self, request):
        """Extraire l'IP réelle du client (gère les proxies)."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', 'unknown')
    
    def _get_client_id(self, request):
        """Extraire l'identifiant du client (token hashé ou 'anonymous')."""
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        if auth_header.startswith('Bearer '):
            token = auth_header[7:].strip()
            # Hasher le token pour identifier le client sans stocker le token en clair
            import hashlib
            return hashlib.sha256(token.encode()).hexdigest()[:16]
        return 'anonymous'
    
    def _rate_limit_response(self, message):
        """Réponse JSON-RPC pour rate limit."""
        return JsonResponse({
            "success": False,
            "error": {
                "code": "RATE_LIMIT_EXCEEDED",
                "message": message
            }
        }, status=429)
