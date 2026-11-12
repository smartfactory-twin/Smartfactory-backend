from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('equipements', '0006_remove_userscope_userscope_unique_target'),
    ]

    operations = [
        migrations.AddField(
            model_name='machine',
            name='type_equipement',
            field=models.CharField(
                blank=True,
                choices=[
                    ('COMPRESSEUR', 'Compresseur'),
                    ('POMPE', 'Pompe'),
                    ('MOTEUR', 'Moteur'),
                    ('CONVOYEUR', 'Convoyeur'),
                    ('TURBINE', 'Turbine'),
                    ('PRESSE', 'Presse'),
                    ('AUTRE', 'Autre'),
                ],
                default='',
                max_length=20,
            ),
        ),
    ]
