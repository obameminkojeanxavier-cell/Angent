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
