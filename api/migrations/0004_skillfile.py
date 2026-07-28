import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0003_artifact'),
    ]

    operations = [
        migrations.CreateModel(
            name='SkillFile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('path', models.CharField(max_length=255)),
                ('content', models.TextField(blank=True, default='')),
                ('content_type', models.CharField(default='text/plain', max_length=100)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('skill', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='files', to='api.skill')),
            ],
            options={
                'ordering': ['path'],
                'unique_together': {('skill', 'path')},
            },
        ),
    ]
