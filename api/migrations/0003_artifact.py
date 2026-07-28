import django.db.models.deletion
from django.db import migrations, models

import api.models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0002_skill'),
    ]

    operations = [
        migrations.CreateModel(
            name='Artifact',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('slug', models.CharField(db_index=True, default=api.models._artifact_slug, editable=False, max_length=32, unique=True)),
                ('name', models.CharField(blank=True, default='', max_length=200)),
                ('content_type', models.CharField(default='text/html', max_length=100)),
                ('content', models.TextField(blank=True, default='')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('client', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='artifacts', to='api.agentclient')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
