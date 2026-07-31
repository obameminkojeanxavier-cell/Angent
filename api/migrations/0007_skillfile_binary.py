from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0006_skill_entry_point_skill_output_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='skillfile',
            name='content_binary',
            field=models.BinaryField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name='skillfile',
            name='is_binary',
            field=models.BooleanField(default=False),
        ),
    ]
