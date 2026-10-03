from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_telephone'),
    ]

    operations = [
        migrations.AddField(
            model_name='utilisateur',
            name='photo',
            field=models.ImageField(
                blank=True, null=True,
                upload_to='profiles/',
                verbose_name='Photo de profil'
            ),
        ),
    ]
