from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0005_force_initial_admin_profile'),
    ]

    operations = [
        migrations.CreateModel(
            name='VocalCommand',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('texte', models.CharField(max_length=1000)),
                ('intention', models.CharField(blank=True, default='', max_length=80)),
                ('confiance', models.FloatField(blank=True, null=True)),
                ('resultat', models.CharField(blank=True, default='', max_length=1000)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('utilisateur', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='commandes_vocales', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-created_at', '-pk']},
        ),
        migrations.AddIndex(
            model_name='vocalcommand',
            index=models.Index(fields=['utilisateur', '-created_at'], name='accounts_vo_utilisa_02ad89_idx'),
        ),
    ]
