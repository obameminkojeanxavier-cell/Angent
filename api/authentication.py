import secrets

from django.conf import settings
from rest_framework import authentication
from rest_framework.exceptions import AuthenticationFailed


class APIUser:
    """
    Principal léger représentant un appelant authentifié par token.

    On n'utilise pas d'utilisateur en base : le token API suffit. DRF exige
    seulement que `request.user.is_authenticated` soit vrai pour que la
    permission IsAuthenticated laisse passer la requête.
    """

    is_authenticated = True
    is_active = True
    is_anonymous = False

    def __str__(self):
        return 'api-token'


class TokenAuthentication(authentication.BaseAuthentication):
    """Authentification par header `Authorization: Bearer <API_TOKEN>`."""

    keyword = 'Bearer'

    def authenticate(self, request):
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')

        # Pas de header Bearer -> pas de credentials fournis.
        # On renvoie None : la classe de permission décidera (401 si protégé,
        # accès autorisé si l'endpoint est public).
        if not auth_header.startswith(self.keyword + ' '):
            return None

        token = auth_header[len(self.keyword) + 1:].strip()

        expected = settings.API_TOKEN
        # Refus si le serveur n'a pas de token configuré : sinon un Bearer vide
        # comparé à une chaîne vide passerait ('' == '').
        if not expected:
            raise AuthenticationFailed('API token not configured on server')

        # Comparaison en temps constant pour éviter les attaques temporelles.
        if not token or not secrets.compare_digest(token, expected):
            raise AuthenticationFailed('Invalid API token')

        return (APIUser(), token)

    def authenticate_header(self, request):
        # Fait renvoyer 401 (et pas 403) sur échec/absence d'authentification.
        return self.keyword
