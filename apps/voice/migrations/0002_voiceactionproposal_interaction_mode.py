import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('voice', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='voiceagentrequest',
            name='interaction_mode',
            field=models.CharField(default='text', max_length=5),
        ),
        migrations.CreateModel(
            name='VoiceActionProposal',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('outil', models.CharField(max_length=40)),
                ('parametres', models.JSONField()),
                ('parametres_hash', models.CharField(max_length=64)),
                ('resume', models.CharField(max_length=500)),
                ('apercu', models.JSONField()),
                ('spoken_summary', models.CharField(max_length=250)),
                ('statut', models.CharField(choices=[('pending', 'En attente'), ('executed', 'Exécutée'), ('cancelled', 'Annulée'), ('expired', 'Expirée'), ('failed', 'Échec')], default='pending', max_length=12)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('expires_at', models.DateTimeField(db_index=True)),
                ('executed_at', models.DateTimeField(blank=True, null=True)),
                ('resultat', models.JSONField(blank=True, null=True)),
                ('erreur', models.CharField(blank=True, default='', max_length=500)),
                ('conversation', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='action_proposals', to='voice.voiceconversation')),
                ('utilisateur', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='voice_action_proposals', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.AddIndex(
            model_name='voiceactionproposal',
            index=models.Index(fields=['utilisateur', 'conversation', 'statut'], name='voice_prop_user_conv_idx'),
        ),
        migrations.AddIndex(
            model_name='voiceactionproposal',
            index=models.Index(fields=['utilisateur', '-created_at'], name='voice_prop_user_date_idx'),
        ),
    ]
