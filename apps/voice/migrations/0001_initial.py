import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]

    operations = [
        migrations.CreateModel(
            name='VoiceConversation',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('messages', models.JSONField(blank=True, default=list)),
                ('expires_at', models.DateTimeField(db_index=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('utilisateur', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                                   related_name='voice_conversations',
                                                   to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-updated_at']},
        ),
        migrations.CreateModel(
            name='VoiceAgentRequest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('conversation_id', models.UUIDField(blank=True, db_index=True, null=True)),
                ('texte', models.CharField(max_length=2000)),
                ('outils_appeles', models.JSONField(blank=True, default=list)),
                ('resume_resultat', models.CharField(blank=True, default='', max_length=4000)),
                ('duree_ms', models.PositiveIntegerField(default=0)),
                ('statut', models.CharField(choices=[('success', 'Réussie'), ('error', 'Erreur')], max_length=12)),
                ('erreur', models.CharField(blank=True, default='', max_length=120)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('utilisateur', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                                   related_name='voice_agent_requests',
                                                   to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-created_at', '-pk']},
        ),
        migrations.AddIndex(
            model_name='voiceconversation',
            index=models.Index(fields=['utilisateur', 'expires_at'], name='voice_conv_user_exp_idx'),
        ),
        migrations.AddIndex(
            model_name='voiceagentrequest',
            index=models.Index(fields=['utilisateur', '-created_at'], name='voice_req_user_created_idx'),
        ),
    ]
