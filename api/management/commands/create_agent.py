from django.core.management.base import BaseCommand, CommandError

from api.models import AgentClient
from api.tokens import generate_token, hash_token, ALL_SCOPES


class Command(BaseCommand):
    help = "Crée un client agent (LLM/skill) et affiche son token UNE seule fois."

    def add_arguments(self, parser):
        parser.add_argument('--name', required=True, help='Nom unique du client')
        parser.add_argument(
            '--scopes', default='',
            help='Liste séparée par virgules parmi: ' + ','.join(ALL_SCOPES) + '  (ou "*" pour tous)',
        )
        parser.add_argument(
            '--tables', default='',
            help='Tables autorisées séparées par virgules (vide = toutes)',
        )
        parser.add_argument('--description', default='')

    def handle(self, *args, **opts):
        name = opts['name']
        if AgentClient.objects.filter(name=name).exists():
            raise CommandError(f"Un client nommé '{name}' existe déjà.")

        raw_scopes = [s.strip() for s in opts['scopes'].split(',') if s.strip()]
        if raw_scopes != ['*']:
            invalid = [s for s in raw_scopes if s not in ALL_SCOPES]
            if invalid:
                raise CommandError(
                    "Scopes invalides: " + ','.join(invalid)
                    + " | valides: " + ','.join(ALL_SCOPES) + " ou *"
                )
        tables = [t.strip() for t in opts['tables'].split(',') if t.strip()]

        token = generate_token()
        AgentClient.objects.create(
            name=name,
            description=opts['description'],
            token_hash=hash_token(token),
            scopes=raw_scopes,
            allowed_tables=tables,
        )

        self.stdout.write(self.style.SUCCESS(f"Agent créé : {name}"))
        self.stdout.write(f"Scopes : {','.join(raw_scopes) or '(aucun)'}")
        self.stdout.write(f"Tables : {','.join(tables) or 'toutes'}")
        self.stdout.write('')
        self.stdout.write(self.style.WARNING('TOKEN (copie-le maintenant, non ré-affichable) :'))
        self.stdout.write(token)
