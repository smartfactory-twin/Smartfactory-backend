from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='utilisateur',
            name='must_reset_password',
            field=models.BooleanField(default=False, verbose_name='Doit réinitialiser son mot de passe'),
        ),
    ]
