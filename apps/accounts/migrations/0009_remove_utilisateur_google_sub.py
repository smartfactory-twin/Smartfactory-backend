from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0008_utilisateur_google_sub'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='utilisateur',
            name='google_sub',
        ),
    ]
