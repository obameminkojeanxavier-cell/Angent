from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0004_skillfile'),
    ]

    operations = [
        migrations.AddField(
            model_name='skill',
            name='kind',
            field=models.CharField(blank=True, default='', max_length=50),
        ),
        migrations.AddField(
            model_name='skill',
            name='is_orchestrator',
            field=models.BooleanField(default=False),
        ),
    ]
