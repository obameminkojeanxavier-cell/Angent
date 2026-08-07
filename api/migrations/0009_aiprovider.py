from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0008_artifact_is_binary'),
    ]

    operations = [
        migrations.CreateModel(
            name='AIProvider',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, unique=True)),
                ('provider', models.CharField(default='deepseek', max_length=50)),
                ('role', models.CharField(choices=[('system', 'Agent système (analyse / optimisation)'), ('assistant', 'Assistant (aide à la rédaction, résumés)'), ('reviewer', 'Relecteur (contrôle qualité, conformité)'), ('other', 'Autre')], default='system', max_length=20)),
                ('description', models.CharField(blank=True, default='', max_length=255)),
                ('base_url', models.CharField(default='https://api.deepseek.com', max_length=255)),
                ('model', models.CharField(default='deepseek-chat', max_length=100)),
                ('api_key', models.TextField(blank=True, default='')),
                ('is_active', models.BooleanField(default=True)),
                ('can_read_data', models.BooleanField(default=True)),
                ('can_read_audit', models.BooleanField(default=True)),
                ('can_propose_changes', models.BooleanField(default=True)),
                ('can_apply_changes', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('last_used_at', models.DateTimeField(blank=True, null=True)),
            ],
            options={
                'ordering': ['name'],
            },
        ),
    ]
