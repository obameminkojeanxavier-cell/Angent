import uuid

from django.db import models


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
