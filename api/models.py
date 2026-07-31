import secrets
import uuid

from django.db import models


def _artifact_slug():
    return secrets.token_urlsafe(8)


class AgentClient(models.Model):
    """
    Un consommateur des API : un modèle LLM (ChatGPT, Claude), un agent ou un
    skill. Chacun possède son propre token (stocké hashé) et un ensemble de
    permissions (scopes) et de tables autorisées.
    """

    name = models.CharField(max_length=100, unique=True)
    description = models.CharField(max_length=255, blank=True, default='')
    # SHA-256 du token en clair (le token n'est jamais stocké en clair).
    token_hash = models.CharField(max_length=64, unique=True, db_index=True)
    # Liste de scopes, ex: ["data:read", "data:write"]. "*" = tous.
    scopes = models.JSONField(default=list)
    # Tables autorisées ; liste vide = toutes les tables.
    allowed_tables = models.JSONField(default=list)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.name

    # DRF : IsAuthenticated vérifie request.user.is_authenticated.
    @property
    def is_authenticated(self):
        return True

    def has_scope(self, scope):
        if not scope:
            return True
        return '*' in self.scopes or scope in self.scopes

    def can_access_table(self, table):
        return not self.allowed_tables or table in self.allowed_tables


class SkillTask(models.Model):
    """Trace d'exécution d'un skill : permet de suivre l'état et le résultat."""

    STATUS_CHOICES = [
        ('pending', 'pending'),
        ('running', 'running'),
        ('succeeded', 'succeeded'),
        ('failed', 'failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client = models.ForeignKey(
        AgentClient, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='tasks',
    )
    skill = models.CharField(max_length=100)
    params = models.JSONField(default=dict)
    status = models.CharField(max_length=20, default='pending', choices=STATUS_CHOICES)
    result = models.JSONField(null=True, blank=True)
    error = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.skill}:{self.id}'


class Skill(models.Model):
    """
    Skill enregistré en base, injecté manuellement par l'administrateur.

    ChatGPT le LIT (nom, description, instructions, exemple) puis l'exécute en
    suivant les instructions via les actions CRUD. Aucun code n'est stocké ni
    exécuté ici : `instructions` est du texte que l'agent interprète.
    """

    name = models.CharField(max_length=100, unique=True)
    description = models.CharField(max_length=255, blank=True, default='')
    category = models.CharField(max_length=100, blank=True, default='')
    # 'orchestrateur' pour le skill principal, sinon type de capacité du
    # sous-skill (ex: fs.write, db.insert…) ou vide (instructionnel).
    kind = models.CharField(max_length=50, blank=True, default='')
    # True = skill orchestrateur (point d'entrée / verrou). Un seul suffit.
    is_orchestrator = models.BooleanField(default=False)
    # Instructions détaillées : ce que l'agent doit faire, quelles actions
    # appeler, dans quel ordre, avec quels paramètres.
    instructions = models.TextField(blank=True, default='')
    # Exemple d'entrée (paramètres attendus), pour guider l'agent.
    input_example = models.JSONField(null=True, blank=True)
    # Point d'entrée du skill (fichier principal à exécuter, ex: generator.py, template.html)
    entry_point = models.CharField(max_length=255, blank=True, default='')
    # Type de sortie attendu (html, pdf, markdown, json, etc.)
    output_type = models.CharField(max_length=50, blank=True, default='html')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    @property
    def entry_instructions(self):
        """Instructions principales : contenu de SKILL.md si présent, sinon le champ instructions."""
        entry = self.files.filter(path__iexact='SKILL.md').first()
        if entry:
            return entry.content
        return self.instructions


class SkillFile(models.Model):
    """
    Un fichier appartenant à un skill (skill = dossier). Chemin relatif dans le
    dossier, ex: 'SKILL.md', 'templates/rapport.html', 'scripts/gen.py'.
    Le contenu est stocké tel quel ; il n'est JAMAIS exécuté côté serveur.
    """

    skill = models.ForeignKey(Skill, related_name='files', on_delete=models.CASCADE)
    path = models.CharField(max_length=255)
    # Contenu texte (scripts, markdown, html, yaml…)
    content = models.TextField(blank=True, default='')
    # Contenu binaire (logos PNG/WEBP, modèles DOCX…) : indispensable pour que
    # les ressources du skill soient restituées à l'exécution.
    content_binary = models.BinaryField(null=True, blank=True, editable=False)
    is_binary = models.BooleanField(default=False)
    content_type = models.CharField(max_length=100, default='text/plain')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['path']
        unique_together = ('skill', 'path')

    def __str__(self):
        return f'{self.skill.name}/{self.path}'

    @property
    def size(self):
        if self.is_binary:
            return len(self.content_binary or b'')
        return len((self.content or '').encode('utf-8'))

    def write_to(self, target_path):
        """Écrit ce fichier sur le disque, en binaire ou en texte selon son type."""
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if self.is_binary:
            data = self.content_binary
            # psycopg peut renvoyer un memoryview pour un BinaryField.
            if isinstance(data, memoryview):
                data = data.tobytes()
            target_path.write_bytes(data or b'')
        else:
            target_path.write_text(self.content or '', encoding='utf-8')


class Artifact(models.Model):
    """
    Contenu produit par un agent (HTML, texte, CSV, JSON, Markdown, SVG…),
    stocké et servi à une URL publique `/a/<slug>` : rendu si HTML, sinon
    téléchargé. L'agent génère le contenu ; DataHub le conserve et l'expose.
    """

    slug = models.CharField(max_length=32, unique=True, default=_artifact_slug,
                            editable=False, db_index=True)
    name = models.CharField(max_length=200, blank=True, default='')
    content_type = models.CharField(max_length=100, default='text/html')
    content = models.TextField(blank=True, default='')
    client = models.ForeignKey(
        AgentClient, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='artifacts',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.name or self.slug} ({self.content_type})'


class AuditLog(models.Model):
    """Historique de toutes les opérations effectuées via les API."""

    client = models.ForeignKey(
        AgentClient, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='audit_logs',
    )
    # Nom figé (au cas où le client serait supprimé plus tard).
    client_name = models.CharField(max_length=100, blank=True, default='')
    action = models.CharField(max_length=50)      # ex: select, insert, skill.run
    target = models.CharField(max_length=200, blank=True, default='')  # table / skill
    status = models.CharField(max_length=20)       # success | error | denied
    detail = models.JSONField(default=dict)        # résumé, sans secret
    ip = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.action} {self.target} ({self.status})'
