from django.contrib import admin

from .models import AgentClient, SkillTask, AuditLog, Skill, Artifact


@admin.register(Artifact)
class ArtifactAdmin(admin.ModelAdmin):
    list_display = ('slug', 'name', 'content_type', 'client', 'created_at')
    list_filter = ('content_type',)
    search_fields = ('slug', 'name')
    readonly_fields = ('slug', 'created_at', 'updated_at')


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'description', 'is_active', 'updated_at')
    list_filter = ('is_active', 'category')
    search_fields = ('name', 'description', 'instructions')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(AgentClient)
class AgentClientAdmin(admin.ModelAdmin):
    list_display = ('name', 'scopes', 'allowed_tables', 'is_active', 'created_at', 'last_used_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'description')
    # token_hash en lecture seule : on ne modifie pas un token à la main.
    readonly_fields = ('token_hash', 'created_at', 'last_used_at')


@admin.register(SkillTask)
class SkillTaskAdmin(admin.ModelAdmin):
    list_display = ('id', 'skill', 'status', 'client', 'created_at', 'updated_at')
    list_filter = ('status', 'skill')
    readonly_fields = ('id', 'created_at', 'updated_at')


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'client_name', 'action', 'target', 'status', 'ip')
    list_filter = ('status', 'action')
    search_fields = ('client_name', 'action', 'target')
    readonly_fields = ('client', 'client_name', 'action', 'target', 'status', 'detail', 'ip', 'created_at')
