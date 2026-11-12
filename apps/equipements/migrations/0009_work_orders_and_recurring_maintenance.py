import django.utils.timezone
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('equipements', '0008_inspection_gallery_annotations_and_video'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='OrdreTravail',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('type_ordre', models.CharField(choices=[('Corrective', 'Corrective'), ('Préventive', 'Préventive'), ('Inspection', 'Inspection')], default='Corrective', max_length=20)),
                ('priorite', models.CharField(choices=[('Haute', 'Haute'), ('Moyenne', 'Moyenne'), ('Basse', 'Basse')], default='Moyenne', max_length=10)),
                ('titre', models.CharField(max_length=300)),
                ('assigne', models.CharField(blank=True, default='', max_length=150)),
                ('statut', models.CharField(choices=[('Créé', 'Créé'), ('Assigné', 'Assigné'), ('En cours', 'En cours'), ('En attente pièces', 'En attente pièces'), ('Rapport déposé', 'Rapport déposé'), ('Validé', 'Validé'), ('Clôturé', 'Clôturé')], default='Créé', max_length=30)),
                ('echeance', models.DateTimeField(blank=True, null=True)),
                ('from_alert', models.PositiveIntegerField(blank=True, null=True)),
                ('historique', models.JSONField(blank=True, default=list)),
                ('rapport', models.JSONField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('cree_par', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='ordres_travail_crees', to=settings.AUTH_USER_MODEL)),
                ('machine', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ordres_travail', to='equipements.machine')),
            ],
            options={'verbose_name': 'Ordre de travail', 'verbose_name_plural': 'Ordres de travail', 'ordering': ['-created_at', '-pk']},
        ),
        migrations.CreateModel(
            name='MaintenanceRecurrente',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('titre', models.CharField(max_length=200)),
                ('frequence_jours', models.PositiveIntegerField(default=30)),
                ('date_debut', models.DateField(default=django.utils.timezone.localdate)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('cree_par', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='maintenances_recurrentes_creees', to=settings.AUTH_USER_MODEL)),
                ('machine', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='maintenances_recurrentes', to='equipements.machine')),
            ],
            options={'verbose_name': 'Maintenance préventive récurrente', 'verbose_name_plural': 'Maintenances préventives récurrentes', 'ordering': ['date_debut', 'pk']},
        ),
    ]
