from django.core.management.base import BaseCommand

from api.models import AgentClient


class Command(BaseCommand):
    help = "Liste les clients agents enregistrés (sans révéler les tokens)."

    def handle(self, *args, **opts):
        clients = AgentClient.objects.all().order_by('name')
        if not clients:
            self.stdout.write("Aucun client enregistré.")
            return
        for c in clients:
            state = 'actif' if c.is_active else 'désactivé'
            scopes = ','.join(c.scopes) or '(aucun)'
            tables = ','.join(c.allowed_tables) or 'toutes'
            last = c.last_used_at.isoformat() if c.last_used_at else 'jamais'
            self.stdout.write(
                f"- {c.name} [{state}] scopes={scopes} tables={tables} dernier_usage={last}"
            )
