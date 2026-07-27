from django.core.management.base import BaseCommand, CommandError

from api.models import AgentClient


class Command(BaseCommand):
    help = "Désactive (révoque) un client agent par son nom. Son token cesse de fonctionner."

    def add_arguments(self, parser):
        parser.add_argument('--name', required=True)
        parser.add_argument(
            '--delete', action='store_true',
            help='Supprimer définitivement au lieu de simplement désactiver',
        )

    def handle(self, *args, **opts):
        name = opts['name']
        try:
            client = AgentClient.objects.get(name=name)
        except AgentClient.DoesNotExist:
            raise CommandError(f"Aucun client nommé '{name}'.")

        if opts['delete']:
            client.delete()
            self.stdout.write(self.style.SUCCESS(f"Client '{name}' supprimé."))
        else:
            client.is_active = False
            client.save(update_fields=['is_active'])
            self.stdout.write(self.style.SUCCESS(f"Client '{name}' désactivé."))
