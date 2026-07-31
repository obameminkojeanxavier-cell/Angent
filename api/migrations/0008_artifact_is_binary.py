from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0007_skillfile_binary'),
    ]

    operations = [
        migrations.AddField(
            model_name='artifact',
            name='is_binary',
            field=models.BooleanField(default=False),
        ),
    ]
