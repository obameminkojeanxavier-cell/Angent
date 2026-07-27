import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='AgentClient',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, unique=True)),
                ('description', models.CharField(blank=True, default='', max_length=255)),
                ('token_hash', models.CharField(db_index=True, max_length=64, unique=True)),
                ('scopes', models.JSONField(default=list)),
                ('allowed_tables', models.JSONField(default=list)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('last_used_at', models.DateTimeField(blank=True, null=True)),
            ],
        ),
        migrations.CreateModel(
            name='SkillTask',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('skill', models.CharField(max_length=100)),
                ('params', models.JSONField(default=dict)),
                ('status', models.CharField(choices=[('pending', 'pending'), ('running', 'running'), ('succeeded', 'succeeded'), ('failed', 'failed')], default='pending', max_length=20)),
                ('result', models.JSONField(blank=True, null=True)),
                ('error', models.TextField(blank=True, default='')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('client', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='tasks', to='api.agentclient')),
            ],
        ),
        migrations.CreateModel(
            name='AuditLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('client_name', models.CharField(blank=True, default='', max_length=100)),
                ('action', models.CharField(max_length=50)),
                ('target', models.CharField(blank=True, default='', max_length=200)),
                ('status', models.CharField(max_length=20)),
                ('detail', models.JSONField(default=dict)),
                ('ip', models.GenericIPAddressField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('client', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='audit_logs', to='api.agentclient')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
