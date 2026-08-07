from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0009_aiprovider'),
    ]

    operations = [
        migrations.AddField(
            model_name='aiprovider',
            name='system_prompt',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='aiprovider',
            name='test_message',
            field=models.TextField(
                blank=True, default='',
                help_text='Question de contrôle envoyée lors de la vérification.'),
        ),
        migrations.AddField(
            model_name='aiprovider',
            name='temperature',
            field=models.FloatField(default=0.2),
        ),
        migrations.AddField(
            model_name='aiprovider',
            name='max_tokens',
            field=models.IntegerField(default=1024),
        ),
    ]
