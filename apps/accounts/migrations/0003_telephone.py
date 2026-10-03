from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_must_reset_password'),
    ]

    operations = [
        migrations.AddField(
            model_name='utilisateur',
            name='telephone',
            field=models.CharField(
                blank=True, default='', max_length=20,
                verbose_name='Numéro de téléphone'
            ),
        ),
    ]
