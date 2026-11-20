from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('equipements', '0009_work_orders_and_recurring_maintenance')]

    operations = [
        migrations.AlterField(
            model_name='sensor', name='frequence_mesure',
            field=models.IntegerField(blank=True, help_text='Fréquence en secondes', null=True, verbose_name='Fréquence de mesure (secondes)'),
        ),
        migrations.AlterField(
            model_name='sensor', name='seuil_min',
            field=models.FloatField(blank=True, null=True, verbose_name='Seuil minimum'),
        ),
        migrations.AlterField(
            model_name='sensor', name='seuil_max',
            field=models.FloatField(blank=True, null=True, verbose_name='Seuil maximum'),
        ),
        migrations.AddField(
            model_name='sensor', name='sensor_role',
            field=models.CharField(choices=[('temperature', 'Température'), ('vibration', 'Vibration'), ('pressure', 'Pression'), ('flow', 'Débit'), ('current', 'Courant'), ('speed', 'Vitesse'), ('other', 'Autre')], default='other', max_length=20),
        ),
        migrations.AddField(model_name='sensor', name='nominal_min', field=models.FloatField(blank=True, null=True)),
        migrations.AddField(model_name='sensor', name='nominal_max', field=models.FloatField(blank=True, null=True)),
        migrations.AddField(
            model_name='sensor', name='criticality',
            field=models.CharField(choices=[('low', 'Faible'), ('medium', 'Moyenne'), ('high', 'Élevée')], default='low', max_length=10),
        ),
        migrations.AddField(model_name='sensor', name='is_ai_eligible', field=models.BooleanField(default=False)),
    ]
