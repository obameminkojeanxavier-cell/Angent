from django.conf import settings
from rest_framework.permissions import BasePermission


def _is_agent(user):
    return bool(getattr(user, 'is_authenticated', False))


class ReadAccess(BasePermission):
    """
    Lecture de données.

    - Si un client est authentifié : il doit posséder le scope data:read.
    - Sinon (anonyme) : autorisé seulement si REQUIRE_AUTH_FOR_READ est False
      (page web de consultation, derrière Cloudflare Access).
    """

    def has_permission(self, request, view):
        user = request.user
        if _is_agent(user):
            return user.has_scope('data:read')
        return not getattr(settings, 'REQUIRE_AUTH_FOR_READ', False)


class HasScope(BasePermission):
    """
    Exige un client authentifié possédant le scope déclaré par la vue
    (attribut `required_scope`).
    """

    message = 'Permission (scope) insuffisante pour cette opération.'

    def has_permission(self, request, view):
        user = request.user
        if not _is_agent(user):
            return False
        scope = getattr(view, 'required_scope', None)
        return user.has_scope(scope)


ORCHESTRATOR_MISSING = (
    "Aucun skill orchestrateur n'est installé : l'agent n'a pas accès au serveur "
    "ni à la base de données. Veuillez importer le skill orchestrateur, puis réessayer."
)


class OrchestratorGate(BasePermission):
    """
    Verrou à deux niveaux : tant qu'aucun skill ORCHESTRATEUR actif n'existe,
    un agent ne peut réaliser AUCUNE action sur le serveur / la base.

    Exemptions :
    - requêtes anonymes (page web publique) — gérées par ReadAccess ;
    - token maître (client synthétique, pk None) — admin / tests ;
    - vues marquées `orchestrator_exempt = True` (catalogue des skills), pour que
      l'agent puisse toujours découvrir les compétences et signaler l'absence
      d'orchestrateur.
    """

    def has_permission(self, request, view):
        if getattr(view, 'orchestrator_exempt', False):
            return True
        user = request.user
        if not _is_agent(user):
            return True
        if getattr(user, 'pk', None) is None:  # token maître
            return True
        from .skills import orchestrator_active
        if orchestrator_active():
            return True
        self.message = ORCHESTRATOR_MISSING
        return False
