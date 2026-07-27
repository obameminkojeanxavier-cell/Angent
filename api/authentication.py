from django.utils import timezone
from rest_framework import authentication
from rest_framework.exceptions import AuthenticationFailed

from .tokens import resolve_client


class AgentTokenAuthentication(authentication.BaseAuthentication):
    """
    Authentification par `Authorization: Bearer <token>`.

    Le token est résolu vers un AgentClient (token maître de .env, ou client
    enregistré en base). En cas de succès, request.user = le client (avec ses
    scopes et tables autorisées).
    """

    keyword = 'Bearer'

    def authenticate(self, request):
        header = request.META.get('HTTP_AUTHORIZATION', '')

        # Pas de header Bearer -> pas de credentials : la permission décidera
        # (les lectures peuvent rester publiques selon REQUIRE_AUTH_FOR_READ).
        if not header.startswith(self.keyword + ' '):
            return None

        raw = header[len(self.keyword) + 1:].strip()
        if not raw:
            raise AuthenticationFailed('Empty token')

        client = resolve_client(raw)
        if client is None:
            raise AuthenticationFailed('Invalid or inactive token')

        # Trace de dernière utilisation (uniquement pour les clients en base).
        if getattr(client, 'pk', None):
            try:
                type(client).objects.filter(pk=client.pk).update(
                    last_used_at=timezone.now()
                )
            except Exception:
                pass

        return (client, raw)

    def authenticate_header(self, request):
        return self.keyword
