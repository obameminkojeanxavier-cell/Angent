from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from api.models import Skill, SkillFile

# Type MIME par extension.
EXT_CT = {
    '.md': 'text/markdown', '.markdown': 'text/markdown',
    '.html': 'text/html', '.htm': 'text/html',
    '.txt': 'text/plain', '.json': 'application/json', '.csv': 'text/csv',
    '.py': 'text/x-python', '.js': 'text/javascript', '.ts': 'text/plain',
    '.css': 'text/css', '.svg': 'image/svg+xml',
    '.yaml': 'text/yaml', '.yml': 'text/yaml', '.xml': 'application/xml',
    '.sql': 'text/plain', '.sh': 'text/x-shellscript',
}
MAX_FILE_BYTES = 1_000_000  # 1 Mo par fichier


class Command(BaseCommand):
    help = "Importe un skill (dossier complet OU fichier unique) dans la base DataHub."

    def add_arguments(self, parser):
        parser.add_argument('--name', required=True, help="Nom unique du skill")
        parser.add_argument('--path', required=True, help="Dossier du skill, ou fichier unique (.md)")
        parser.add_argument('--description', default='')
        parser.add_argument('--category', default='')
        parser.add_argument('--replace', action='store_true',
                            help="Supprime les fichiers existants du skill avant import")

    def handle(self, *args, **opts):
        src = Path(opts['path'])
        if not src.exists():
            raise CommandError(f"Chemin introuvable : {src}")

        skill, created = Skill.objects.update_or_create(
            name=opts['name'],
            defaults={'description': opts['description'], 'category': opts['category'], 'is_active': True},
        )
        if opts['replace']:
            skill.files.all().delete()

        if src.is_file():
            entries = [(src.name, src)]
        else:
            entries = [(f.relative_to(src).as_posix(), f) for f in sorted(src.rglob('*')) if f.is_file()]

        count = 0
        for rel, f in entries:
            if f.stat().st_size > MAX_FILE_BYTES:
                self.stdout.write(self.style.WARNING(f"  ignoré (trop volumineux) : {rel}"))
                continue
            try:
                content = f.read_text(encoding='utf-8-sig')  # retire un éventuel BOM
            except (UnicodeDecodeError, ValueError):
                self.stdout.write(self.style.WARNING(f"  ignoré (binaire non supporté) : {rel}"))
                continue
            ct = EXT_CT.get(f.suffix.lower(), 'text/plain')
            SkillFile.objects.update_or_create(
                skill=skill, path=rel, defaults={'content': content, 'content_type': ct}
            )
            count += 1
            self.stdout.write(f"  + {rel} ({ct})")

        state = 'créé' if created else 'mis à jour'
        self.stdout.write(self.style.SUCCESS(f"Skill '{opts['name']}' {state} : {count} fichier(s) importé(s)."))
        if not skill.files.filter(path__iexact='SKILL.md').exists():
            self.stdout.write(self.style.WARNING(
                "⚠️  Aucun SKILL.md : ajoute-en un (instructions principales que l'agent lira)."
            ))
