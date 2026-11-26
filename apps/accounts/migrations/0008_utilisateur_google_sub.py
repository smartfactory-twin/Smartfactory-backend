from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0007_auditlog_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='utilisateur',
            name='google_sub',
            field=models.CharField(
                blank=True,
                editable=False,
                max_length=255,
                null=True,
                unique=True,
                verbose_name='Identifiant Google',
            ),
        ),
    ]
