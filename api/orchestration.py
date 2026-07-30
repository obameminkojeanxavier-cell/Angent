"""
Middleware d'orchestration pour imposer le passage par le skill orchestrateur.

Ce middleware vérifie qu'un orchestrateur actif existe avant d'autoriser l'accès
aux endpoints sensibles (API REST et MCP). Les routes d'administration sont exemptées.
"""
from django.http import JsonResponse
from django.conf import settings


class OrchestrationMiddleware:
    """
    Middleware qui impose le passage par le skill orchestrateur pour les agents.
    
    Les routes exemptées (configurées via ORCHESTRATION_EXEMPT_PATHS) ne sont pas
    soumises à cette vérification : administration, documentation, etc.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        # Routes exemptées par défaut (administration, docs, login)
        self.exempt_paths = getattr(settings, 'ORCHESTRATION_EXEMPT_PATHS', [
            '/manage/',
            '/admin/',
            '/api.md',
            '/skill.md',
            '/openapi.json',
            '/a/',
            '/static/',
            '/api/skills/orchestrator/',  # Endpoint dédié exempté
            '/api/skills/orchestrator/active/',  # Endpoint dédié exempté
            '/api/skills/',  # Tous les endpoints skills (définition, fichiers, exécution)
        ])
    
    def __call__(self, request):
        path = request.path
        
        # Exempter les routes d'administration et documentation
        for exempt in self.exempt_paths:
            if path.startswith(exempt):
                return self.get_response(request)
        
        # Vérifier si un orchestrateur est actif
        if not self._orchestrator_active():
            # Pour les requêtes API/MCP, renvoyer une erreur structurée
            if path.startswith('/api/') or path.startswith('/mcp'):
                return JsonResponse({
                    'error': 'ORCHESTRATOR_REQUIRED',
                    'message': 'Aucun skill orchestrateur actif. Les agents doivent passer par l\'orchestrateur pour accéder au système.',
                    'hint': 'Importez et activez un skill orchestrateur depuis l\'administration (/manage/).'
                }, status=403)
        
        return self.get_response(request)
    
    def _orchestrator_active(self):
        """Vérifie si un skill orchestrateur actif existe via l'endpoint dédié."""
        try:
            from .models import Skill
            # Utilisation directe du modèle pour éviter les appels récursifs dans le middleware
            return Skill.objects.filter(is_orchestrator=True, is_active=True).exists()
        except Exception:
            # En cas d'erreur (base non migrée), on refuse l'accès par sécurité
            return False
